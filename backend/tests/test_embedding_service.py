"""Milestone spec items 1-11 (embedding side): pgvector model
configuration, embedding creation, metadata, model/version tracking,
idempotency, duplicate prevention, coexisting model versions, empty/
INSUFFICIENT-quality chunk handling, batch embedding, and failure
handling.

Unit tests against the SQLite test database (see tests/conftest.py) —
`KnowledgeChunkEmbedding` round-trips a Python `list[float]` through
pgvector's SQLAlchemy `Vector` type on SQLite too (verified directly;
only the PostgreSQL-only `<=>`/`.cosine_distance()` *search* operators
require a real server — see tests/test_retrieval_service.py and
tests/postgres_support.py for those).
"""

import uuid

from app.embeddings.embedding_service import EmbeddingOutcomeStatus, embedding_service
from app.embeddings.provider import HashingEmbeddingProvider
from app.models.embedding import KnowledgeChunkEmbedding
from app.models.enums import QualityStatus, ScopeType
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


def make_chunks(db_session, *, texts_and_quality, organization_id=None):
    scope = ScopeType.ORGANIZATION if organization_id else ScopeType.GLOBAL
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=scope,
            organization_id=organization_id,
            publisher="OSHA",
            name=f"Test Source {uuid.uuid4()}",
            source_type="regulation",
        ),
    )
    document = knowledge_document_service.create(
        db_session,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id, title="Doc", document_type="regulation_text"
        ),
    )
    version = knowledge_document_version_service.create(
        db_session,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1",
            content_hash=f"hash-{uuid.uuid4()}",
            storage_reference="ref",
        ),
    )
    chunks_in = [
        KnowledgeChunkCreate(
            chunk_index=i,
            content=text,
            character_count=len(text),
            document_id=document.id,
            source_id=source.id,
            organization_id=organization_id,
            quality_status=quality,
        )
        for i, (text, quality) in enumerate(texts_and_quality)
    ]
    return knowledge_chunk_service.create_many(db_session, document_version=version, chunks_in=chunks_in)


# --- 1. pgvector model configuration -----------------------------------------


def test_embedding_column_dimension_matches_central_setting(db_session):
    from app.core.config import settings

    (chunk,) = make_chunks(db_session, texts_and_quality=[("Safety text.", QualityStatus.HIGH)])
    provider = HashingEmbeddingProvider(dimensions=settings.EMBEDDING_DIMENSIONS)
    outcome = embedding_service.embed_chunk(db_session, chunk=chunk, provider=provider)
    assert len(outcome.embedding.embedding) == settings.EMBEDDING_DIMENSIONS
    assert outcome.embedding.dimensions == settings.EMBEDDING_DIMENSIONS


# --- 2/3. Embedding creation & metadata --------------------------------------


def test_embedding_creation_records_full_metadata(db_session):
    (chunk,) = make_chunks(
        db_session, texts_and_quality=[("Fall protection is required at height.", QualityStatus.HIGH)]
    )
    provider = HashingEmbeddingProvider(model_name="test-model", model_version="v1", dimensions=32)

    outcome = embedding_service.embed_chunk(db_session, chunk=chunk, provider=provider)

    assert outcome.status == EmbeddingOutcomeStatus.CREATED
    record = outcome.embedding
    assert record.knowledge_chunk_id == chunk.id
    assert record.organization_id == chunk.organization_id
    assert record.provider == "hashing"
    assert record.model_name == "test-model"
    assert record.model_version == "v1"
    assert record.dimensions == 32
    assert record.content_hash  # sha256 hex string, non-empty
    assert record.created_at is not None


def test_embedding_never_modifies_the_source_chunk(db_session):
    (chunk,) = make_chunks(
        db_session, texts_and_quality=[("Original chunk content.", QualityStatus.HIGH)]
    )
    original_content = chunk.content
    embedding_service.embed_chunk(db_session, chunk=chunk, provider=HashingEmbeddingProvider(dimensions=16))
    assert chunk.content == original_content


# --- 4/7. Model/version tracking; coexisting model versions -----------------


def test_different_model_versions_coexist_for_the_same_chunk(db_session):
    (chunk,) = make_chunks(db_session, texts_and_quality=[("PPE is required on site.", QualityStatus.HIGH)])
    v1 = HashingEmbeddingProvider(model_name="sie-hashing-embedder", model_version="v1", dimensions=16)
    v2 = HashingEmbeddingProvider(model_name="sie-hashing-embedder", model_version="v2", dimensions=16)

    out1 = embedding_service.embed_chunk(db_session, chunk=chunk, provider=v1)
    out2 = embedding_service.embed_chunk(db_session, chunk=chunk, provider=v2)

    assert out1.status == EmbeddingOutcomeStatus.CREATED
    assert out2.status == EmbeddingOutcomeStatus.CREATED
    assert out1.embedding.id != out2.embedding.id

    rows = (
        db_session.query(KnowledgeChunkEmbedding)
        .filter(KnowledgeChunkEmbedding.knowledge_chunk_id == chunk.id)
        .all()
    )
    assert len(rows) == 2
    assert {r.model_version for r in rows} == {"v1", "v2"}
    # Neither row overwrote the other — both remain independently queryable.


def test_different_providers_coexist_for_the_same_chunk(db_session):
    (chunk,) = make_chunks(db_session, texts_and_quality=[("Confined space entry.", QualityStatus.HIGH)])
    a = HashingEmbeddingProvider(model_name="model-a", model_version="v1", dimensions=16)
    b = HashingEmbeddingProvider(model_name="model-b", model_version="v1", dimensions=16)

    embedding_service.embed_chunk(db_session, chunk=chunk, provider=a)
    embedding_service.embed_chunk(db_session, chunk=chunk, provider=b)

    rows = (
        db_session.query(KnowledgeChunkEmbedding)
        .filter(KnowledgeChunkEmbedding.knowledge_chunk_id == chunk.id)
        .all()
    )
    assert {r.model_name for r in rows} == {"model-a", "model-b"}


# --- 5/6. Idempotency & duplicate prevention ---------------------------------


def test_reembedding_the_same_chunk_and_model_is_idempotent(db_session):
    (chunk,) = make_chunks(db_session, texts_and_quality=[("Emergency evacuation route.", QualityStatus.HIGH)])
    provider = HashingEmbeddingProvider(dimensions=16)

    first = embedding_service.embed_chunk(db_session, chunk=chunk, provider=provider)
    second = embedding_service.embed_chunk(db_session, chunk=chunk, provider=provider)

    assert first.status == EmbeddingOutcomeStatus.CREATED
    assert second.status == EmbeddingOutcomeStatus.SKIPPED_EXISTING
    assert second.embedding.id == first.embedding.id

    rows = (
        db_session.query(KnowledgeChunkEmbedding)
        .filter(KnowledgeChunkEmbedding.knowledge_chunk_id == chunk.id)
        .all()
    )
    assert len(rows) == 1  # never duplicated


def test_stale_content_hash_is_not_silently_overwritten(db_session):
    """Simulates the (should-never-happen, chunks are immutable) case of
    a chunk's content changing after it was already embedded — the
    milestone's own "do not overwrite historical embeddings blindly"."""
    (chunk,) = make_chunks(db_session, texts_and_quality=[("Original text.", QualityStatus.HIGH)])
    provider = HashingEmbeddingProvider(dimensions=16)
    first = embedding_service.embed_chunk(db_session, chunk=chunk, provider=provider)

    chunk.content = "Changed text that no longer matches the stored embedding."
    db_session.add(chunk)
    db_session.commit()

    outcome = embedding_service.embed_chunk(db_session, chunk=chunk, provider=provider)
    assert outcome.status == EmbeddingOutcomeStatus.SKIPPED_STALE_CONTENT_HASH
    assert outcome.embedding.id == first.embedding.id  # untouched

    forced = embedding_service.embed_chunk(db_session, chunk=chunk, provider=provider, force=True)
    assert forced.status == EmbeddingOutcomeStatus.CREATED
    assert forced.embedding.id == first.embedding.id  # same row, updated in place


# --- 8/9. Empty content & INSUFFICIENT-quality handling ----------------------


def test_empty_content_chunk_is_never_embedded(db_session):
    (chunk,) = make_chunks(db_session, texts_and_quality=[("", QualityStatus.INSUFFICIENT)])
    outcome = embedding_service.embed_chunk(db_session, chunk=chunk, provider=HashingEmbeddingProvider(dimensions=16))
    assert outcome.status == EmbeddingOutcomeStatus.SKIPPED_EMPTY_CONTENT
    assert outcome.embedding is None


def test_insufficient_quality_chunk_is_skipped_by_default(db_session):
    (chunk,) = make_chunks(
        db_session, texts_and_quality=[("Some text that extracted poorly.", QualityStatus.INSUFFICIENT)]
    )
    outcome = embedding_service.embed_chunk(db_session, chunk=chunk, provider=HashingEmbeddingProvider(dimensions=16))
    assert outcome.status == EmbeddingOutcomeStatus.SKIPPED_INSUFFICIENT_QUALITY
    assert outcome.embedding is None


def test_insufficient_quality_chunk_can_be_embedded_via_explicit_config(db_session, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.EMBED_INSUFFICIENT_QUALITY_CHUNKS", True)
    (chunk,) = make_chunks(
        db_session, texts_and_quality=[("Some text that extracted poorly.", QualityStatus.INSUFFICIENT)]
    )
    outcome = embedding_service.embed_chunk(db_session, chunk=chunk, provider=HashingEmbeddingProvider(dimensions=16))
    assert outcome.status == EmbeddingOutcomeStatus.CREATED


def test_insufficient_quality_chunk_can_be_embedded_via_force(db_session):
    (chunk,) = make_chunks(
        db_session, texts_and_quality=[("Some text that extracted poorly.", QualityStatus.INSUFFICIENT)]
    )
    outcome = embedding_service.embed_chunk(
        db_session, chunk=chunk, provider=HashingEmbeddingProvider(dimensions=16), force=True
    )
    assert outcome.status == EmbeddingOutcomeStatus.CREATED


# --- 10. Batch embedding ------------------------------------------------------


def test_batch_embedding_embeds_every_chunk_in_a_version(db_session):
    chunks = make_chunks(
        db_session,
        texts_and_quality=[
            ("Working at height requires a harness.", QualityStatus.HIGH),
            ("Lifting operations require a lift plan.", QualityStatus.HIGH),
            ("", QualityStatus.INSUFFICIENT),
        ],
    )
    version_id = chunks[0].document_version_id

    report = embedding_service.generate_embeddings_for_version(
        db_session, version_id=version_id, provider=HashingEmbeddingProvider(dimensions=16)
    )

    assert report.total == 3
    assert report.created == 2
    assert report.skipped == 1
    assert report.failed == 0


def test_batch_embedding_is_idempotent_on_rerun(db_session):
    chunks = make_chunks(
        db_session,
        texts_and_quality=[
            ("Working at height requires a harness.", QualityStatus.HIGH),
            ("Lifting operations require a lift plan.", QualityStatus.HIGH),
        ],
    )
    version_id = chunks[0].document_version_id
    provider = HashingEmbeddingProvider(dimensions=16)

    first = embedding_service.generate_embeddings_for_version(db_session, version_id=version_id, provider=provider)
    second = embedding_service.generate_embeddings_for_version(db_session, version_id=version_id, provider=provider)

    assert first.created == 2
    assert second.created == 0
    assert second.skipped == 2

    rows = (
        db_session.query(KnowledgeChunkEmbedding)
        .filter(KnowledgeChunkEmbedding.knowledge_chunk_id.in_([c.id for c in chunks]))
        .all()
    )
    assert len(rows) == 2  # no duplicates from re-running the batch


# --- 11. Failed embedding handling --------------------------------------------


def test_provider_failure_is_reported_not_raised(db_session):
    (chunk,) = make_chunks(db_session, texts_and_quality=[("Some text.", QualityStatus.HIGH)])

    class BrokenProvider:
        provider_name = "broken"
        model_name = "broken-model"
        model_version = "v1"
        dimensions = 16

        def embed_text(self, text):
            raise RuntimeError("simulated embedding provider failure")

        def embed_texts(self, texts):
            return [self.embed_text(t) for t in texts]

    outcome = embedding_service.embed_chunk(db_session, chunk=chunk, provider=BrokenProvider())

    assert outcome.status == EmbeddingOutcomeStatus.FAILED
    assert "simulated embedding provider failure" in outcome.reason


def test_batch_embedding_continues_past_a_single_chunk_failure(db_session):
    chunks = make_chunks(
        db_session,
        texts_and_quality=[
            ("Good chunk one.", QualityStatus.HIGH),
            ("BOOM", QualityStatus.HIGH),
            ("Good chunk two.", QualityStatus.HIGH),
        ],
    )
    version_id = chunks[0].document_version_id

    class SometimesBrokenProvider:
        provider_name = "sometimes-broken"
        model_name = "m"
        model_version = "v1"
        dimensions = 8

        def embed_text(self, text):
            if text == "BOOM":
                raise RuntimeError("simulated failure")
            return [0.1] * 8

        def embed_texts(self, texts):
            return [self.embed_text(t) for t in texts]

    report = embedding_service.generate_embeddings_for_version(
        db_session, version_id=version_id, provider=SometimesBrokenProvider()
    )

    assert report.total == 3
    assert report.created == 2
    assert report.failed == 1
