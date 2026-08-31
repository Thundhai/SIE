"""KnowledgeChunk — a citable slice of one document version's content.

Chunks are the smallest unit of provenance: `document_version_id` (plus,
transitively through the version and document, the source) is what will
let a future evidence-citation feature point at exactly the passage a
claim came from. No embedding or vector column exists yet — this table
only carries the plain text and the structural metadata (page, section,
ordering) needed to display and cite a chunk; semantic search is future
work layered on top of this table, not part of it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, utcnow

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

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Free-form structured metadata (e.g. clause numbers, table refs) kept
    # for future evidence-citation use. Python attribute is `chunk_metadata`
    # because `metadata` is reserved by SQLAlchemy's declarative base; the
    # underlying column is still named `metadata`.
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
