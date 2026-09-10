"""`GET /api/v1/auth/me` and `GET /api/v1/auth/organizations` response
schemas — see `app/api/v1/auth.py`'s own docstring for the full design
rationale (backend-authoritative effective permissions and tenant
context, replacing anything the frontend might otherwise derive itself).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class EffectivePermissionsRead(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    organization_id: uuid.UUID
    organization_name: str
    #: An `OrganizationRole` value (e.g. "ORG_ADMIN"), or the literal
    #: string "PLATFORM_ADMIN" when `is_platform_admin` is true — see
    #: `app.services.tenant_context.authorize_tenant_context()`'s own
    #: platform-admin branch.
    role: str
    #: `Permission` values (e.g. "safety_data:read"), sorted for a
    #: deterministic response — never re-derived by the frontend, only
    #: consumed. See `app/api/v1/auth.py`'s own docstring.
    permissions: list[str]
    is_platform_admin: bool
    #: "dev" or "production" — which of the two authentication mechanisms
    #: (`app.api.deps_auth`) resolved this request. Display/diagnostic
    #: only, e.g. so a frontend can visibly disclose "this is a
    #: development identity, not a real login" (SIE Milestone 20).
    auth_mode: str
    #: The `Identity.provider` label (e.g. "azuread", "okta") of the most
    #: recently authenticated external identity linked to this user, or
    #: `None` if this user has never authenticated via a production OIDC
    #: token (e.g. a dev-mode-only user, or one provisioned by other
    #: means). Never the issuer/subject themselves, and never a token —
    #: display-only, per the milestone's "without exposing secrets or raw
    #: tokens" requirement.
    identity_provider: str | None = None


class AuthOrganizationMembershipRead(BaseModel):
    """One organization the authenticated identity may explicitly select
    — see `app/api/v1/auth.py::list_my_organizations`'s own docstring for
    why this exists (multi-organization identities must be handled
    explicitly, never silently defaulted)."""

    organization_id: uuid.UUID
    organization_name: str
    role: str


class AuthOrganizationsRead(BaseModel):
    memberships: list[AuthOrganizationMembershipRead]
    is_platform_admin: bool
