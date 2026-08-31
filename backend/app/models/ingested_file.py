"""IngestedFile — metadata about one uploaded file, independent of what
knowledge document/version it ends up producing.

Deliberately narrow: this table only records what the file *is*
(name, detected type, size, hash, where its bytes live) and its current
processing state. It does not reference a KnowledgeSource or
KnowledgeDocument — that association belongs to IngestionJob (see
app/models/ingestion_job.py), the same separation as elsewhere in this
codebase between "what a thing is" and "what happened to it."

No binary content is stored here or anywhere in PostgreSQL —
`storage_reference` is an opaque key returned by a `StorageProvider`
(app/ingestion/storage.py) pointing at wherever the actual bytes live
(the local filesystem today; object storage later, without a schema
change).

Uploading the same bytes twice is not deduplicated at this table: each
upload is its own IngestedFile row (and its own IngestionJob), because
each upload is a real, distinct event worth keeping a record of. What
*is* deduplicated is the resulting KnowledgeDocumentVersion — reusing the
Knowledge Foundation's existing content_hash idempotency (see
app/services/knowledge_document_version_service.py) rather than adding a
second, competing mechanism here. `content_hash` is indexed (not unique)
so that duplicate-upload detection can still be surfaced as an
informational warning in the ingestion response.
"""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExtractionMethod, ExtractionStatus, IngestionJobStatus


class IngestedFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingested_files"
    __table_args__ = (Index("ix_ingested_files_content_hash", "content_hash"),)

    # Nullable for the same reason KnowledgeSource/KnowledgeDocument's
    # organization_id is nullable: a file can be uploaded for GLOBAL
    # knowledge. Unlike those tables there is no scope_type/CHECK pair
    # here — a file's scope is decided by the source/document it gets
    # associated with via its IngestionJob, not by the file itself.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Display-only. Never used to construct a filesystem/storage path —
    # see app/ingestion/storage.py for how storage keys are actually
    # derived (from content_hash), which is what prevents path traversal
    # regardless of what a client sends here.
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)

    detected_media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    storage_reference: Mapped[str] = mapped_column(String(1000), nullable=False)

    ingestion_status: Mapped[IngestionJobStatus] = mapped_column(
        SAEnum(IngestionJobStatus, name="ingestion_job_status", native_enum=True),
        nullable=False,
        default=IngestionJobStatus.RECEIVED,
    )
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SAEnum(ExtractionStatus, name="extraction_status", native_enum=True),
        nullable=False,
        default=ExtractionStatus.PENDING,
    )
    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(
        SAEnum(ExtractionMethod, name="extraction_method", native_enum=True),
        nullable=True,
    )

    organization: Mapped["Organization | None"] = relationship()  # noqa: F821
    jobs: Mapped[list["IngestionJob"]] = relationship(  # noqa: F821
        back_populates="file",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<IngestedFile id={self.id!s} original_filename={self.original_filename!r} "
            f"detected_media_type={self.detected_media_type!r} "
            f"ingestion_status={self.ingestion_status!s}>"
        )
