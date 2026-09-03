"""Unified request-context dependency — Intelligence Platform Integration
& Enterprise API v0.1, items 7-8, 17-20.

Composes the two EXISTING authentication mechanisms this codebase
already has (never a third — item 5's "do not create a second competing
authentication system" applied to this internal composition too):
`app.api.deps_auth`'s development-only human identity header, and
`app.api.deps_machine_auth`'s machine-client Bearer credential.
`RequestContext` is a thin wrapper over whichever one a given request
actually presented, so a capability genuinely meant for either kind of
caller (analytics, predictions, knowledge retrieval, RAG query) can
accept one dependency instead of duplicating auth branching in every
router.

    Authorization: Bearer <client_id>:<secret>  -> machine (MachineClientContext)
    X-SIE-Dev-User-Id: <uuid>  (DEV_MODE only)    -> human (existing user)
    neither                                       -> 401

**Item 36 — a machine client's organization is never overridable.**
`authorize_context()` below is the one place that matters: for a machine
caller it requires the endpoint's own `organization_id` to equal
`ApiClient.organization_id` (resolved once, at authentication time, never
a request field) before even checking scope — no scope, however broad,
lets a machine client reach a different organization's data. A human
caller has no fixed organization; the same function instead asks
`authorization_service` exactly as `app.api.deps_auth.require_permission`
already does, so both branches funnel through this codebase's one real
authorization check for organization-scoped human access.

**Item 9 — GLOBAL knowledge is not organization-scoped at all.** When
`organization_id` is `None` (a GLOBAL-only request), this module's rule
for a *human* caller matches the one `app/api/v1/retrieval.py` already
established: authentication alone is sufficient, no permission/scope
check, since GLOBAL content was never gated by any one organization's
role to begin with. A *machine* caller is different: it has no
organization-membership-derived role to fall back on at all — only the
scopes it was explicitly granted at credential-creation time — so a
GLOBAL request from a machine client still requires the endpoint's own
permission/scope, exactly as an organization-scoped request would.
Otherwise any active credential, regardless of what it was actually
provisioned to do (e.g. an ingestion-only `safety_data:write` client),
could read GLOBAL knowledge/analytics/predictions for free — least
privilege (item 6) applies to GLOBAL reads too, not only
organization-scoped ones.

**Item 7 — human vs machine access are not interchangeable everywhere.**
This module is opt-in per router. The human-only administrative surface
(model governance/approval, API client management, membership
management) is deliberately never wired to it — those routers keep using
`app.api.deps_auth` alone, unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_dev_authenticated_user_id, get_production_authenticated_user_id
from app.api.deps_machine_auth import get_machine_client_context
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission


@dataclass(frozen=True)
class RequestContext:
    """`kind` is `"human"` or `"machine"` — the two, and only two,
    identity kinds this codebase authenticates (see module docstring)."""

    kind: str
    user_id: uuid.UUID | None = None
    api_client_id: uuid.UUID | None = None
    client_id: str | None = None
    machine_organization_id: uuid.UUID | None = None  # set only for kind == "machine"
    scopes: frozenset[str] = frozenset()

    @property
    def is_machine(self) -> bool:
        return self.kind == "machine"

    @property
    def identity_label(self) -> str:
        """Safe-to-log identifier for this caller — never a secret, never
        raw request content. Used by observability/audit call sites."""
        return f"api_client:{self.client_id}" if self.is_machine else f"user:{self.user_id}"


def get_request_context(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> RequestContext:
    """Picks whichever of the three mechanisms this request actually
    presented. A `Bearer` credential is checked first, then disambiguated
    by shape — a machine `<client_id>:<secret>` credential always
    contains a `:`, which a JWT's base64url segments never do (see
    `app.api.deps_auth.get_authenticated_user_id`'s own docstring for the
    identical rule used there):

        Authorization: Bearer <client_id>:<secret>  -> machine (MachineClientContext)
        Authorization: Bearer <JWT>                  -> human, production (SIE Milestone 20)
        X-SIE-Dev-User-Id: <uuid>  (DEV_MODE only)    -> human, development
        none of the above                             -> 401 or 501 (fail closed)
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[len("bearer ") :].strip()
        if ":" in token:
            machine_context = get_machine_client_context(authorization=authorization, db=db)
            return RequestContext(
                kind="machine",
                api_client_id=machine_context.api_client_id,
                client_id=machine_context.client_id,
                machine_organization_id=machine_context.organization_id,
                scopes=machine_context.scopes,
            )
        user_id = get_production_authenticated_user_id(token, db)
        return RequestContext(kind="human", user_id=user_id)

    user_id = get_dev_authenticated_user_id(request=request, db=db)
    return RequestContext(kind="human", user_id=user_id)


def authorize_context(
    db: Session,
    context: RequestContext,
    *,
    permission: Permission,
    organization_id: uuid.UUID | None,
) -> bool:
    """The one real authorization check this module performs — see
    module docstring for the machine-organization-pinning and
    GLOBAL-knowledge rules this encodes."""
    if organization_id is None:
        # GLOBAL: for a human caller, authentication alone is this
        # codebase's existing rule (see module docstring) — reaching this
        # function at all already proves that. A machine client is
        # different: it has no organization-membership-derived role to
        # fall back on, only the scopes explicitly granted to it at
        # credential-creation time, so a GLOBAL request must still carry
        # the endpoint's own required scope — otherwise any credential,
        # regardless of what it was actually provisioned for (e.g. an
        # ingestion-only `safety_data:write` client), could read GLOBAL
        # knowledge/analytics/predictions for free. This does not touch
        # organization-scoped authorization below, which already checks
        # scope for machine callers.
        if context.is_machine:
            return permission.value in context.scopes
        return True
    if context.is_machine:
        return organization_id == context.machine_organization_id and permission.value in context.scopes
    return authorization_service.can(
        db, user_id=context.user_id, permission=permission, organization_id=organization_id
    )


def require_context_permission(permission: Permission) -> Callable[..., RequestContext]:
    """Dependency factory for the common case: `organization_id` is a
    required query parameter and the caller (human or machine) must have
    `permission` in it. Mirrors `app.api.deps_auth.require_permission`'s
    and `app.api.deps_machine_auth.require_scope`'s shape — this is the
    one dependency an endpoint reaches for when it wants to accept both
    identity kinds instead of picking one of those two.

    Routes that allow an *optional* `organization_id` (a GLOBAL-capable
    query, e.g. `app/api/v1/retrieval.py`/`rag.py`) don't use this
    factory — they call `get_request_context()` and `authorize_context()`
    directly against their own (body-supplied, not query-supplied)
    `organization_id`, the same way they already call
    `authorization_service.can()` conditionally today.
    """

    def _dependency(
        organization_id: uuid.UUID = Query(...),
        context: RequestContext = Depends(get_request_context),
        db: Session = Depends(get_db),
    ) -> RequestContext:
        if not authorize_context(db, context, permission=permission, organization_id=organization_id):
            _log_access_denied(db, context, permission=permission, organization_id=organization_id)
            detail = (
                f"API client is not authorized for organization {organization_id} or is missing "
                f"scope {permission.value}."
                if context.is_machine
                else f"Missing {permission.value} permission in the requested organization."
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        return context

    return _dependency


def _log_access_denied(
    db: Session, context: RequestContext, *, permission: Permission, organization_id: uuid.UUID | None
) -> None:
    from app.services.audit_service import AuditAction, audit_service

    audit_service.log(
        db,
        action=AuditAction.API_ACCESS_DENIED,
        resource_type="RequestContext",
        organization_id=organization_id,
        user_id=context.user_id,
        metadata={
            "identity": context.identity_label,
            "kind": context.kind,
            "required_permission": permission.value,
        },
    )
