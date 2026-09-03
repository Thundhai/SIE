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


class EmbeddingDimensionMismatchError(ValueError):
    """Raised immediately, before any provider call or DB write, when a
    provider's own output dimension does not match this deployment's one
    central `settings.EMBEDDING_DIMENSIONS` — the pgvector column's fixed
    width (see app/models/embedding.py's own docstring).

    This architecture assumes **one configured vector dimension per
    deployment** — the pgvector `vector(N)` column type is fixed-width at
    creation time, so a single `knowledge_chunk_embeddings` table cannot
    simultaneously hold, say, 256-dim hashing vectors and 384-dim
    sentence-transformer vectors. That is not a limitation introduced
    here; it is what a fixed-width SQL column type means. Supporting
    multiple *simultaneous* embedding dimensions safely would require a
    real schema redesign (one column/table per dimension, or a
    variable-length representation pgvector does not offer) — deliberately
    not undertaken, since nothing in this codebase's own requirements
    needs more than one embedding model live at a time.

    Switching to a model with a different dimension is still fully
    supported — it is a **new migration** (widening or replacing the
    `vector(N)` column, exactly as `EMBEDDING_DIMENSIONS`'s own docstring
    in app/core/config.py already says) plus setting `EMBEDDING_DIMENSIONS`
    to match that model's real output dimension *before* that migration
    ever runs — migration 0006 reads the setting live, at migration-run
    time, not a value baked into the migration file, specifically so this
    works without editing the migration itself.

    Without this check, a misconfigured deployment (e.g.
    `EMBEDDING_PROVIDER=sentence_transformers` with a model whose real
    dimension doesn't match a stale `EMBEDDING_DIMENSIONS`) would only
    surface as an opaque `psycopg.errors.DataException: expected N
    dimensions, not M` from deep inside the INSERT — this raises the same
    fact immediately, with an actionable message, before ever calling the
    provider or touching the database.
    """


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
class _PendingEmbedding:
    """One chunk that has passed every eligibility check (not empty, not
    INSUFFICIENT-quality without override, not already embedded under
    this exact model identity) and is ready to actually be sent to the
    provider. Internal to this module — never returned to a caller."""

    chunk: KnowledgeChunk
    content: str
    content_hash: str
    existing: KnowledgeChunkEmbedding | None


@dataclass
class BatchEmbeddingReport:
    """Summary of one `generate_embeddings_for_version`/`embed_chunks_batch`
    call — see those functions' own docstrings for the idempotency/
    failure-reporting contract this exists to satisfy.

    `document_version_id` is `None` for a batch not scoped to a single
    version (e.g. a re-embedding run spanning a document's chunks
    directly — see `app/embeddings/reembedding_service.py`); populated
    when the caller has one (e.g. `generate_embeddings_for_version`)."""

    document_version_id: uuid.UUID | None = None
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

        A thin, single-chunk wrapper around `embed_chunks_batch` (SIE
        Milestone 21) — same eligibility rules, same failure reporting,
        just for exactly one chunk. Kept as its own method because a lot
        of call sites (query embedding aside — that's a different thing
        entirely, see `RetrievalService`) genuinely only have one chunk
        in hand.
        """
        provider = provider or get_embedding_provider()
        self._check_dimensions(provider)
        outcome, pending = self._resolve_eligibility(db, chunk=chunk, provider=provider, force=force)
        if outcome is not None:
            return outcome
        return self._embed_pending(db, provider=provider, pending=[pending])[0]

    def embed_chunks_batch(
        self,
        db: Session,
        *,
        chunks: list[KnowledgeChunk],
        provider: EmbeddingProvider | None = None,
        force: bool = False,
        document_version_id: uuid.UUID | None = None,
    ) -> BatchEmbeddingReport:
        """Embed a list of chunks — SIE Milestone 21's real batching entry
        point. The model/provider is resolved exactly **once** (never
        loaded per chunk — item 6), and every chunk that actually needs
        embedding is sent to the provider in **one** `embed_texts()` call
        (never one `embed_text()` call per chunk — item 7), letting a real
        model batch its own forward pass instead of running one text at a
        time. Chunks that don't need embedding at all (already embedded
        under this exact model identity, empty content, INSUFFICIENT
        quality without override) never reach the provider — resolved
        first, cheaply, from the database alone.

        **Batch-call failure isolation.** If the single batched
        `embed_texts()` call itself raises (a real provider failure, or a
        test double that fails on one specific input), this does not fail
        every chunk in the batch: the batch is retried one chunk at a time
        so a single bad chunk's failure is reported against *that* chunk
        alone (`FAILED`), while every chunk that succeeds on its own is
        still `CREATED` — the same resilience `generate_embeddings_for_version`
        has always offered, now sitting behind real batching for the
        common (everything-succeeds) case instead of always embedding one
        chunk at a time.

        A dimension mismatch (`EmbeddingDimensionMismatchError`) is
        different: it is a deployment-level configuration error affecting
        every chunk equally, not a per-chunk data problem, so it is
        deliberately allowed to propagate and abort the whole call
        immediately rather than being reported as N separate failures.
        """
        provider = provider or get_embedding_provider()
        self._check_dimensions(provider)

        report = BatchEmbeddingReport(document_version_id=document_version_id)
        pending: list[_PendingEmbedding] = []
        for chunk in chunks:
            outcome, item = self._resolve_eligibility(db, chunk=chunk, provider=provider, force=force)
            if outcome is not None:
                report.outcomes.append(outcome)
            else:
                assert item is not None  # exactly one of (outcome, item) is set
                pending.append(item)

        report.outcomes.extend(self._embed_pending(db, provider=provider, pending=pending))

        logger.info(
            "embedding_batch_complete",
            extra={
                "document_version_id": str(document_version_id) if document_version_id else None,
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

    def generate_embeddings_for_version(
        self,
        db: Session,
        *,
        version_id: uuid.UUID,
        provider: EmbeddingProvider | None = None,
    ) -> BatchEmbeddingReport:
        """Embed every chunk belonging to one `KnowledgeDocumentVersion`.

        Idempotent and safe to re-run: chunks already embedded under this
        provider/model identity are skipped, never duplicated. Thin
        wrapper around `embed_chunks_batch` — see that method's own
        docstring for the real-batching and failure-isolation contract
        this inherits unchanged; this method's own public contract
        (arguments, return shape, idempotency, per-chunk failure
        reporting) is untouched from before SIE Milestone 21.
        """
        provider = provider or get_embedding_provider()
        self._check_dimensions(provider)

        chunks = db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_version_id == version_id)
            .order_by(KnowledgeChunk.chunk_index)
        ).scalars().all()

        return self.embed_chunks_batch(
            db, chunks=list(chunks), provider=provider, document_version_id=version_id
        )

    def _check_dimensions(self, provider: EmbeddingProvider) -> None:
        if provider.dimensions != settings.EMBEDDING_DIMENSIONS:
            raise EmbeddingDimensionMismatchError(
                f"EmbeddingProvider {provider.provider_name!r} (model "
                f"{provider.model_name!r}:{provider.model_version!r}) produces "
                f"{provider.dimensions}-dimensional vectors, but this deployment's "
                f"pgvector column is configured for EMBEDDING_DIMENSIONS="
                f"{settings.EMBEDDING_DIMENSIONS}. Set EMBEDDING_DIMENSIONS to "
                f"match this provider's real output dimension (and run a new "
                f"migration to widen the column) before embedding with it, or "
                f"choose a provider/model whose dimension already matches."
            )

    def _resolve_eligibility(
        self,
        db: Session,
        *,
        chunk: KnowledgeChunk,
        provider: EmbeddingProvider,
        force: bool,
    ) -> tuple[EmbeddingOutcome | None, _PendingEmbedding | None]:
        """Every check `embed_chunk` used to make before ever calling a
        provider, extracted so `embed_chunks_batch` can run it once per
        chunk *before* deciding what to actually send to the provider in
        one call. Returns exactly one of `(outcome, None)` — nothing more
        to do for this chunk — or `(None, pending)` — this chunk is
        eligible and ready to embed."""
        content = chunk.content or ""
        if not content.strip():
            return (
                EmbeddingOutcome(
                    chunk_id=chunk.id,
                    status=EmbeddingOutcomeStatus.SKIPPED_EMPTY_CONTENT,
                    reason="Chunk has no usable text content to embed.",
                ),
                None,
            )

        if (
            chunk.quality_status == QualityStatus.INSUFFICIENT
            and not force
            and not settings.EMBED_INSUFFICIENT_QUALITY_CHUNKS
        ):
            return (
                EmbeddingOutcome(
                    chunk_id=chunk.id,
                    status=EmbeddingOutcomeStatus.SKIPPED_INSUFFICIENT_QUALITY,
                    reason=(
                        "Chunk quality_status is INSUFFICIENT; set "
                        "EMBED_INSUFFICIENT_QUALITY_CHUNKS=true or pass force=True "
                        "to embed it anyway."
                    ),
                ),
                None,
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
                return (
                    EmbeddingOutcome(
                        chunk_id=chunk.id,
                        status=EmbeddingOutcomeStatus.SKIPPED_EXISTING,
                        embedding=existing,
                        reason="Already embedded under this exact model identity.",
                    ),
                    None,
                )
            if existing.content_hash != content_hash and not force:
                return (
                    EmbeddingOutcome(
                        chunk_id=chunk.id,
                        status=EmbeddingOutcomeStatus.SKIPPED_STALE_CONTENT_HASH,
                        embedding=existing,
                        reason=(
                            "An embedding already exists for this chunk/model, but its "
                            "content_hash no longer matches the chunk's current content "
                            "(chunks are expected to be immutable — this should not "
                            "normally happen). Pass force=True to re-embed."
                        ),
                    ),
                    None,
                )

        return None, _PendingEmbedding(
            chunk=chunk, content=content, content_hash=content_hash, existing=existing
        )

    def _embed_pending(
        self,
        db: Session,
        *,
        provider: EmbeddingProvider,
        pending: list[_PendingEmbedding],
    ) -> list[EmbeddingOutcome]:
        """Send every pending chunk to `provider.embed_texts()` in one
        real batch call. On failure, isolate: retry one chunk at a time
        so a single bad input is reported against just that chunk rather
        than failing chunks that would have succeeded — see
        `embed_chunks_batch`'s own docstring."""
        if not pending:
            return []

        contents = [item.content for item in pending]
        try:
            vectors = provider.embed_texts(contents)
            if len(vectors) != len(pending):
                raise ValueError(
                    f"Provider {provider.provider_name!r} returned {len(vectors)} "
                    f"vector(s) for {len(pending)} input text(s)."
                )
            return self._write_rows(db, provider=provider, pending=pending, vectors=vectors)
        except Exception as exc:  # noqa: BLE001 - isolated/reported below, never swallowed
            if len(pending) == 1:
                # Safe structured logging (never the chunk's own content):
                # chunk id and error type/message only.
                logger.warning(
                    "embedding_failed",
                    extra={
                        "chunk_id": str(pending[0].chunk.id),
                        "provider": provider.provider_name,
                        "model_name": provider.model_name,
                        "model_version": provider.model_version,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                return [
                    EmbeddingOutcome(
                        chunk_id=pending[0].chunk.id,
                        status=EmbeddingOutcomeStatus.FAILED,
                        reason=f"{type(exc).__name__}: {exc}",
                    )
                ]

            logger.warning(
                "embedding_batch_call_failed_isolating_per_chunk",
                extra={
                    "provider": provider.provider_name,
                    "model_name": provider.model_name,
                    "model_version": provider.model_version,
                    "batch_size": len(pending),
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            outcomes: list[EmbeddingOutcome] = []
            for item in pending:
                outcomes.extend(self._embed_pending(db, provider=provider, pending=[item]))
            return outcomes

    def _write_rows(
        self,
        db: Session,
        *,
        provider: EmbeddingProvider,
        pending: list[_PendingEmbedding],
        vectors: list[list[float]],
    ) -> list[EmbeddingOutcome]:
        """Create-or-update one `KnowledgeChunkEmbedding` row per
        (pending, vector) pair, committing once for the whole group
        (real batching all the way to the database write, not just the
        provider call) rather than once per row."""
        touched: list[tuple[_PendingEmbedding, KnowledgeChunkEmbedding]] = []
        for item, vector in zip(pending, vectors):
            if item.existing is not None:
                row = item.existing
                row.provider = provider.provider_name
                row.model_name = provider.model_name
                row.model_version = provider.model_version
                row.dimensions = provider.dimensions
                row.content_hash = item.content_hash
                row.embedding = vector
                row.organization_id = item.chunk.organization_id
            else:
                row = KnowledgeChunkEmbedding(
                    knowledge_chunk_id=item.chunk.id,
                    organization_id=item.chunk.organization_id,
                    provider=provider.provider_name,
                    model_name=provider.model_name,
                    model_version=provider.model_version,
                    dimensions=provider.dimensions,
                    content_hash=item.content_hash,
                    embedding=vector,
                )
            db.add(row)
            touched.append((item, row))

        db.commit()

        outcomes = []
        for item, row in touched:
            db.refresh(row)
            outcomes.append(
                EmbeddingOutcome(chunk_id=item.chunk.id, status=EmbeddingOutcomeStatus.CREATED, embedding=row)
            )
        return outcomes


embedding_service = EmbeddingService()
