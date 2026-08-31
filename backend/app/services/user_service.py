"""User service.

Not built on `TenantScopedRepository`: a User is a platform-level
identity, not an organization-owned resource (see app/models/user.py) —
there is no `organization_id` to scope reads by. Access to *what a user
can do within an organization* is governed entirely by
`OrganizationMembership` (app/services/membership_service.py) and
evaluated by `app/services/authorization_service.py`, not by anything
here.

`platform_role` is deliberately not settable via `create()`/`UserCreate`
(see app/schemas/user.py) — granting platform-wide administrative access
is treated as its own explicit administrative action
(`set_platform_role`), not a side effect of basic user creation, the same
way membership status/role changes are their own methods on
`OrganizationMembershipService` rather than folded into `create`. No HTTP
endpoint calls `set_platform_role` in this milestone (see the README);
it exists for internal/seeding use and is exercised directly in tests.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate


class UserService:
    def create(self, db: Session, *, obj_in: UserCreate) -> User:
        obj = User(**obj_in.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def get(self, db: Session, *, id: uuid.UUID) -> User | None:
        return db.get(User, id)

    def get_by_email(self, db: Session, *, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return db.execute(stmt).scalar_one_or_none()

    def set_platform_role(
        self, db: Session, *, user: User, platform_role: str | None
    ) -> User:
        user.platform_role = platform_role
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


user_service = UserService()
