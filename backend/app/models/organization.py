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
    users: Mapped[list["User"]] = relationship(  # noqa: F821
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    data_sources: Mapped[list["DataSource"]] = relationship(  # noqa: F821
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    knowledge_sources: Mapped[list["KnowledgeSource"]] = relationship(  # noqa: F821
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Organization id={self.id!s} name={self.name!r}>"
