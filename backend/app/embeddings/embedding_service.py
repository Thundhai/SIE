"""EmbeddingService — turns one already-persisted `KnowledgeChunk` into a
stored `KnowledgeChunkEmbedding` row.

    KnowledgeChunk -> validate -> content_hash -> EmbeddingProvider
        -> KnowledgeChunkEmbedding

This is the one place a `KnowledgeChunk`'s text is ever sent to an
`EmbeddingProvider`. It never modifies the source chunk (no write to
`KnowledgeChunk.content` or any of its other fields happens here — the
chunk is read-only input) and never invents content: a chunk that has
nothing usable to embed is skipped, not silently embedded as a zero
vector pretending to mean something.

Called from application/service code that already has an authorized
`KnowledgeChunk` in hand (the same "caller resolves and authorizes first,
this service trusts the object it's given" shape as
`app/services/chunking_service.py` and `app/services/knowledge_chunk_service.py`)
— this module performs no tenant authorization of its own.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.embeddings.provider import EmbeddingProvider, get_embedding_provider
from app.ingestion.hashing import sha256_hex
from app.models.embedding import KnowledgeChunkEmbedding
from app.models.enums import QualityStatus
from app.models.knowledge_chunk import KnowledgeChunk

logger = logging.getLogger(__name__)


class EmbeddingOutcomeStatus(str, Enum):
    """What happened for one chunk. Deliberately not booleans/exceptions
    for the common cases — a skip is an expected, everyday outcome
    (already embedded, empty content, low quality), not a failure."""

    CREATED = "created"
    SKIPPED_EXISTING = "skipped_existing"
    SKIPPED_EMPTY_CONTENT = "skipped_empty_content"
    SKIPPED_INSUFFICIENT_QUALITY = "skipped_insufficient_quality"
    SKIPPED_STALE_CONTENT_HASH = "skipped_stale_content_hash"
    FAILED = "failed"


@dataclass
class EmbeddingOutcome:
    chunk_id: uuid.UUID
    status: EmbeddingOutcomeStatus
    embedding: KnowledgeChunkEmbedding | None = None
    reason: str | None = None


@dataclass
class BatchEmbeddingReport:
    """Summary of one `generate_embeddings_for_version` call — see that
    function's own docstring for the idempotency/failure-reporting
    contract this exists to satisfy."""

    document_version_id: uuid.UUID
    outcomes: list[EmbeddingOutcome] = field(default_factory=list)

    @property
    def created(self) -> int:
        return self._count(EmbeddingOutcomeStatus.CREATED)

    @property
    def skipped(self) -> int:
        return sum(
            self._count(s)
            for s in (
                EmbeddingOutcomeStatus.SKIPPED_EXISTING,
                EmbeddingOutcomeStatus.SKIPPED_EMPTY_CONTENT,
                EmbeddingOutcomeStatus.SKIPPED_INSUFFICIENT_QUALITY,
                EmbeddingOutcomeStatus.SKIPPED_STALE_CONTENT_HASH,
            )
        )

    @property
    def failed(self) -> int:
        return self._count(EmbeddingOutcomeStatus.FAILED)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    def _count(self, status: EmbeddingOutcomeStatus) -> int:
        return sum(1 for o in self.outcomes if o.status == status)


class EmbeddingService:
    def embed_chunk(
        self,
        db: Session,
        *,
        chunk: KnowledgeChunk,
        provider: EmbeddingProvider | None = None,
        force: bool = False,
    ) -> EmbeddingOutcome:
        """Embed one chunk under `provider` (defaults to
        `get_embedding_provider()`, i.e. whatever `EMBEDDING_PROVIDER`
        app setting names).

        Idempotent: if this exact (chunk, provider, model_name,
        model_version) combination already has an embedding whose
        `content_hash` matches the chunk's current content, the existing
        row is returned unchanged — no duplicate is created, and the
        provider is never even called. `force=True` is the one way to
        actually recompute and overwrite an existing row (e.g. a genuine
        content-hash mismatch, or deliberately re-embedding); without it,
        a mismatch is reported as `SKIPPED_STALE_CONTENT_HASH` rather
        than silently overwritten — see the milestone's own "do not
        overwrite historical embeddings blindly" instruction.
        """
        provider = provider or get_embedding_provider()

        content = chunk.content or ""
        if not content.strip():
            return EmbeddingOutcome(
                chunk_id=chunk.id,
                status=EmbeddingOutcomeStatus.SKIPPED_EMPTY_CONTENT,
                reason="Chunk has no usable text content to embed.",
            )

        if (
            chunk.quality_status == QualityStatus.INSUFFICIENT
            and not force
            and not settings.EMBED_INSUFFICIENT_QUALITY_CHUNKS
        ):
            return EmbeddingOutcome(
                chunk_id=chunk.id,
                status=EmbeddingOutcomeStatus.SKIPPED_INSUFFICIENT_QUALITY,
                reason=(
                    "Chunk quality_status is INSUFFICIENT; set "
                    "EMBED_INSUFFICIENT_QUALITY_CHUNKS=true or pass force=True "
                    "to embed it anyway."
                ),
            )

        content_hash = sha256_hex(content.encode("utf-8"))

        existing = db.execute(
            select(KnowledgeChunkEmbedding).where(
                KnowledgeChunkEmbedding.knowledge_chunk_id == chunk.id,
                KnowledgeChunkEmbedding.provider == provider.provider_name,
                KnowledgeChunkEmbedding.model_name == provider.model_name,
                KnowledgeChunkEmbedding.model_version == provider.model_version,
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.content_hash == content_hash and not force:
                return EmbeddingOutcome(
                    chunk_id=chunk.id,
                    status=EmbeddingOutcomeStatus.SKIPPED_EXISTING,
                    embedding=existing,
                    reason="Already embedded under this exact model identity.",
                )
            if existing.content_hash != content_hash and not force:
                return EmbeddingOutcome(
                    chunk_id=chunk.id,
                    status=EmbeddingOutcomeStatus.SKIPPED_STALE_CONTENT_HASH,
                    embedding=existing,
                    reason=(
                        "An embedding already exists for this chunk/model, but its "
                        "content_hash no longer matches the chunk's current content "
                        "(chunks are expected to be immutable — this should not "
                        "normally happen). Pass force=True to re-embed."
                    ),
                )

        try:
            vector = provider.embed_text(content)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            # Safe structured logging (milestone item 26): chunk id and
            # error type/message only — never the chunk's own content.
            logger.warning(
                "embedding_failed",
                extra={
                    "chunk_id": str(chunk.id),
                    "provider": provider.provider_name,
                    "model_name": provider.model_name,
                    "model_version": provider.model_version,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            return EmbeddingOutcome(
                chunk_id=chunk.id,
                status=EmbeddingOutcomeStatus.FAILED,
                reason=f"{type(exc).__name__}: {exc}",
            )

        if existing is not None and force:
            existing.provider = provider.provider_name
            existing.model_name = provider.model_name
            existing.model_version = provider.model_version
            existing.dimensions = provider.dimensions
            existing.content_hash = content_hash
            existing.embedding = vector
            existing.organization_id = chunk.organization_id
            db.commit()
            db.refresh(existing)
            return EmbeddingOutcome(
                chunk_id=chunk.id, status=EmbeddingOutcomeStatus.CREATED, embedding=existing
            )

        record = KnowledgeChunkEmbedding(
            knowledge_chunk_id=chunk.id,
            organization_id=chunk.organization_id,
            provider=provider.provider_name,
            model_name=provider.model_name,
            model_version=provider.model_version,
            dimensions=provider.dimensions,
            content_hash=content_hash,
            embedding=vector,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return EmbeddingOutcome(
            chunk_id=chunk.id, status=EmbeddingOutcomeStatus.CREATED, embedding=record
        )

    def generate_embeddings_for_version(
        self,
        db: Session,
        *,
        version_id: uuid.UUID,
        provider: EmbeddingProvider | None = None,
    ) -> BatchEmbeddingReport:
        """Embed every chunk belonging to one `KnowledgeDocumentVersion`.

        Idempotent and safe to re-run: chunks already embedded under this
        provider/model identity are skipped (see `embed_chunk`), never
        duplicated. Failures on individual chunks are collected into the
        report rather than aborting the whole batch — one bad chunk does
        not block embedding the rest of the version.
        """
        provider = provider or get_embedding_provider()

        chunks = db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_version_id == version_id)
            .order_by(KnowledgeChunk.chunk_index)
        ).scalars().all()

        report = BatchEmbeddingReport(document_version_id=version_id)
        for chunk in chunks:
            report.outcomes.append(self.embed_chunk(db, chunk=chunk, provider=provider))

        logger.info(
            "embedding_batch_complete",
            extra={
                "document_version_id": str(version_id),
                "provider": provider.provider_name,
                "model_name": provider.model_name,
                "model_version": provider.model_version,
                "total": report.total,
                "chunks_created": report.created,
                "chunks_skipped": report.skipped,
                "chunks_failed": report.failed,
            },
        )
        return report


embedding_service = EmbeddingService()
