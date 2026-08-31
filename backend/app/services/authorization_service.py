"""Authorization — deciding whether a user may do something in an
organization.

This is the one place `can(user, permission, organization)` is evaluated.
It performs, in order, exactly the four checks the milestone specifies:

    1. the user exists
    2. the user has a membership in the organization
       (PLATFORM_ADMIN is the one documented exception — see below)
    3. that membership is ACTIVE
    4. the membership's role grants the requested permission

There is no other path to `True`. In particular, this is *not* a general
"is this user special" switch — the platform-admin exception is scoped to
one specific, named role (`User.platform_role ==
app.services.permissions.PLATFORM_ADMIN`), checked explicitly as step 2's
alternative, not a blanket bypass of steps 3-4 or of this function
altogether. That is the distinction the milestone draws between "platform
administrators may have platform-wide permissions where appropriate" and
"do not create an unrestricted superuser path... without explicit role
handling."
"""

import uuid

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.membership_service import membership_service
from app.services.permissions import (
    ALL_PERMISSIONS,
    PLATFORM_ADMIN,
    Permission,
    permissions_for_role,
)


class AuthorizationError(Exception):
    """Raised by `require()` (and available for callers of `can()` that
    prefer to raise their own). Not tied to HTTP — the API layer maps this
    to a 403, but this module has no FastAPI dependency."""


class AuthorizationService:
    def can(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        permission: Permission,
        organization_id: uuid.UUID | None,
    ) -> bool:
        user = db.get(User, user_id)
        if user is None:
            return False

        if user.platform_role == PLATFORM_ADMIN:
            return permission in ALL_PERMISSIONS

        if organization_id is None:
            # No org context and not a platform admin: nothing left to
            # check against. (Global-knowledge reads are deliberately
            # never routed through this method at all — see
            # app/services/tenant_context.py and the README's "Global
            # knowledge" section — so reaching this branch means an
            # organization-scoped permission was checked with no
            # organization, which is correctly "no".)
            return False

        membership = membership_service.get_active_membership(
            db, user_id=user_id, organization_id=organization_id
        )
        if membership is None:
            return False

        return permission in permissions_for_role(membership.role)

    def require(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        permission: Permission,
        organization_id: uuid.UUID | None,
    ) -> None:
        if not self.can(
            db, user_id=user_id, permission=permission, organization_id=organization_id
        ):
            raise AuthorizationError(
                f"user {user_id} lacks permission {permission.value!r}"
                + (f" in organization {organization_id}" if organization_id else "")
            )


authorization_service = AuthorizationService()
