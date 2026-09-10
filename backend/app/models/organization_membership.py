"""OrganizationMembership — the authoritative link between a User and an
Organization, with a role and a status.

This is the record `app/services/tenant_context.py::build_tenant_context`
and `app/services/authorization_service.py::AuthorizationService.can` read
to decide whether a user may act within an organization at all, and with
what permissions. `User.organization_id` (see app/models/user.py) is not
consulted for this — membership is the single source of truth for access,
by design, so there is exactly one place that answers "is this user
allowed in this organization."

One row per (user, organization) pair — see the unique constraint below —
rather than one row per membership *event*. A status change (suspend,
revoke, reactivate) updates the existing row in place; it does not insert
a new one. This is what "prevents duplicate active membership
relationships for the same user and organization" without needing a
partial/conditional unique index: duplicates of any status are prevented,
which is a strictly stronger and simpler guarantee.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MembershipStatus


class OrganizationMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "organization_id", name="uq_organization_memberships_user_organization"
        ),
        Index("ix_organization_memberships_organization_id_role", "organization_id", "role"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # A plain string, validated against app.services.permissions.OrganizationRole
    # at the service layer rather than a native DB enum — see
    # app/models/enums.py and app/services/permissions.py for why.
    role: Mapped[str] = mapped_column(String(50), nullable=False)

    status: Mapped[MembershipStatus] = mapped_column(
        SAEnum(MembershipStatus, name="membership_status", native_enum=True),
        nullable=False,
        default=MembershipStatus.ACTIVE,
    )

    user: Mapped["User"] = relationship(back_populates="memberships")  # noqa: F821
    organization: Mapped["Organization"] = relationship(back_populates="memberships")  # noqa: F821

    @property
    def is_active(self) -> bool:
        return self.status == MembershipStatus.ACTIVE

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<OrganizationMembership id={self.id!s} user_id={self.user_id!s} "
            f"organization_id={self.organization_id!s} role={self.role!r} "
            f"status={self.status!s}>"
        )
