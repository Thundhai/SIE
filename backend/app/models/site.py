"""Site model — a physical/operational location owned by an Organization."""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Site(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (
        # SIE Milestone 35A: lets a child table's own foreign key be
        # declared as the composite (child_column, organization_id) ->
        # (id, organization_id), which Postgres then enforces as a
        # genuine schema-level guarantee that a referencing row's
        # organization_id always matches this site's own -- not merely
        # checked by application code. See app/models/project_site.py's
        # own docstring for the one place this is actually used, and
        # why the identical guarantee is architecturally not possible
        # for `SafetyEvent.attributed_project_id` (an `ON DELETE SET
        # NULL` column).
        UniqueConstraint("id", "organization_id", name="uq_sites_id_organization_id"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    organization: Mapped["Organization"] = relationship(back_populates="sites")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Site id={self.id!s} organization_id={self.organization_id!s} name={self.name!r}>"
