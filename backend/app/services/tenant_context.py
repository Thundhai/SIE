"""TenantContext — a trusted, pre-authorized bundle of "who, where, and
what they can do", handed to services instead of a bare organization_id.

    Authenticated User -> Membership -> Authorized Organization
        -> TenantContext -> Service -> Repository

`TenantContext` itself is a plain, inert data holder — the security
property lives entirely in how one gets created. The only way to obtain
one is `authorize_tenant_context()` below, which performs the real check
(active membership required) and is the sole holder of the private token
`TenantContext.__init__` requires. Calling `TenantContext(...)` directly
without that token raises `TypeError`. This will not stop a determined
reader of this source file, but Python has no true access control — the
goal is to make "just construct a TenantContext with whatever
organization_id you want" fail loudly by construction, rather than merely
being discouraged by convention, so a future call site can't do it by
accident (e.g. copy-pasting a test's identity-injection code into a real
request path).

For GLOBAL knowledge, note there is *no* TenantContext at all — global
resources are read via the existing `NullableTenantScopedRepository` with
`organization_id=None` directly (see app/services/knowledge_source_service.py),
exactly as before this milestone. TenantContext exists only for
*organization*-scoped access; "does this request even need one" is a
decision the calling route makes (see app/api/deps.py), not something
this module decides on its own.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services.membership_service import membership_service
from app.services.permissions import (
    ALL_PERMISSIONS,
    PLATFORM_ADMIN,
    Permission,
    permissions_for_role,
)
from app.services.user_service import user_service

_FACTORY_TOKEN = object()
"""Only known inside this module. See module docstring."""


@dataclass(frozen=True)
class TenantContext:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    permissions: frozenset[Permission]
    _token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _FACTORY_TOKEN:
            raise TypeError(
                "TenantContext must be constructed via "
                "app.services.tenant_context.authorize_tenant_context() — "
                "it is what performs the membership/authorization check "
                "this object asserts has already happened."
            )

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions


class TenantContextError(Exception):
    """Raised by `authorize_tenant_context()` when the user does not have
    active, authorized access to the requested organization. The API
    layer maps this to a 403 (see app/api/deps.py)."""


def authorize_tenant_context(
    db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID
) -> TenantContext:
    """The only supported way to obtain a `TenantContext`.

    Resolves the user's *active* membership in `organization_id` and
    packages its role and permissions. Raises `TenantContextError` — never
    returns a partially-authorized or empty-permission context — if the
    user doesn't exist, has no membership, or that membership isn't
    ACTIVE. A platform admin is granted a context with every permission
    without requiring a membership row to exist, mirroring
    `AuthorizationService.can`'s explicit (not blanket) platform-admin
    exception.
    """
    user = user_service.get(db, id=user_id)
    if user is None:
        raise TenantContextError(f"user {user_id} not found")

    if user.platform_role == PLATFORM_ADMIN:
        return TenantContext(
            user_id=user_id,
            organization_id=organization_id,
            role=PLATFORM_ADMIN,
            permissions=ALL_PERMISSIONS,
            _token=_FACTORY_TOKEN,
        )

    membership = membership_service.get_active_membership(
        db, user_id=user_id, organization_id=organization_id
    )
    if membership is None:
        raise TenantContextError(
            f"user {user_id} has no active membership in organization {organization_id}"
        )

    return TenantContext(
        user_id=user_id,
        organization_id=organization_id,
        role=membership.role,
        permissions=permissions_for_role(membership.role),
        _token=_FACTORY_TOKEN,
    )
