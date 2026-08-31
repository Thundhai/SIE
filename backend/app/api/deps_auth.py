"""Identity & authorization FastAPI dependencies.

    Authentication -> Identity -> Authorization -> TenantContext
        -> existing TenantScopedRepository -> Database

This module is the HTTP-layer wiring for that pipeline. It is deliberately
separate from app/api/deps.py (which predates identity/authorization and
only resolves path resources like Organization) so the one genuinely
security-sensitive file in the API layer is small and easy to review in
full.

THERE IS NO REAL AUTHENTICATION IMPLEMENTED YET. `get_dev_authenticated_user_id`
below is the *only* way a request currently gets an authenticated
identity, and it exists purely to exercise the rest of this pipeline
(authorization, TenantContext, membership checks) end-to-end ahead of a
real OIDC/OAuth2 integration. It:

  * only operates when `settings.DEV_MODE` is true (default: false — see
    app/core/config.py). With DEV_MODE off (the production default),
    every route that depends on this raises 501, not "falls back to
    trusting the caller" — failing closed, not open.
  * reads a plain request header (`X-SIE-Dev-User-Id`) naming an
    *existing* User by id. It grants exactly that user's real, already-
    stored permissions (via `authorize_tenant_context`) — it cannot grant
    a permission the named user doesn't otherwise have, and it cannot
    grant access to an organization the named user isn't an active member
    of (or a platform admin). There is no way to pass permissions or an
    organization directly; only a user id.
  * performs no cryptography and trusts the header completely, which is
    exactly why it is gated the way it is. Nothing about it resembles a
    production authentication mechanism (no token, no signature, no
    expiry) — it must be replaced by real OIDC/OAuth2 token verification
    (see app/services/identity_service.py::TokenVerifier) before any
    production deployment. See the README's "Identity architecture"
    section.

No HTTP endpoint mints or issues anything here — this is a request-header
convention consumed by a dependency, not a login/token endpoint, per the
milestone's own preference for "dependency injection/mocked identity...
rather than exposing a development HTTP endpoint."
"""

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.permissions import Permission
from app.services.tenant_context import (
    TenantContext,
    TenantContextError,
    authorize_tenant_context,
)
from app.services.user_service import user_service

DEV_USER_HEADER = "X-SIE-Dev-User-Id"


def get_dev_authenticated_user_id(
    request: Request,
    db: Session = Depends(get_db),
) -> uuid.UUID:
    """Resolve 'the current user' for this request. See module docstring —
    this is a development-only mechanism, not authentication."""
    if not settings.DEV_MODE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Authentication is not configured. This deployment has DEV_MODE "
                "disabled and no real OIDC/OAuth2 identity provider is wired up yet."
            ),
        )

    header_value = request.headers.get(DEV_USER_HEADER)
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {DEV_USER_HEADER} header (development-mode identity required).",
        )
    try:
        user_id = uuid.UUID(header_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{DEV_USER_HEADER} must be a UUID.",
        ) from exc

    if user_service.get(db, id=user_id) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user.")
    return user_id


def get_tenant_context(
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Authorize the current user for the organization named in the URL
    path and return the resulting TenantContext, or 403.

    This is the concrete answer to "the URL organization_id must no
    longer be treated as sufficient proof of access": the path parameter
    is only ever used here to ask `authorize_tenant_context` whether the
    authenticated user actually has active membership in it — never to
    filter data directly.
    """
    try:
        return authorize_tenant_context(db, user_id=user_id, organization_id=organization_id)
    except TenantContextError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def require_permission(permission: Permission) -> Callable[..., TenantContext]:
    """Dependency factory: `Depends(require_permission(Permission.USERS_MANAGE))`.

    Builds on `get_tenant_context` (so membership/active-status is always
    checked first) and additionally requires the resulting context to
    carry the given permission, or 403.
    """

    def _dependency(context: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if not context.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission.value}",
            )
        return context

    return _dependency
