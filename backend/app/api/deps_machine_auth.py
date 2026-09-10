"""Machine-client authentication — milestone item 10.

    external system -> Authorization: Bearer <client_id>:<secret>
        -> ApiClientService.authenticate() -> MachineClientContext
        -> require_scope(Permission.SAFETY_DATA_WRITE) -> ingestion routes

Deliberately **not** `app/api/deps_auth.py`'s development-only
`X-SIE-Dev-User-Id` header mechanism — that mechanism exists purely to
exercise the human-identity/authorization pipeline ahead of a real
OIDC/OAuth2 integration and is explicitly documented as unfit for any
production integration (see that module's own docstring). This is the
credential external systems (Safelytic or any other connected
application) actually use to push data into
`POST /api/v1/intelligence/events`/`/events/batch`.

`MachineClientContext` mirrors `app.services.tenant_context.TenantContext`'s
shape (a trusted, pre-authorized bundle handed to route handlers) but is
deliberately a separate, simpler type: a machine client has explicit
`scopes` granted at creation time (see `app/models/api_client.py`), never
a role-derived permission set inherited from an `OrganizationMembership`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission


@dataclass(frozen=True)
class MachineClientContext:
    api_client_id: uuid.UUID
    organization_id: uuid.UUID
    client_id: str
    scopes: frozenset[str]

    def has_scope(self, permission: Permission) -> bool:
        return permission.value in self.scopes


def get_machine_client_context(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MachineClientContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header "
            "(expected 'Bearer <client_id>:<secret>').",
        )
    token = authorization[len("Bearer ") :].strip()
    if ":" not in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed bearer credential (expected '<client_id>:<secret>').",
        )
    client_id, secret = token.split(":", 1)

    api_client = api_client_service.authenticate(db, client_id=client_id, secret=secret)
    if api_client is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid, expired, or revoked API client credential."
        )

    # Item 24's own example list ("API_AUTHENTICATED") — logged here, once
    # per machine-authenticated request, since machine-to-machine
    # integration is the actual new external surface this milestone is
    # about (never logged for the pre-existing dev-mode human header,
    # which already has its own, more specific per-action audit entries).
    from app.services.audit_service import AuditAction, audit_service

    audit_service.log(
        db,
        action=AuditAction.API_AUTHENTICATED,
        resource_type="ApiClient",
        resource_id=api_client.id,
        organization_id=api_client.organization_id,
        metadata={"client_id": api_client.client_id, "scope_count": len(api_client.scopes)},
    )

    return MachineClientContext(
        api_client_id=api_client.id,
        organization_id=api_client.organization_id,
        client_id=api_client.client_id,
        scopes=frozenset(api_client.scopes),
    )


def require_scope(permission: Permission) -> Callable[..., MachineClientContext]:
    """Dependency factory: `Depends(require_scope(Permission.SAFETY_DATA_WRITE))`
    — mirrors `app.api.deps_auth.require_permission`'s shape exactly."""

    def _dependency(
        context: MachineClientContext = Depends(get_machine_client_context), db: Session = Depends(get_db)
    ) -> MachineClientContext:
        if not context.has_scope(permission):
            from app.services.audit_service import AuditAction, audit_service

            audit_service.log(
                db,
                action=AuditAction.API_ACCESS_DENIED,
                resource_type="ApiClient",
                resource_id=context.api_client_id,
                organization_id=context.organization_id,
                metadata={"client_id": context.client_id, "required_scope": permission.value},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API client missing required scope: {permission.value}",
            )
        return context

    return _dependency
