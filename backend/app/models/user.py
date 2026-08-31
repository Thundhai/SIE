"""User model — a person belonging to an Organization.

This is a platform/tenant user record for SIE itself (not a Safelytic or
other external-application account). Authentication/authorization is out of
scope for this foundation phase.
"""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_organization_id_email"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    organization: Mapped["Organization"] = relationship(back_populates="users")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id!s} organization_id={self.organization_id!s} email={self.email!r}>"
