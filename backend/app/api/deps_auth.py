"""Identity & authorization FastAPI dependencies.

    Authentication -> Identity -> Authorization -> TenantContext
        -> existing TenantScopedRepository -> Database

This module is the HTTP-layer wiring for that pipeline. It is deliberately
separate from app/api/deps.py (which predates identity/authorization and
only resolves path resources like Organization) so the one genuinely
security-sensitive file in the API layer is small and easy to review in
full.

Two authentication mechanisms feed the *same* downstream pipeline
(`authorize_tenant_context` -> `TenantContext` -> `AuthorizationService` —
neither ever creates a second, competing permission system — see SIE
Milestone 20: Production Authentication & Identity Foundation v0.1):

  * `get_dev_authenticated_user_id` — development-only, gated by
    `settings.DEV_MODE`. See its own docstring: no cryptography, trusts a
    plain request header naming an *existing* User by id.
  * `get_production_authenticated_user_id` — real OIDC/OAuth2 Bearer
    token verification (`app.services.oidc_verifier.OIDCTokenVerifier`),
    followed by identity resolution
    (`app.services.identity_service.identity_resolver_service`). This is
    what a real deployment (`DEV_MODE=False`) uses.

`get_authenticated_user_id` is the one dispatcher every human-only route
in this codebase depends on (directly or via `get_tenant_context`): it
picks whichever of the two mechanisms a request actually presented, and
never lets a production Bearer token fall through to the dev-header
mechanism (nor the reverse) — see that function's own docstring for the
exact routing rule and every case it fails closed on.

No HTTP endpoint mints or issues anything here — this module only
*verifies* a token an external identity provider already issued (or, in
DEV_MODE, a trusted header naming an existing user); it is not a
login/token-issuing endpoint itself.
"""

import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.audit_service import AuditAction, audit_service
from app.services.identity_service import identity_resolver_service
from app.services.oidc_verifier import (
    OIDCConfigurationError,
    TokenVerificationError,
    get_oidc_verifier,
)
from app.services.permissions import Permission
from app.services.tenant_context import (
    TenantContext,
    TenantContextError,
    authorize_tenant_context,
)
from app.services.user_service import user_service

DEV_USER_HEADER = "X-SIE-Dev-User-Id"
BEARER_PREFIX = "bearer "


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


def _log_auth_rejected(
    db: Session, *, reason: str, user_id: uuid.UUID | None = None
) -> None:
    """Auditable rejection — see module docstring's security-events
    requirement. `reason` is always a fixed, human-readable phrase from
    this module (never raw token content, a header value, or exception
    internals that could carry it)."""
    audit_service.log(
        db,
        action=AuditAction.AUTH_REJECTED,
        resource_type="Identity",
        user_id=user_id,
        metadata={"reason": reason},
    )


def get_production_authenticated_user_id(token: str, db: Session) -> uuid.UUID:
    """Verify a production Bearer token (real OIDC/OAuth2, never
    development trust) and resolve it to an existing-or-newly-provisioned
    SIE `User`, exactly the way `get_dev_authenticated_user_id` resolves
    the dev header to one — same return type, same downstream contract,
    so `get_tenant_context`/`authorize_tenant_context` and everything
    built on them are completely unaware which mechanism produced the id.

    Fails closed at every step, per the milestone's security requirements:

      * OIDC not configured (`OIDC_ISSUER`/`OIDC_AUDIENCE`/`OIDC_JWKS_URL`
        missing) -> 501, never a silent pass-through.
      * signature invalid, expired, wrong issuer/audience, missing
        subject, malformed, unknown key id -> 401, auditable
        (`AuditAction.AUTH_REJECTED`), never the raw token logged.
      * token verifies but the resolved user's `status` is not `"active"`
        (an inactive/deactivated SIE user — the identity-level analogue
        of a `MembershipStatus` that isn't ACTIVE) -> 401, auditable.

    A verified, active identity is logged as `AuditAction.AUTH_SUCCEEDED`
    and its `user.id` returned — from there, tenant resolution and
    authorization are entirely the existing, unchanged
    `authorize_tenant_context`/`AuthorizationService` pipeline.
    """
    if not token or token.count(".") != 2:
        # Obviously not a JWT (e.g. empty, or garbage with no "." at all)
        # -- a client error, independent of whether OIDC itself happens
        # to be configured, so this is checked (and reported as a plain
        # 401) before the configuration check below rather than being
        # masked by a 501 "not configured" on a deployment that hasn't
        # set up production authentication yet.
        _log_auth_rejected(db, reason="Malformed token: expected a three-segment JWT.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        )

    try:
        verifier = get_oidc_verifier()
    except OIDCConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Production authentication is not configured on this deployment "
                f"({exc})."
            ),
        ) from exc

    try:
        claims = verifier.verify(token)
    except TokenVerificationError as exc:
        _log_auth_rejected(db, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        ) from exc

    user = identity_resolver_service.resolve_or_create_user(db, claims=claims)

    if user.status != "active":
        _log_auth_rejected(db, reason="Resolved identity's user is not active.", user_id=user.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This identity is not active.")

    audit_service.log(
        db,
        action=AuditAction.AUTH_SUCCEEDED,
        resource_type="Identity",
        resource_id=user.id,
        user_id=user.id,
        metadata={"issuer": claims.issuer, "provider": claims.provider},
    )
    return user.id


def get_authenticated_user_id(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> uuid.UUID:
    """The one dispatcher every human-only route depends on (directly, or
    via `get_tenant_context` below): resolves 'the current authenticated
    human user', whichever of the two mechanisms this codebase has
    (development header, production Bearer token) actually applies.

    Routing rule, in order:

      1. `Authorization: Bearer <credential>` present, and `<credential>`
         contains a `:` — this is a *machine* client credential
         (`app.api.deps_machine_auth`'s `<client_id>:<secret>` shape), not
         a human token. Rejected with 401 here rather than silently
         misinterpreting it as something else — a machine credential
         presented to a human-only endpoint (e.g. `/auth/me`) is a caller
         error, not a valid identity of either kind.
      2. `Authorization: Bearer <credential>` present, no `:` — a JWT
         cannot contain the base64url alphabet's excluded `:` character,
         so this is treated as a production access token and routed to
         `get_production_authenticated_user_id`. This is the *only*
         branch that mechanism is reachable from — it never runs as a
         fallback from, or alongside, the dev-header mechanism, which is
         exactly what "no insecure fallback to development authentication
         when DEV_MODE=false" requires: a production Bearer token is
         either verified for real or rejected; it is never silently
         reinterpreted as anything else.
      3. No `Authorization` header (or one that isn't `Bearer`), and
         `settings.DEV_MODE` is false — this deployment has neither
         mechanism reachable for this request. If OIDC itself isn't even
         configured, 501 (nothing is wired up at all — unchanged from
         `get_dev_authenticated_user_id`'s own long-standing behavior).
         If OIDC *is* configured, this is instead reported as 401
         "missing token" — a more specific, and more correct, answer than
         501 once production authentication is genuinely available.
      4. No `Authorization` header (or one that isn't `Bearer`), and
         `settings.DEV_MODE` is true — the existing, unchanged dev-header
         mechanism (`get_dev_authenticated_user_id`).
    """
    if authorization and authorization.lower().startswith(BEARER_PREFIX):
        token = authorization[len(BEARER_PREFIX) :].strip()
        if ":" in token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A machine client credential cannot be used to authenticate as a human user.",
            )
        return get_production_authenticated_user_id(token, db)

    if not settings.DEV_MODE:
        try:
            get_oidc_verifier()
        except OIDCConfigurationError:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=(
                    "Authentication is not configured. This deployment has DEV_MODE "
                    "disabled and no real OIDC/OAuth2 identity provider is wired up yet."
                ),
            ) from None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token. Provide an 'Authorization: Bearer <token>' header.",
        )

    return get_dev_authenticated_user_id(request=request, db=db)


def get_tenant_context(
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_authenticated_user_id),
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
