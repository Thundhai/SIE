"""IngestionJob — one immutable attempt to ingest one IngestedFile.

Mirrors the KnowledgeDocument/KnowledgeDocumentVersion split: IngestedFile
holds current, mutable state about a file; each IngestionJob is a
point-in-time record of one processing attempt against it (a file could,
in principle, be reprocessed later by a new job — e.g. after an adapter
improves — without losing the history of earlier attempts).

`organization_id`/`source_id`/`document_id` are all nullable and all
`ON DELETE SET NULL` (matching AuditLog's reasoning, not
KnowledgeDocument's): a job is a historical log entry about what was
*attempted*, and should stay queryable even if the organization, source,
or document it targeted is later deleted. `file_id` is the one required,
`ON DELETE CASCADE` reference — a job about a deleted file is meaningless
on its own.

There is no `document_version_id` column here, even though a job's
successful outcome is "a KnowledgeDocumentVersion was created or reused."
That association is recoverable without one: the job's IngestedFile
carries the same `content_hash` the resulting KnowledgeDocumentVersion
was created (or matched) with, so
`app/services/knowledge_provenance_service.py::get_ingestion_provenance`
joins job -> file -> (document_id, content_hash) -> version rather than
this table carrying a fourth FK for a value that's already determined by
the other three plus the file.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import IngestionJobStatus


class IngestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ingested_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[IngestionJobStatus] = mapped_column(
        SAEnum(IngestionJobStatus, name="ingestion_job_status", native_enum=True),
        nullable=False,
        default=IngestionJobStatus.RECEIVED,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped["IngestedFile"] = relationship(back_populates="jobs")  # noqa: F821
    organization: Mapped["Organization | None"] = relationship()  # noqa: F821
    source: Mapped["KnowledgeSource | None"] = relationship()  # noqa: F821
    document: Mapped["KnowledgeDocument | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IngestionJob id={self.id!s} file_id={self.file_id!s} status={self.status!s}>"
