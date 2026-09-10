"""Effective-permissions and tenant-selection endpoints — SIE Enterprise
Read API & Browser Integration Foundation v0.1, extended by SIE
Milestone 20 (Production Authentication & Identity Foundation v0.1).

    GET /api/v1/auth/me?organization_id=...
        -> get_tenant_context()          (app.api.deps_auth, UNCHANGED)
        -> authorize_tenant_context()     (app.services.tenant_context, UNCHANGED)
        -> TenantContext.permissions       (already the full, resolved,
                                             backend-authoritative permission set)

**This is the backend-authoritative replacement for the frontend's own
`hasPermission()` stub** (SIE Frontend Foundation v0.1's own documented
limitation — see `src/auth/DevAuthProvider.tsx`'s docstring). It
introduces zero new authorization logic: `get_tenant_context` is the exact
same dependency `app.api.deps_auth.require_permission()` already builds on
for every existing human-only administrative route (memberships, API
clients). `TenantContext.permissions` was already computed by
`permissions_for_role()` — this endpoint's only job is to serialize that
existing, trusted value, never to re-derive or duplicate it (the frontend
must not, and does not, carry its own copy of `ROLE_PERMISSIONS` — see
`docs/FRONTEND_ARCHITECTURE.md`).

**Human-only, deliberately** — mirrors `app/api/deps_context.py`'s own
"item 7" rule: "the human-only administrative surface... is deliberately
never wired to [RequestContext]". A machine client has no per-session
"current user" to introspect; these endpoints answer questions that have
no meaning for a Bearer-credentialed integration.

**Production authentication boundary (SIE Milestone 20).**
`get_tenant_context` now resolves the current human user via
`app.api.deps_auth.get_authenticated_user_id` — the dispatcher that picks
between the development header (`DEV_MODE` only) and real OIDC/OAuth2
Bearer-token verification (`app.services.oidc_verifier`), never both at
once and never an insecure fallback from one to the other. `GET
/api/v1/auth/me` still fails closed (`501`) whenever neither mechanism is
usable for the current request; see that dependency's own docstring for
every case it distinguishes (missing token vs. not configured vs. dev
mode).

**Organization selection (item 3 of the milestone).** `GET
/api/v1/auth/organizations` lets a client discover which organizations the
authenticated identity may explicitly select *before* calling `/auth/me`
— the client still must always name the organization explicitly via
`organization_id`; nothing here (or anywhere else in this codebase) ever
picks one on the caller's behalf. A platform admin's memberships are
listed the same as anyone else's — platform-wide access
(`authorize_tenant_context`'s own platform-admin branch) does not require
an `OrganizationMembership` row to exist, so this list is not necessarily
exhaustive of every organization a platform admin *could* select, only
the ones they hold an explicit membership in; `is_platform_admin` is
surfaced separately so a frontend can present that distinction rather
than being misled by an empty or partial list.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import BEARER_PREFIX, get_authenticated_user_id, get_tenant_context
from app.models.identity import Identity
from app.models.enums import MembershipStatus
from app.models.organization import Organization
from app.schemas.auth import (
    AuthOrganizationMembershipRead,
    AuthOrganizationsRead,
    EffectivePermissionsRead,
)
from app.services.membership_service import membership_service
from app.services.tenant_context import TenantContext
from app.services.user_service import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=EffectivePermissionsRead)
def get_me(
    tenant_context: TenantContext = Depends(get_tenant_context),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> EffectivePermissionsRead:
    user = user_service.get(db, id=tenant_context.user_id)
    if user is None:  # pragma: no cover -- get_tenant_context already resolved this user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user.")

    organization = db.get(Organization, tenant_context.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    is_production = bool(authorization) and authorization.lower().startswith(BEARER_PREFIX)

    identity = None
    if is_production:
        identity = (
            db.query(Identity)
            .filter(Identity.user_id == user.id)
            .order_by(Identity.last_authenticated_at.desc())
            .first()
        )

    return EffectivePermissionsRead(
        user_id=user.id,
        name=user.name,
        email=user.email,
        organization_id=organization.id,
        organization_name=organization.name,
        role=tenant_context.role,
        permissions=sorted(p.value for p in tenant_context.permissions),
        is_platform_admin=user.is_platform_admin,
        auth_mode="production" if is_production else "dev",
        identity_provider=identity.provider if identity is not None else None,
    )


@router.get("/organizations", response_model=AuthOrganizationsRead)
def list_my_organizations(
    user_id: uuid.UUID = Depends(get_authenticated_user_id),
    db: Session = Depends(get_db),
) -> AuthOrganizationsRead:
    """List the organizations the authenticated identity may explicitly
    select — see this module's own docstring. Requires only a resolved
    identity (`get_authenticated_user_id`), not an already-chosen
    organization: this is the endpoint a client calls *before* it has one
    to pass to `/auth/me` or any other `organization_id`-scoped route."""
    user = user_service.get(db, id=user_id)
    if user is None:  # pragma: no cover -- get_authenticated_user_id already resolved this user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user.")

    memberships = [
        m
        for m in membership_service.list_for_user(db, user_id=user_id)
        if m.status == MembershipStatus.ACTIVE
    ]
    rows: list[AuthOrganizationMembershipRead] = []
    for membership in memberships:
        organization = db.get(Organization, membership.organization_id)
        if organization is not None:
            rows.append(
                AuthOrganizationMembershipRead(
                    organization_id=organization.id,
                    organization_name=organization.name,
                    role=membership.role,
                )
            )

    return AuthOrganizationsRead(memberships=rows, is_platform_admin=user.is_platform_admin)


__all__ = ["router"]
