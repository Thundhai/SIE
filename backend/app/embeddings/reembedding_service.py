"""ReembeddingService — the explicit, service-level seam for re-embedding
already-ingested content under a new (or the same) embedding model
identity. SIE Milestone 21: Real Semantic Embedding & Retrieval
Productionization v0.1, items 9-10.

    document
       |
       v
    current KnowledgeDocumentVersion
       |
       v
    eligible chunks              (KnowledgeChunk rows for that version)
       |
       v
    selected model identity      (an explicit EmbeddingProvider — never
       |                          get_embedding_provider()'s ambient default)
       v
    batch embedding               (EmbeddingService.embed_chunks_batch —
       |                          one real provider call, not one per chunk)
       v
    new embedding rows            (KnowledgeChunkEmbedding, under that
                                    provider's own (provider, model_name,
                                    model_version) identity)

**This is a synchronous, on-demand seam — not a background worker.**
Calling it re-embeds whatever chunks it's given, in the calling request/
process, and returns a report. Bulk background processing (a queue, a
scheduled job, a Celery/Redis worker) is explicitly out of this
milestone's scope — see its own "explicit exclusions" list — this module
is the seam such a worker would call into later, not the worker itself.

**Never destructive.** A re-embedding call only ever writes rows under
the *given* `provider`'s own `(provider_name, model_name, model_version)`
identity (`KnowledgeChunkEmbedding`'s own unique constraint scopes rows
by exactly that triple, per chunk — see `app/models/embedding.py`). An
existing model identity's rows are structurally untouched by a call
naming a *different* identity: there is no code path here (or anywhere
in `EmbeddingService`) that deletes or overwrites a
`KnowledgeChunkEmbedding` row under a different `(provider, model_name,
model_version)` than the one it was just asked to write. Re-embedding
under the *same* identity again is still governed by `EmbeddingService`'s
own existing idempotency rule: unchanged content is left alone unless
`force=True` is passed explicitly.

**The target model identity is always explicit.** Every method below
requires `provider` — there is no default to `get_embedding_provider()`'s
ambient, settings-driven identity. A re-embedding operation choosing a
model "by accident" (because someone changed `EMBEDDING_PROVIDER` and
happened to also trigger a re-embed) is exactly the failure mode item 9
guards against; the caller must always name the target model identity by
constructing (or being handed) a specific `EmbeddingProvider` instance.

**Provenance, document version, organization scope, and timestamps are
preserved automatically, by construction** — this module adds no new
logic for any of them because none is needed: `EmbeddingService` already
copies `organization_id` from the chunk being embedded, the pgvector row
carries its own `created_at`/`content_hash`, and neither this module nor
`EmbeddingService` ever modifies a `KnowledgeChunk`, its
`document_version_id`, or any ancestor `KnowledgeDocument`/
`KnowledgeSource` row — only `KnowledgeChunkEmbedding` rows are ever
written here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings.embedding_service import BatchEmbeddingReport, embedding_service
from app.embeddings.provider import EmbeddingProvider
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument


class UnknownDocumentError(ValueError):
    """Raised when `reembed_document_current_version` is given a
    `document_id` that does not resolve to an existing `KnowledgeDocument`,
    or whose `current_version_id` is unset (no version has ever been
    published for it) — a clear, immediate error rather than silently
    re-embedding zero chunks and reporting an empty, misleadingly
    "successful" report."""


class ReembeddingService:
    def reembed_document_version(
        self,
        db: Session,
        *,
        version_id: uuid.UUID,
        provider: EmbeddingProvider,
        force: bool = False,
        include_insufficient_quality: bool = False,
    ) -> BatchEmbeddingReport:
        """Re-embed every eligible chunk of one specific
        `KnowledgeDocumentVersion` under `provider`'s explicit model
        identity.

        `force=False` (the default): chunks already embedded under this
        exact `(provider, model_name, model_version)` identity, with
        matching content, are left alone (idempotent — safe to call
        repeatedly, e.g. after a partial prior run). `force=True` also
        recomputes chunks that already have a matching-hash embedding
        under this identity — the one deliberate way to force a genuine
        recompute (e.g. after fixing a bug in a locally-trained model)
        without touching any other model identity's rows.

        `include_insufficient_quality=True` additionally embeds chunks
        whose `quality_status` is INSUFFICIENT (normally skipped) —
        opt-in per call, distinct from the global
        `settings.EMBED_INSUFFICIENT_QUALITY_CHUNKS` switch, so a
        deliberate re-embedding run can choose this without changing
        that deployment-wide default.
        """
        chunks = (
            db.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_version_id == version_id)
                .order_by(KnowledgeChunk.chunk_index)
            )
            .scalars()
            .all()
        )

        if include_insufficient_quality:
            # embed_chunks_batch's own per-chunk quality gate only opens
            # for INSUFFICIENT chunks when force=True or the global
            # EMBED_INSUFFICIENT_QUALITY_CHUNKS setting is on -- force=True
            # here would also blindly recompute already-embedded HIGH/
            # MEDIUM/LOW chunks, which is not what this flag means. Route
            # around that by embedding the two groups separately: normal
            # chunks keep the caller's own `force`, INSUFFICIENT chunks are
            # embedded via the global-override path (force=True on just
            # that subset achieves "include them" without forcing a
            # recompute of everything else).
            from app.models.enums import QualityStatus

            normal_chunks = [c for c in chunks if c.quality_status != QualityStatus.INSUFFICIENT]
            insufficient_chunks = [c for c in chunks if c.quality_status == QualityStatus.INSUFFICIENT]

            report = embedding_service.embed_chunks_batch(
                db, chunks=normal_chunks, provider=provider, force=force, document_version_id=version_id
            )
            if insufficient_chunks:
                extra = embedding_service.embed_chunks_batch(
                    db,
                    chunks=insufficient_chunks,
                    provider=provider,
                    force=True,
                    document_version_id=version_id,
                )
                report.outcomes.extend(extra.outcomes)
            return report

        return embedding_service.embed_chunks_batch(
            db, chunks=chunks, provider=provider, force=force, document_version_id=version_id
        )

    def reembed_document_current_version(
        self,
        db: Session,
        *,
        document_id: uuid.UUID,
        provider: EmbeddingProvider,
        force: bool = False,
        include_insufficient_quality: bool = False,
    ) -> BatchEmbeddingReport:
        """Convenience entry point matching this module's own "document
        -> eligible chunks" diagram: resolves `document_id`'s
        `current_version_id` and delegates to
        `reembed_document_version`. Superseded/historical versions are
        not touched by this call — re-embed a specific past version
        directly via `reembed_document_version(version_id=...)` if that
        is genuinely what's needed."""
        document = db.get(KnowledgeDocument, document_id)
        if document is None or document.current_version_id is None:
            raise UnknownDocumentError(
                f"Document {document_id} does not exist or has no current published "
                "version to re-embed."
            )
        return self.reembed_document_version(
            db,
            version_id=document.current_version_id,
            provider=provider,
            force=force,
            include_insufficient_quality=include_insufficient_quality,
        )


reembedding_service = ReembeddingService()
