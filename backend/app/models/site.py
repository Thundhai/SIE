"""Site model — a physical/operational location owned by an Organization."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Site(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    organization: Mapped["Organization"] = relationship(back_populates="sites")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Site id={self.id!s} organization_id={self.organization_id!s} name={self.name!r}>"
