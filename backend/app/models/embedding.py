"""KnowledgeChunkEmbedding — one embedding vector for one KnowledgeChunk,
under one specific embedding model identity.

    KnowledgeChunk -> EmbeddingService -> KnowledgeChunkEmbedding (this table)

**One row per (chunk, provider, model_name, model_version) combination —
never one row per chunk.** A chunk can have multiple embeddings, one per
embedding model it has ever been embedded under:

    Chunk A
    ├── Embedding(provider=hashing, model=sie-hashing-embedder, version=v1)
    └── Embedding(provider=sentence_transformers, model=all-MiniLM-L6-v2, version=1)

This is what lets embedding models change over time without silently
invalidating history: re-embedding under a new model/version creates a
*new* row rather than overwriting the old one (see
`UniqueConstraint` below, and `app/services/embedding_service.py`'s own
idempotency docstring). `RetrievalService` always searches within one
named model identity — vectors produced by different models are never
compared against each other, since nothing guarantees their vector
spaces are even remotely compatible.

Fields, matching the milestone's own spec:

  * `provider` / `model_name` / `model_version` / `dimensions` — the full
    embedding model identity. Plain strings (not a native DB enum): like
    `KnowledgeChunk.extraction_method`'s sibling fields, this vocabulary
    is provider/config-driven and expected to grow, not a small closed
    set a migration should gate.
  * `content_hash` — sha256 of the exact chunk content that was embedded
    (`app.ingestion.hashing.sha256_hex`, the same hashing already used
    for file/version content addressing elsewhere in this codebase). Lets
    a future consistency check detect a chunk whose content has drifted
    from what its embedding actually represents, without needing to
    re-embed to find out.
  * `embedding` — the actual vector, `pgvector.sqlalchemy.Vector` sized
    from the *one* central `settings.EMBEDDING_DIMENSIONS` value (see
    that setting's own docstring for why this must never be hardcoded a
    second time) — never returned directly by any API response (see
    app/schemas/retrieval.py).

`organization_id` is denormalized straight from the embedded chunk at
write time — the same "copy tenant identity onto the child row so
queries can filter directly, without a join" precedent used by
`KnowledgeChunk.organization_id` itself (see that model's docstring).
This is not decorative: `RetrievalService` filters on this column
*explicitly*, in the same query that does the vector search, precisely so
tenant isolation is never enforced by "vector similarity alone happens
not to cross tenants" — see the README's tenant isolation section.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.models.base import Base, UUIDPrimaryKeyMixin, utcnow


class KnowledgeChunkEmbedding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_chunk_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_chunk_id",
            "provider",
            "model_name",
            "model_version",
            name="uq_knowledge_chunk_embeddings_chunk_model",
        ),
    )

    knowledge_chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Denormalized from the chunk at embedding time — see module
    # docstring. NULL exactly when the chunk's own organization_id is
    # NULL (GLOBAL knowledge).
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)

    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.EMBEDDING_DIMENSIONS), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    knowledge_chunk: Mapped["KnowledgeChunk"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<KnowledgeChunkEmbedding id={self.id!s} "
            f"knowledge_chunk_id={self.knowledge_chunk_id!s} "
            f"provider={self.provider!r} model={self.model_name!r}:{self.model_version!r}>"
        )
