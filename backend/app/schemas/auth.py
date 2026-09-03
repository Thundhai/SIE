"""`GET /api/v1/auth/me` response schema — see `app/api/v1/auth.py`'s
own docstring for the full design rationale (backend-authoritative
effective permissions, replacing the frontend's `hasPermission()` stub).
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
