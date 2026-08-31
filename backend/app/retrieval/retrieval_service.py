"""RetrievalService — metadata-filtered semantic similarity search over
`KnowledgeChunkEmbedding`, returning ranked evidence.

    query text -> EmbeddingProvider -> query vector
        -> [tenant filter] + [metadata filters] + [vector similarity]
        -> ranked, thresholded RetrievalResult list

**This service returns evidence, not answers.** It does not call an LLM,
does not assemble a prompt, and does not generate prose — there is no
reasoning layer anywhere in this call chain. See the README's "Semantic
Knowledge Architecture" section for the explicit statement that RAG/LLM
integration is not implemented by this milestone.

**Tenant isolation is enforced by an explicit SQL predicate on
`KnowledgeChunkEmbedding.organization_id`, never by vector similarity
alone.** `allowed_organization_id` is not request input taken at face
value — it is the *already-authorized* scope the caller (see
app/api/v1/retrieval.py) resolved before calling this method, exactly the
same "resolve-then-authorize-then-pass-a-trusted-value" shape used by
every other tenant-sensitive service in this codebase
(`ChunkingService`, `IngestionService`). `None` means "GLOBAL knowledge
only"; a UUID means "GLOBAL plus that one authorized organization" — see
the README for the full GLOBAL/ORGANIZATION combination rule. There is no
third mode that returns more than one organization's private knowledge in
a single call.

**Embedding model identity is pinned, not inferred.** A search always
runs within one (`provider`, `model_name`, `model_version`) — defaulting
to `get_embedding_provider()`'s identity, i.e. whatever `EMBEDDING_*` app
settings currently name — and only ever compares the query vector against
stored embeddings under that *exact* identity. Vectors from different
models are never mixed in one ORDER BY (see
`app/models/embedding.py`'s own docstring for why that would be
meaningless).

**Weak matches are not silently treated as evidence.** Below
`min_similarity` (default `settings.RETRIEVAL_MIN_SIMILARITY`), a result
is excluded entirely, not just ranked low — if nothing clears the bar,
the response's `outcome` is `NO_RELEVANT_EVIDENCE`
(`app/retrieval/results.py`), a first-class response shape, not an empty
list a caller has to infer meaning from.

**Similarity is a vector-closeness score, not a confidence or truth
signal** — see `RelevanceLevel`'s own docstring. `HIGH`/`MODERATE`/`LOW`
labels are relevance buckets over that score, never called "confidence"
anywhere in code, logs, or the API response.

**Future architecture, not built here** (see the README): this service
is deliberately shaped so a future evolution can become

    Keyword Search + Vector Search -> Fusion -> Reranking -> Evidence Selection

without changing its public contract — `search()` already returns a
ranked `RetrievalResponse`; adding a keyword-search branch and a fusion
step ahead of the final ranking is additive. No BM25/keyword search,
Elasticsearch, OpenSearch, or reranking model exists in this codebase.
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.embeddings.provider import EmbeddingProvider, get_embedding_provider
from app.models.embedding import KnowledgeChunkEmbedding
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.knowledge_source import KnowledgeSource
from app.retrieval.filters import RetrievalFilters
from app.retrieval.results import (
    RelevanceLevel,
    RetrievalOutcome,
    RetrievalResponse,
    RetrievalResult,
)

logger = logging.getLogger(__name__)


class RetrievalService:
    def search(
        self,
        db: Session,
        *,
        query_text: str,
        allowed_organization_id: uuid.UUID | None,
        filters: RetrievalFilters | None = None,
        top_k: int | None = None,
        min_similarity: float | None = None,
        provider: EmbeddingProvider | None = None,
    ) -> RetrievalResponse:
        started = time.monotonic()
        filters = filters or RetrievalFilters()
        provider = provider or get_embedding_provider()
        top_k = min(top_k or settings.RETRIEVAL_DEFAULT_TOP_K, settings.RETRIEVAL_MAX_TOP_K)
        min_similarity = (
            settings.RETRIEVAL_MIN_SIMILARITY if min_similarity is None else min_similarity
        )

        query_vector = provider.embed_text(query_text)

        distance = KnowledgeChunkEmbedding.embedding.cosine_distance(query_vector)
        similarity_expr = (1 - distance).label("similarity")
        max_distance = 1 - min_similarity

        where_clauses = self._tenant_clause(allowed_organization_id) + self._model_clause(
            provider
        ) + self._filter_clauses(filters)

        stmt = (
            select(
                KnowledgeChunk,
                KnowledgeChunkEmbedding,
                similarity_expr,
                KnowledgeDocumentVersion,
                KnowledgeDocument,
                KnowledgeSource,
            )
            .join(
                KnowledgeChunkEmbedding,
                KnowledgeChunkEmbedding.knowledge_chunk_id == KnowledgeChunk.id,
            )
            .join(
                KnowledgeDocumentVersion,
                KnowledgeChunk.document_version_id == KnowledgeDocumentVersion.id,
            )
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .join(KnowledgeSource, KnowledgeChunk.source_id == KnowledgeSource.id)
            .where(*where_clauses, distance <= max_distance)
            .order_by(distance)
            .limit(top_k)
        )

        rows = db.execute(stmt).all()

        results = [
            self._to_result(rank, chunk, embedding, similarity, version, document, source)
            for rank, (chunk, embedding, similarity, version, document, source) in enumerate(
                rows, start=1
            )
        ]

        outcome = RetrievalOutcome.RESULTS if results else RetrievalOutcome.NO_RELEVANT_EVIDENCE
        duration_ms = round((time.monotonic() - started) * 1000, 2)

        response = RetrievalResponse(
            query=query_text,
            outcome=outcome,
            embedding_provider=provider.provider_name,
            embedding_model=provider.model_name,
            embedding_model_version=provider.model_version,
            results=results,
            result_count=len(results),
            filters_applied={
                "scope": (
                    "GLOBAL"
                    if allowed_organization_id is None
                    else f"GLOBAL + ORGANIZATION:{allowed_organization_id}"
                ),
                **filters.as_dict(),
            },
            search_metadata={
                "top_k_requested": top_k,
                "min_similarity": min_similarity,
                "duration_ms": duration_ms,
            },
        )

        self._log_request(
            query_text=query_text,
            allowed_organization_id=allowed_organization_id,
            response=response,
        )
        return response

    def _tenant_clause(self, allowed_organization_id: uuid.UUID | None) -> list:
        """The one place tenant isolation is enforced for retrieval — an
        explicit predicate on the embeddings table itself, always applied,
        never optional. See this module's own docstring."""
        if allowed_organization_id is None:
            return [KnowledgeChunkEmbedding.organization_id.is_(None)]
        return [
            (
                KnowledgeChunkEmbedding.organization_id.is_(None)
                | (KnowledgeChunkEmbedding.organization_id == allowed_organization_id)
            )
        ]

    def _model_clause(self, provider: EmbeddingProvider) -> list:
        return [
            KnowledgeChunkEmbedding.provider == provider.provider_name,
            KnowledgeChunkEmbedding.model_name == provider.model_name,
            KnowledgeChunkEmbedding.model_version == provider.model_version,
        ]

    def _filter_clauses(self, filters: RetrievalFilters) -> list:
        clauses = []
        if filters.source_id is not None:
            clauses.append(KnowledgeChunk.source_id == filters.source_id)
        if filters.document_id is not None:
            clauses.append(KnowledgeChunk.document_id == filters.document_id)
        if filters.document_version_id is not None:
            clauses.append(KnowledgeChunk.document_version_id == filters.document_version_id)
        if filters.content_type is not None:
            clauses.append(KnowledgeChunk.content_type == filters.content_type)
        if filters.industry_sector is not None:
            clauses.append(KnowledgeSource.industry_sector == filters.industry_sector)
        if filters.jurisdiction is not None:
            clauses.append(KnowledgeSource.jurisdiction == filters.jurisdiction)
        if filters.verification_status is not None:
            clauses.append(KnowledgeSource.verification_status == filters.verification_status)
        if filters.effective_date_from is not None:
            clauses.append(
                KnowledgeDocumentVersion.effective_date >= filters.effective_date_from
            )
        if filters.effective_date_to is not None:
            clauses.append(KnowledgeDocumentVersion.effective_date <= filters.effective_date_to)
        return clauses

    def _to_result(
        self,
        rank: int,
        chunk: KnowledgeChunk,
        embedding: KnowledgeChunkEmbedding,
        similarity: float,
        version: KnowledgeDocumentVersion,
        document: KnowledgeDocument,
        source: KnowledgeSource,
    ) -> RetrievalResult:
        similarity = float(similarity)
        return RetrievalResult(
            rank=rank,
            chunk_id=chunk.id,
            similarity=round(similarity, 6),
            relevance=self._relevance_level(similarity),
            content=chunk.content,
            content_type=chunk.content_type,
            document_id=document.id,
            document_version_id=version.id,
            source_id=source.id,
            document_title=document.title,
            source_name=source.name,
            source_publisher=source.publisher,
            version_label=version.version_label,
            location=chunk.source_reference,
            page_number=chunk.page_number,
            sheet_name=chunk.sheet_name,
            row_number=chunk.row_number,
            slide_number=chunk.slide_number,
            section_title=chunk.section_title,
            section_path=chunk.section_path,
            extraction_quality=chunk.quality_status,
            extraction_method=chunk.extraction_method,
            source_authority_level=source.authority_level,
            verification_status=source.verification_status,
            scope="GLOBAL" if chunk.organization_id is None else "ORGANIZATION",
            organization_id=chunk.organization_id,
            jurisdiction=source.jurisdiction,
            industry_sector=source.industry_sector,
            publication_date=version.publication_date.isoformat()
            if version.publication_date
            else None,
            effective_date=version.effective_date.isoformat() if version.effective_date else None,
        )

    def _relevance_level(self, similarity: float) -> RelevanceLevel:
        if similarity >= settings.RETRIEVAL_HIGH_SIMILARITY:
            return RelevanceLevel.HIGH
        if similarity >= settings.RETRIEVAL_MODERATE_SIMILARITY:
            return RelevanceLevel.MODERATE
        return RelevanceLevel.LOW

    def _log_request(
        self,
        *,
        query_text: str,
        allowed_organization_id: uuid.UUID | None,
        response: RetrievalResponse,
    ) -> None:
        # Safe structured logging (milestone item 26): never the raw
        # query text unless a deployment explicitly opts in
        # (LOG_RETRIEVAL_QUERY_TEXT, default off — see its own docstring
        # in app/core/config.py), never a raw embedding vector, never
        # full chunk content — only shape/metadata about the request.
        logger.info(
            "retrieval_search",
            extra={
                "organization_id": str(allowed_organization_id) if allowed_organization_id else None,
                "query_length": len(query_text),
                "query_text": query_text if settings.LOG_RETRIEVAL_QUERY_TEXT else None,
                "outcome": response.outcome.value,
                "result_count": response.result_count,
                "duration_ms": response.search_metadata.get("duration_ms"),
                "embedding_model": f"{response.embedding_provider}:{response.embedding_model}:"
                f"{response.embedding_model_version}",
            },
        )


retrieval_service = RetrievalService()
