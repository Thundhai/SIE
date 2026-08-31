"""Recall@K evaluation harness — "Prototype retrieval evaluation" per the
milestone spec (items 20-21). Not a production benchmark: a small,
synthetic, regression-catching check, run against a real PostgreSQL +
pgvector database (see tests/postgres_support.py).

    seed_evaluation_corpus() -> real KnowledgeChunk + KnowledgeChunkEmbedding rows
        -> run_recall_at_k() -> RecallReport (Recall@1 / Recall@3 / Recall@5)

Every number this harness produces is calculated from
tests/fixtures/evaluation/{corpus,queries}.py through the actual
production `EmbeddingService`/`RetrievalService` code path — never
fabricated or extrapolated. See `RecallReport.label` for the exact
wording used anywhere this result is surfaced (README, final report):
always "Prototype evaluation result on synthetic fixture dataset", never
a claim about production or enterprise performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.embeddings.embedding_service import embedding_service
from app.embeddings.provider import EmbeddingProvider, get_embedding_provider
from app.models.enums import QualityStatus, ScopeType
from app.retrieval.retrieval_service import retrieval_service
from app.schemas.knowledge_chunk import KnowledgeChunkCreate
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import (
    knowledge_document_version_service,
)
from app.services.knowledge_source_service import knowledge_source_service
from tests.fixtures.evaluation.corpus import CORPUS
from tests.fixtures.evaluation.queries import QUERIES

LABEL = "Prototype retrieval evaluation result on synthetic fixture dataset — not a production benchmark."


def seed_evaluation_corpus(db: Session, *, provider: EmbeddingProvider | None = None) -> None:
    """Load tests/fixtures/evaluation/corpus.py into the database as real
    KnowledgeChunk rows (one GLOBAL source/document/version), and embed
    every one of them — through the same production
    KnowledgeChunkService/EmbeddingService code every other chunk in this
    codebase goes through, not a separate mock path."""
    provider = provider or get_embedding_provider()

    source = knowledge_source_service.create(
        db,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="SIE Evaluation Fixtures",
            name="Synthetic Safety Corpus",
            source_type="evaluation_fixture",
        ),
    )
    document = knowledge_document_service.create(
        db,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id,
            title="Synthetic Safety Knowledge Corpus",
            document_type="evaluation_fixture",
            language="en",
        ),
    )
    version = knowledge_document_version_service.create(
        db,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1",
            content_hash="evaluation-corpus-v1",
            storage_reference="fixture://evaluation-corpus",
        ),
    )

    chunks_in = [
        KnowledgeChunkCreate(
            chunk_index=index,
            content=entry.text,
            character_count=len(entry.text),
            document_id=document.id,
            source_id=source.id,
            organization_id=None,
            section_title=entry.section_title,
            quality_status=QualityStatus.HIGH,
            chunk_metadata={"eval_topic": entry.topic},
        )
        for index, entry in enumerate(CORPUS)
    ]
    chunks = knowledge_chunk_service.create_many(db, document_version=version, chunks_in=chunks_in)

    for chunk in chunks:
        outcome = embedding_service.embed_chunk(db, chunk=chunk, provider=provider)
        if outcome.status.value not in ("created", "skipped_existing"):
            raise RuntimeError(
                f"Failed to embed evaluation corpus chunk {chunk.id}: "
                f"{outcome.status.value} ({outcome.reason})"
            )


@dataclass
class RecallReport:
    ks: list[int]
    recall_at_k: dict[int, float]
    per_query: list[dict] = field(default_factory=list)
    label: str = LABEL

    def summary(self) -> str:
        parts = ", ".join(f"Recall@{k}={self.recall_at_k[k]:.2f}" for k in self.ks)
        return f"{self.label} {parts} (n={len(self.per_query)} queries)"


def run_recall_at_k(
    db: Session,
    *,
    ks: list[int] | None = None,
    provider: EmbeddingProvider | None = None,
) -> RecallReport:
    """For each query in tests/fixtures/evaluation/queries.py, retrieve
    top-max(ks) results and check whether a chunk from the query's
    expected topic appears within the top-k, for each k in `ks`. Recall@K
    here is per-query binary hit/miss averaged over all queries (the
    standard definition when each query has one relevant topic, not a
    ranked set of multiple graded-relevance documents)."""
    ks = sorted(ks or [1, 3, 5])
    provider = provider or get_embedding_provider()
    max_k = max(ks)

    hits_at_k: dict[int, int] = {k: 0 for k in ks}
    per_query: list[dict] = []

    for eval_query in QUERIES:
        response = retrieval_service.search(
            db,
            query_text=eval_query.query,
            allowed_organization_id=None,
            top_k=max_k,
            # No similarity floor for the evaluation itself — recall
            # should reflect ranking quality, not be conflated with the
            # separate min-similarity-threshold behavior (that behavior
            # has its own dedicated tests — see
            # tests/test_retrieval_service.py).
            min_similarity=-1.0,
            provider=provider,
        )
        ranked_topics = [_topic_of(db, r.chunk_id) for r in response.results]

        first_hit_rank = next(
            (rank for rank, topic in zip((r.rank for r in response.results), ranked_topics)
             if topic == eval_query.expected_topic),
            None,
        )
        for k in ks:
            if first_hit_rank is not None and first_hit_rank <= k:
                hits_at_k[k] += 1

        per_query.append(
            {
                "query": eval_query.query,
                "expected_topic": eval_query.expected_topic,
                "first_hit_rank": first_hit_rank,
                "top_result_similarity": response.results[0].similarity if response.results else None,
            }
        )

    total = len(QUERIES)
    recall_at_k = {k: (hits_at_k[k] / total if total else 0.0) for k in ks}
    return RecallReport(ks=ks, recall_at_k=recall_at_k, per_query=per_query)


def _topic_of(db: Session, chunk_id) -> str | None:
    from app.models.knowledge_chunk import KnowledgeChunk

    chunk = db.get(KnowledgeChunk, chunk_id)
    if chunk is None or not chunk.chunk_metadata:
        return None
    return chunk.chunk_metadata.get("eval_topic")
