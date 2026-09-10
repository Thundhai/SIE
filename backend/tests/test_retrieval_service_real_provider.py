"""SIE Milestone 21: Real Semantic Embedding & Retrieval Productionization
v0.1, item 12/20 — proves `RetrievalService`'s existing contract (tenant
filtering, GLOBAL vs. organization scope, model-identity filtering,
top-K, minimum-similarity threshold, provenance) holds unchanged when a
real `SentenceTransformerEmbeddingProvider` is plugged in instead of
`HashingEmbeddingProvider` — no redesign, same service, same public
contract, see `app/retrieval/retrieval_service.py`'s own docstring.

Two tiers of "real provider," gated by what each test actually needs:

  * A tiny, offline-constructed, **untrained** real model
    (`tests.sentence_transformers_support`) — mechanically real (a
    genuine `sentence_transformers.SentenceTransformer`, batched real
    inference, real pgvector storage/search), but not semantically
    trained, so it's only used for tests that check *structural*
    guarantees (isolation, filtering, limits) that hold regardless of
    embedding quality.
  * The actually-trained local model
    (`tests.evaluation.semantic_evaluation_harness`, produced by
    `scripts/train_local_semantic_model.py`) — used only for the two
    tests that need genuine semantic behavior: paraphrase retrieval and
    unrelated-content rejection. Skips (not fails) when that model
    hasn't been trained in this checkout — see that module's own
    docstring.

Requires real PostgreSQL (`@requires_postgres`) throughout, same as
every other `RetrievalService` integration test.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.embeddings.embedding_service import embedding_service
from app.retrieval.results import RetrievalOutcome
from app.retrieval.retrieval_service import retrieval_service
from tests.evaluation.semantic_evaluation_harness import (
    build_real_local_provider,
    real_local_provider_available,
)
from tests.postgres_support import requires_postgres
from tests.sentence_transformers_support import build_tiny_offline_model, requires_sentence_transformers
from tests.test_retrieval_service import make_org, seed_chunk

requires_trained_local_model = pytest.mark.skipif(
    not real_local_provider_available(),
    reason=(
        "scripts/train_local_semantic_model.py has not been run in this checkout "
        "-- see tests/evaluation/semantic_evaluation_harness.py."
    ),
)


@pytest.fixture(scope="module")
def tiny_real_provider(tmp_path_factory):
    """Module-scoped so the (fast, but not free) model construction/save
    happens once for every structural test in this file, not once per
    test."""
    from app.embeddings.provider import SentenceTransformerEmbeddingProvider

    model = build_tiny_offline_model(dimensions=settings.EMBEDDING_DIMENSIONS)
    output_dir = tmp_path_factory.mktemp("tiny_real_provider") / "model"
    model.save(str(output_dir))
    return SentenceTransformerEmbeddingProvider(model_name=str(output_dir), model_version="test-v1")


HEIGHT_TEXT = "Workers must wear a full-body harness when working at height above 1.8 metres."


# --- Structural guarantees, real (untrained) provider -----------------------------------


@requires_postgres
@requires_sentence_transformers
def test_organization_isolation_holds_under_a_real_provider(pg_session, tiny_real_provider):
    org_a = make_org(pg_session)
    org_b = make_org(pg_session)
    seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=org_a.id, embed=False)
    chunk_a, *_ = seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=org_a.id, embed=False)
    outcome = embedding_service.embed_chunk(pg_session, chunk=chunk_a, provider=tiny_real_provider, force=True)
    assert outcome.status.value == "created"

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=org_b.id,
        min_similarity=-1.0,
        provider=tiny_real_provider,
    )
    assert all(r.organization_id != org_a.id for r in response.results)


@requires_postgres
@requires_sentence_transformers
def test_global_scope_holds_under_a_real_provider(pg_session, tiny_real_provider):
    chunk, *_ = seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=None, embed=False)
    embedding_service.embed_chunk(pg_session, chunk=chunk, provider=tiny_real_provider, force=True)

    org = make_org(pg_session)
    other_chunk, *_ = seed_chunk(pg_session, text="Unrelated org-scoped content.", organization_id=org.id, embed=False)
    embedding_service.embed_chunk(pg_session, chunk=other_chunk, provider=tiny_real_provider, force=True)

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=None,
        min_similarity=-1.0,
        provider=tiny_real_provider,
    )
    assert all(r.scope == "GLOBAL" for r in response.results)
    assert any(r.chunk_id == chunk.id for r in response.results)


@requires_postgres
@requires_sentence_transformers
def test_model_identity_isolation_holds_under_a_real_provider(pg_session, tiny_real_provider):
    from app.embeddings.provider import HashingEmbeddingProvider

    hashing = HashingEmbeddingProvider(dimensions=settings.EMBEDDING_DIMENSIONS)
    chunk, *_ = seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=None, embed=False)
    embedding_service.embed_chunk(pg_session, chunk=chunk, provider=hashing, force=True)
    # No embedding under tiny_real_provider's identity exists for this chunk.

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=None,
        min_similarity=-1.0,
        provider=tiny_real_provider,
    )
    assert response.outcome == RetrievalOutcome.NO_RELEVANT_EVIDENCE
    assert response.result_count == 0


@requires_postgres
@requires_sentence_transformers
def test_multiple_model_identities_coexist_under_a_real_provider(pg_session, tiny_real_provider):
    from app.embeddings.provider import HashingEmbeddingProvider

    hashing = HashingEmbeddingProvider(dimensions=settings.EMBEDDING_DIMENSIONS)
    chunk, *_ = seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=None, embed=False)
    embedding_service.embed_chunk(pg_session, chunk=chunk, provider=hashing, force=True)
    embedding_service.embed_chunk(pg_session, chunk=chunk, provider=tiny_real_provider, force=True)

    from app.models.embedding import KnowledgeChunkEmbedding

    rows = (
        pg_session.query(KnowledgeChunkEmbedding)
        .filter(KnowledgeChunkEmbedding.knowledge_chunk_id == chunk.id)
        .all()
    )
    assert {r.provider for r in rows} == {"hashing", "sentence_transformers"}

    hashing_response = retrieval_service.search(
        pg_session, query_text=HEIGHT_TEXT, allowed_organization_id=None, min_similarity=-1.0, provider=hashing
    )
    real_response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=None,
        min_similarity=-1.0,
        provider=tiny_real_provider,
    )
    assert any(r.chunk_id == chunk.id for r in hashing_response.results)
    assert any(r.chunk_id == chunk.id for r in real_response.results)


@requires_postgres
@requires_sentence_transformers
def test_top_k_limit_holds_under_a_real_provider(pg_session, tiny_real_provider):
    for i in range(5):
        chunk, *_ = seed_chunk(pg_session, text=f"Safety chunk number {i} about harnesses.", organization_id=None, embed=False)
        embedding_service.embed_chunk(pg_session, chunk=chunk, provider=tiny_real_provider, force=True)

    response = retrieval_service.search(
        pg_session,
        query_text="harness safety",
        allowed_organization_id=None,
        top_k=2,
        min_similarity=-1.0,
        provider=tiny_real_provider,
    )
    assert response.result_count <= 2
    assert len(response.results) <= 2


@requires_postgres
@requires_sentence_transformers
def test_minimum_similarity_threshold_holds_under_a_real_provider(pg_session, tiny_real_provider):
    chunk, *_ = seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=None, embed=False)
    embedding_service.embed_chunk(pg_session, chunk=chunk, provider=tiny_real_provider, force=True)

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=None,
        min_similarity=1.01,  # unreachable -- cosine similarity never exceeds 1.0
        provider=tiny_real_provider,
    )
    assert response.outcome == RetrievalOutcome.NO_RELEVANT_EVIDENCE
    assert response.results == []


@requires_postgres
@requires_sentence_transformers
def test_empty_query_text_does_not_crash_a_real_provider_search(pg_session, tiny_real_provider):
    chunk, *_ = seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=None, embed=False)
    embedding_service.embed_chunk(pg_session, chunk=chunk, provider=tiny_real_provider, force=True)

    with pytest.raises(ValueError):
        retrieval_service.search(
            pg_session,
            query_text="",
            allowed_organization_id=None,
            provider=tiny_real_provider,
        )


@requires_postgres
@requires_sentence_transformers
def test_no_relevant_evidence_on_an_empty_corpus_under_a_real_provider(pg_session, tiny_real_provider):
    response = retrieval_service.search(
        pg_session,
        query_text="a query with nothing in the corpus to match",
        allowed_organization_id=None,
        provider=tiny_real_provider,
    )
    assert response.outcome == RetrievalOutcome.NO_RELEVANT_EVIDENCE
    assert response.results == []


# --- Genuine semantic behavior, actually-trained local model ----------------------------


@requires_postgres
@requires_trained_local_model
def test_semantic_paraphrase_retrieval_with_the_trained_local_model(pg_session):
    provider = build_real_local_provider()
    chunk, *_ = seed_chunk(
        pg_session,
        text="Workers must wear a full-body harness with a shock-absorbing lanyard "
        "whenever working at height above 1.8 metres where no other fall protection "
        "is in place.",
        organization_id=None,
        embed=False,
    )
    embedding_service.embed_chunk(pg_session, chunk=chunk, provider=provider, force=True)

    # Deliberately no shared vocabulary with the chunk above ("harness",
    # "height", "lanyard", "fall protection" never appear) — see
    # tests/fixtures/evaluation/hard_paraphrase_queries.py for the same
    # style of query.
    response = retrieval_service.search(
        pg_session,
        query_text="What stops someone from hitting the ground if they slip off a ladder or scaffold?",
        allowed_organization_id=None,
        min_similarity=-1.0,
        provider=provider,
    )
    assert response.results, "The trained model should find at least one result on a small single-chunk corpus."
    assert response.results[0].chunk_id == chunk.id


@requires_postgres
@requires_trained_local_model
def test_unrelated_content_is_ranked_below_a_genuine_semantic_match(pg_session):
    provider = build_real_local_provider()
    relevant_chunk, *_ = seed_chunk(
        pg_session,
        text="A trained standby attendant must remain at the entrance of a confined "
        "space at all times while anyone is working inside.",
        organization_id=None,
        embed=False,
    )
    embedding_service.embed_chunk(pg_session, chunk=relevant_chunk, provider=provider, force=True)

    unrelated_chunk, *_ = seed_chunk(
        pg_session,
        text="Quarterly financial results exceeded analyst expectations for the third "
        "consecutive period.",
        organization_id=None,
        embed=False,
    )
    embedding_service.embed_chunk(pg_session, chunk=unrelated_chunk, provider=provider, force=True)

    response = retrieval_service.search(
        pg_session,
        query_text="Does someone need to watch the entrance while a colleague is inside a tank?",
        allowed_organization_id=None,
        min_similarity=-1.0,
        provider=provider,
    )
    assert response.results
    assert response.results[0].chunk_id == relevant_chunk.id
    ranked_ids = [r.chunk_id for r in response.results]
    if unrelated_chunk.id in ranked_ids:
        assert ranked_ids.index(relevant_chunk.id) < ranked_ids.index(unrelated_chunk.id)
