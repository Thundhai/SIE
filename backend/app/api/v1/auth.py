"""Effective-permissions endpoint — SIE Enterprise Read API & Browser
Integration Foundation v0.1.

    GET /api/v1/auth/me?organization_id=...
        -> get_tenant_context()          (app.api.deps_auth, UNCHANGED)
        -> authorize_tenant_context()     (app.services.tenant_context, UNCHANGED)
        -> TenantContext.permissions       (already the full, resolved,
                                             backend-authoritative permission set)

**This is the backend-authoritative replacement for the frontend's own
`hasPermission()` stub** (SIE Frontend Foundation v0.1's own documented
limitation — see `src/auth/DevAuthProvider.tsx`'s docstring: "the
backend has no endpoint to resolve a user's effective permission set").
It introduces zero new authorization logic: `get_tenant_context` is the
exact same dependency `app.api.deps_auth.require_permission()` already
builds on for every existing human-only administrative route
(memberships, API clients). `TenantContext.permissions` was already
computed by `permissions_for_role()` — this endpoint's only job is to
serialize that existing, trusted value, never to re-derive or duplicate
it (the frontend must not, and does not, carry its own copy of
`ROLE_PERMISSIONS` — see `docs/FRONTEND_ARCHITECTURE.md`).

**Human-only, deliberately** — mirrors `app/api/deps_context.py`'s own
"item 7" rule: "the human-only administrative surface... is deliberately
never wired to [RequestContext]". A machine client has no per-session
"current user" to introspect; this endpoint answers "who am I, as the
authenticated human, and what can I do in this organization", a
question that has no meaning for a Bearer-credentialed integration.

**Production authentication boundary.** Like every other route built on
`app.api.deps_auth`, this endpoint fails closed (`501`) whenever
`settings.DEV_MODE` is `False` and no real identity provider is wired —
see that module's own docstring and `docs/FRONTEND_ARCHITECTURE.md`'s
"Production authentication boundary" section for what remains external
infrastructure (a real OIDC/OAuth2 `TokenVerifier` implementation,
`app.services.identity_service.TokenVerifier`) versus what is already a
clean, working seam (everything from `Identity` through this endpoint).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_tenant_context
from app.models.organization import Organization
from app.schemas.auth import EffectivePermissionsRead
from app.services.tenant_context import TenantContext
from app.services.user_service import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=EffectivePermissionsRead)
def get_me(
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> EffectivePermissionsRead:
    user = user_service.get(db, id=tenant_context.user_id)
    if user is None:  # pragma: no cover -- get_tenant_context already resolved this user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user.")

    organization = db.get(Organization, tenant_context.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    return EffectivePermissionsRead(
        user_id=user.id,
        name=user.name,
        email=user.email,
        organization_id=organization.id,
        organization_name=organization.name,
        role=tenant_context.role,
        permissions=sorted(p.value for p in tenant_context.permissions),
        is_platform_admin=user.is_platform_admin,
    )


__all__ = ["router"]
