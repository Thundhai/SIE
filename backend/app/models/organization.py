"""Organization model — the tenant root entity.

Organization is the top of SIE's tenant hierarchy: every other
organization-owned table (Site, User, DataSource, and future tables) points
back to it via `organization_id`. Organization itself has no
`organization_id` — it *is* the tenant.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    sites: Mapped[list["Site"]] = relationship(  # noqa: F821
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    # No delete-orphan here, deliberately: a User is not owned by its
    # default organization (organization_id is a convenience reference,
    # not tenancy — see app/models/user.py) so deleting an organization
    # must not delete the users who merely defaulted to it. The
    # organization_id FK itself is ON DELETE SET NULL, not CASCADE.
    users: Mapped[list["User"]] = relationship(back_populates="organization")  # noqa: F821
    data_sources: Mapped[list["DataSource"]] = relationship(  # noqa: F821
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    knowledge_sources: Mapped[list["KnowledgeSource"]] = relationship(  # noqa: F821
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list["OrganizationMembership"]] = relationship(  # noqa: F821
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    # SIE Milestone 43A: this organization's own standards-catalogue
    # entries (ORGANIZATION-scoped `GoverningStandard` rows only --
    # GLOBAL catalogue entries have no `organization_id` to relate
    # through) and its append-only selection/retirement event log.
    governing_standards: Mapped[list["GoverningStandard"]] = relationship(  # noqa: F821
        cascade="all, delete-orphan",
        overlaps="organization",
    )
    governing_standard_selections: Mapped[list["OrganizationGoverningStandard"]] = relationship(  # noqa: F821
        cascade="all, delete-orphan",
        overlaps="organization",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Organization id={self.id!s} name={self.name!r}>"
