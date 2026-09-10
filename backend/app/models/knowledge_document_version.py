"""KnowledgeDocumentVersion — one immutable ingested snapshot of a document.

Versions are append-only: a version's content is never edited in place,
only superseded by a newer version (`superseded_at`). This is why the
model has `created_at` but deliberately no `updated_at` — unlike the
mutable resources elsewhere in the app, a version row does not change
after it is written except for `superseded_at` and `ingestion_status`
being advanced by ingestion processing.

`content_hash` plus the unique constraint below is what gives duplicate
detection and version integrity: re-ingesting byte-identical content for
the same document is a no-op rather than a silent duplicate (see
KnowledgeDocumentVersionService.create).

No binary content is stored here. `storage_reference` is a placeholder
pointer at wherever the real file will eventually live (object storage);
`extracted_text` is plain extracted text for downstream processing, not a
document store.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import IngestionStatus


class KnowledgeDocumentVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "content_hash", name="uq_knowledge_document_versions_document_content"
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    storage_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ingestion_status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, name="knowledge_ingestion_status", native_enum=True),
        nullable=False,
        default=IngestionStatus.RECEIVED,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    document: Mapped["KnowledgeDocument"] = relationship(  # noqa: F821
        back_populates="versions",
        foreign_keys=[document_id],
    )
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(  # noqa: F821
        back_populates="document_version",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<KnowledgeDocumentVersion id={self.id!s} document_id={self.document_id!s} "
            f"version_label={self.version_label!r} ingestion_status={self.ingestion_status!s}>"
        )
