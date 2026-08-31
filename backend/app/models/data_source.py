"""DataSource model — an external/internal system SIE ingests data from.

Ingestion logic itself is out of scope for this foundation phase; this
model only records that a data source exists, its type, and sync status.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DataSource(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="data_sources")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DataSource id={self.id!s} organization_id={self.organization_id!s} "
            f"name={self.name!r} source_type={self.source_type!r}>"
        )
