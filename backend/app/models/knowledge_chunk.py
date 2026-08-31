"""KnowledgeChunk — a citable slice of one document version's content.

Chunks are the smallest unit of provenance: `document_version_id` (plus,
transitively through the version and document, the source) is what will
let a future evidence-citation feature point at exactly the passage a
claim came from. No embedding or vector column exists yet — this table
only carries the plain text and the structural metadata (page, section,
ordering) needed to display and cite a chunk; semantic search is future
work layered on top of this table, not part of it.

**Knowledge Quality & Semantic Chunking Foundation v0.1** expanded this
table (additive only — see migrations/versions/0005_*.py) to carry the
full location/provenance/quality surface a chunk needs to stand on its
own as a piece of evidence:

  * `document_id`, `source_id`, `organization_id` — denormalized from
    `document_version.document`, following the exact precedent already
    established by `KnowledgeDocument.organization_id` (see that model's
    own docstring): copied at write time purely so a chunk can be
    tenant-filtered and looked up by document/source directly, without
    three joins back through the version and document on every query.
    They are not an independent source of truth — `document_version_id`
    remains the one real foreign key a chunk's identity depends on.
  * `content_type`, `sheet_name`, `row_number`, `slide_number`,
    `section_path`, `source_reference`, `extraction_method` — promoted
    from being buried inside `chunk_metadata` JSON to real, indexable
    columns, because these are exactly the fields a future retrieval
    filter ("only PPTX slides", "only rows from sheet X", "only chunks
    under this section") needs to query on directly.
  * `quality_status` — the deterministic extraction/structure quality
    assessment from `app/ingestion/quality.py` (HIGH/MEDIUM/LOW/
    INSUFFICIENT). This is *not* a judgment about whether the underlying
    safety content is true or authoritative — see that module's
    docstring for the full separation-of-concerns rationale. The
    human-readable reasons behind the status stay in `chunk_metadata`
    (`quality_reasons`) rather than becoming their own columns, since
    they're a variable-length explanation, not something ever filtered
    or joined on.

Deliberately NOT added as real columns, despite being listed in the
milestone spec's chunk-metadata section: `language`, `industry_sector`,
`jurisdiction`, `publication_date`, `effective_date`, `verification_status`.
These already live, as the single source of truth, on `KnowledgeSource`
(jurisdiction/industry_sector/authority_level/verification_status) or
`KnowledgeDocumentVersion` (publication_date/effective_date) or
`KnowledgeDocument` (language). Copying them onto every chunk row would
mean thousands of chunks going stale the moment a source's
`verification_status` changes, or need a bulk-update fan-out this
milestone explicitly has no worker/background-job infrastructure to run
(see the milestone's own "no Celery/Kafka/background workers" boundary).
Instead they are recorded as a point-in-time *snapshot* inside
`chunk_metadata` at chunk-creation time (see
app/services/chunking_service.py) — enough for a future retrieval filter
to use without a join, while the live/current value always remains
queryable from its one real owning table.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import ContentType, ExtractionMethod, QualityStatus

# JSON everywhere except PostgreSQL, where it becomes a real JSONB column.
_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class KnowledgeChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "chunk_index", name="uq_knowledge_chunks_version_index"
        ),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Denormalized from document_version.document — see module docstring.
    # Nullable only for ORM-level construction convenience; the service
    # layer always supplies all three (chunking_service.py never leaves a
    # chunk without full lineage).
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # NULL exactly when the owning source is GLOBAL — same convention as
    # KnowledgeDocument.organization_id.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)

    content_type: Mapped[ContentType] = mapped_column(
        SAEnum(ContentType, name="knowledge_chunk_content_type", native_enum=True),
        nullable=False,
        default=ContentType.TEXT,
    )

    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Full section breadcrumb, e.g. ["Working at Height", "Fall Protection"]
    # — see app/ingestion/structure.py. A plain JSON list, not a separate
    # table: it is display/citation metadata for one chunk, never queried
    # or joined on element-by-element.
    section_path: Mapped[list[str] | None] = mapped_column(_JSONType, nullable=True)
    # Human-readable pointer to exactly where in the source this chunk
    # came from, e.g. "Page 47, Section 6.2" / "Slide 17" / "Sheet
    # Incident Register, Row 124" — see app/ingestion/chunking.py.
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(
        SAEnum(ExtractionMethod, name="extraction_method", native_enum=True),
        nullable=True,
    )
    # Deterministic extraction/structure quality — see
    # app/ingestion/quality.py's module docstring for why this is
    # entirely separate from source authority and verification status.
    quality_status: Mapped[QualityStatus] = mapped_column(
        SAEnum(QualityStatus, name="knowledge_chunk_quality_status", native_enum=True),
        nullable=False,
    )

    # Free-form structured metadata (quality_reasons, the source-metadata
    # snapshot described in the module docstring, row/table part
    # numbering, etc.) kept for future evidence-citation use. Python
    # attribute is `chunk_metadata` because `metadata` is reserved by
    # SQLAlchemy's declarative base; the underlying column is still named
    # `metadata`.
    chunk_metadata: Mapped[dict | None] = mapped_column("metadata", _JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    document_version: Mapped["KnowledgeDocumentVersion"] = relationship(  # noqa: F821
        back_populates="chunks"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<KnowledgeChunk id={self.id!s} document_version_id={self.document_version_id!s} "
            f"chunk_index={self.chunk_index}>"
        )
