"""Milestone spec items 12-23: tenant isolation, global/organization
knowledge behavior, metadata filtering, similarity ordering, minimum
similarity threshold, NO_RELEVANT_EVIDENCE, and provenance preservation.

PostgreSQL-integration tests (real `<=>`/`.cosine_distance()` pgvector
operators — see tests/postgres_support.py). Skipped automatically if no
real PostgreSQL + pgvector server is reachable.
"""

import uuid

from app.core.config import settings
from app.embeddings.embedding_service import embedding_service
from app.embeddings.provider import HashingEmbeddingProvider
from app.models.enums import ContentType, QualityStatus, ScopeType, VerificationStatus
from app.retrieval.filters import RetrievalFilters
from app.retrieval.results import RetrievalOutcome
from app.retrieval.retrieval_service import retrieval_service
from app.schemas.knowledge_chunk import KnowledgeChunkCreate
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.schemas.organization import OrganizationCreate
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import (
    knowledge_document_version_service,
)
from app.services.knowledge_source_service import knowledge_source_service
from app.services.organization_service import organization_service
from tests.postgres_support import requires_postgres

PROVIDER = HashingEmbeddingProvider(dimensions=settings.EMBEDDING_DIMENSIONS)


def make_org(db):
    return organization_service.create(db, obj_in=OrganizationCreate(name=f"Org {uuid.uuid4()}"))


def seed_chunk(
    db,
    *,
    text,
    organization_id=None,
    content_type=ContentType.TEXT,
    jurisdiction=None,
    industry_sector=None,
    verification_status=VerificationStatus.PENDING,
    effective_date=None,
    quality_status=QualityStatus.HIGH,
    embed=True,
):
    scope = ScopeType.ORGANIZATION if organization_id else ScopeType.GLOBAL
    source = knowledge_source_service.create(
        db,
        obj_in=KnowledgeSourceCreate(
            scope_type=scope,
            organization_id=organization_id,
            publisher="OSHA",
            name=f"Source {uuid.uuid4()}",
            source_type="regulation",
            jurisdiction=jurisdiction,
            industry_sector=industry_sector,
            verification_status=verification_status,
        ),
    )
    document = knowledge_document_service.create(
        db,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id,
            organization_id=organization_id,
            title=f"Doc {uuid.uuid4()}",
            document_type="regulation_text",
        ),
    )
    version = knowledge_document_version_service.create(
        db,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1",
            content_hash=f"hash-{uuid.uuid4()}",
            storage_reference="ref",
            effective_date=effective_date,
        ),
    )
    (chunk,) = knowledge_chunk_service.create_many(
        db,
        document_version=version,
        chunks_in=[
            KnowledgeChunkCreate(
                chunk_index=0,
                content=text,
                character_count=len(text),
                document_id=document.id,
                source_id=source.id,
                organization_id=organization_id,
                content_type=content_type,
                quality_status=quality_status,
                source_reference="Page 1",
            )
        ],
    )
    if embed:
        outcome = embedding_service.embed_chunk(db, chunk=chunk, provider=PROVIDER, force=True)
        assert outcome.status.value in ("created", "skipped_existing")
    return chunk, source, document, version


HEIGHT_TEXT = "Workers must wear a full-body harness when working at height above 1.8 metres."


# --- 12/13/14/15. Tenant isolation, global, organization, cross-org --------


@requires_postgres
def test_global_only_search_returns_global_chunks(pg_session):
    seed_chunk(pg_session, text=HEIGHT_TEXT)
    response = retrieval_service.search(
        pg_session, query_text=HEIGHT_TEXT, allowed_organization_id=None, provider=PROVIDER
    )
    assert response.outcome == RetrievalOutcome.RESULTS
    assert response.results[0].scope == "GLOBAL"


@requires_postgres
def test_global_only_search_never_returns_organization_chunks(pg_session):
    org = make_org(pg_session)
    seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=org.id)

    response = retrieval_service.search(
        pg_session, query_text=HEIGHT_TEXT, allowed_organization_id=None, provider=PROVIDER
    )
    assert response.outcome == RetrievalOutcome.NO_RELEVANT_EVIDENCE
    assert response.results == []


@requires_postgres
def test_organization_search_returns_global_plus_that_organization(pg_session):
    org = make_org(pg_session)
    seed_chunk(pg_session, text=HEIGHT_TEXT + " (global)")
    seed_chunk(pg_session, text=HEIGHT_TEXT + " (org)", organization_id=org.id)

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=org.id,
        top_k=5,
        provider=PROVIDER,
    )
    scopes = {r.scope for r in response.results}
    assert scopes == {"GLOBAL", "ORGANIZATION"}


@requires_postgres
def test_organization_a_cannot_retrieve_organization_bs_knowledge(pg_session):
    org_a = make_org(pg_session)
    org_b = make_org(pg_session)
    seed_chunk(pg_session, text=HEIGHT_TEXT, organization_id=org_b.id)

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=org_a.id,
        provider=PROVIDER,
    )

    assert response.outcome == RetrievalOutcome.NO_RELEVANT_EVIDENCE
    assert all(r.organization_id != org_b.id for r in response.results)


@requires_postgres
def test_organization_search_never_returns_a_different_organizations_chunk_even_alongside_matches(
    pg_session,
):
    org_a = make_org(pg_session)
    org_b = make_org(pg_session)
    seed_chunk(pg_session, text=HEIGHT_TEXT + " (org a)", organization_id=org_a.id)
    seed_chunk(pg_session, text=HEIGHT_TEXT + " (org b)", organization_id=org_b.id)

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=org_a.id,
        top_k=10,
        provider=PROVIDER,
    )
    assert all(r.organization_id in (None, org_a.id) for r in response.results)
    assert org_b.id not in {r.organization_id for r in response.results}


# --- 16/17/18/19. Metadata filtering ------------------------------------------


@requires_postgres
def test_content_type_filter(pg_session):
    seed_chunk(pg_session, text=HEIGHT_TEXT, content_type=ContentType.TEXT)
    seed_chunk(pg_session, text=HEIGHT_TEXT, content_type=ContentType.TABLE)

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=None,
        filters=RetrievalFilters(content_type=ContentType.TABLE),
        top_k=10,
        provider=PROVIDER,
    )
    assert response.results
    assert all(r.content_type == ContentType.TABLE for r in response.results)


@requires_postgres
def test_verification_status_filter(pg_session):
    seed_chunk(pg_session, text=HEIGHT_TEXT, verification_status=VerificationStatus.VERIFIED)
    seed_chunk(pg_session, text=HEIGHT_TEXT, verification_status=VerificationStatus.PENDING)

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=None,
        filters=RetrievalFilters(verification_status=VerificationStatus.VERIFIED),
        top_k=10,
        provider=PROVIDER,
    )
    assert response.results
    assert all(r.verification_status == VerificationStatus.VERIFIED for r in response.results)


@requires_postgres
def test_document_version_filter(pg_session):
    _, _, _, version_a = seed_chunk(pg_session, text=HEIGHT_TEXT + " a")
    seed_chunk(pg_session, text=HEIGHT_TEXT + " b")

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=None,
        filters=RetrievalFilters(document_version_id=version_a.id),
        top_k=10,
        provider=PROVIDER,
    )
    assert response.results
    assert all(r.document_version_id == version_a.id for r in response.results)


@requires_postgres
def test_jurisdiction_and_industry_sector_filters(pg_session):
    seed_chunk(pg_session, text=HEIGHT_TEXT, jurisdiction="US", industry_sector="construction")
    seed_chunk(pg_session, text=HEIGHT_TEXT, jurisdiction="UK", industry_sector="oil_and_gas")

    response = retrieval_service.search(
        pg_session,
        query_text=HEIGHT_TEXT,
        allowed_organization_id=None,
        filters=RetrievalFilters(jurisdiction="US", industry_sector="construction"),
        top_k=10,
        provider=PROVIDER,
    )
    assert response.results
    assert all(r.jurisdiction == "US" and r.industry_sector == "construction" for r in response.results)


# --- 20. Similarity score ordering ---------------------------------------------


@requires_postgres
def test_results_are_ordered_by_descending_similarity(pg_session):
    seed_chunk(pg_session, text=HEIGHT_TEXT)
    seed_chunk(pg_session, text="Fall protection equipment such as a harness is required at height.")
    seed_chunk(pg_session, text="Entry into a confined space requires atmospheric testing.")

    response = retrieval_service.search(
        pg_session,
        query_text="What controls are required for working at height?",
        allowed_organization_id=None,
        top_k=10,
        min_similarity=-1.0,
        provider=PROVIDER,
    )
    similarities = [r.similarity for r in response.results]
    assert similarities == sorted(similarities, reverse=True)
    ranks = [r.rank for r in response.results]
    assert ranks == list(range(1, len(ranks) + 1))


# --- 21/22. Minimum similarity threshold & NO_RELEVANT_EVIDENCE -------------


@requires_postgres
def test_minimum_similarity_threshold_excludes_weak_matches(pg_session):
    seed_chunk(pg_session, text=HEIGHT_TEXT)

    permissive = retrieval_service.search(
        pg_session,
        query_text="quarterly financial revenue report",
        allowed_organization_id=None,
        min_similarity=-1.0,
        provider=PROVIDER,
    )
    strict = retrieval_service.search(
        pg_session,
        query_text="quarterly financial revenue report",
        allowed_organization_id=None,
        min_similarity=0.5,
        provider=PROVIDER,
    )
    assert permissive.result_count >= 1
    assert strict.outcome == RetrievalOutcome.NO_RELEVANT_EVIDENCE
    assert strict.results == []


@requires_postgres
def test_no_relevant_evidence_when_the_corpus_is_empty(pg_session):
    response = retrieval_service.search(
        pg_session, query_text=HEIGHT_TEXT, allowed_organization_id=None, provider=PROVIDER
    )
    assert response.outcome == RetrievalOutcome.NO_RELEVANT_EVIDENCE
    assert response.result_count == 0
    assert response.results == []


# --- 23. Provenance preservation ----------------------------------------------


@requires_postgres
def test_retrieval_result_preserves_full_provenance(pg_session):
    chunk, source, document, version = seed_chunk(
        pg_session,
        text=HEIGHT_TEXT,
        jurisdiction="US",
        industry_sector="construction",
        verification_status=VerificationStatus.VERIFIED,
    )

    response = retrieval_service.search(
        pg_session, query_text=HEIGHT_TEXT, allowed_organization_id=None, provider=PROVIDER
    )
    assert response.results
    result = response.results[0]

    assert result.chunk_id == chunk.id
    assert result.document_id == document.id
    assert result.document_version_id == version.id
    assert result.source_id == source.id
    assert result.source_name == source.name
    assert result.document_title == document.title
    assert result.version_label == version.version_label
    assert result.location == "Page 1"
    assert result.extraction_quality == QualityStatus.HIGH
    assert result.verification_status == VerificationStatus.VERIFIED
    assert result.source_authority_level == source.authority_level
    assert result.jurisdiction == "US"
    assert result.industry_sector == "construction"
    assert result.scope == "GLOBAL"


# --- Embedding model identity pinning ------------------------------------------


@requires_postgres
def test_search_only_matches_embeddings_under_the_same_model_identity(pg_session):
    chunk, *_ = seed_chunk(pg_session, text=HEIGHT_TEXT, embed=False)
    other_model = HashingEmbeddingProvider(
        model_name="other-model", model_version="v1", dimensions=settings.EMBEDDING_DIMENSIONS
    )
    embedding_service.embed_chunk(pg_session, chunk=chunk, provider=other_model)

    # Searching under PROVIDER's identity finds nothing, even though the
    # chunk *is* embedded — just under a different model.
    response = retrieval_service.search(
        pg_session, query_text=HEIGHT_TEXT, allowed_organization_id=None, provider=PROVIDER
    )
    assert response.outcome == RetrievalOutcome.NO_RELEVANT_EVIDENCE

    response_other = retrieval_service.search(
        pg_session, query_text=HEIGHT_TEXT, allowed_organization_id=None, provider=other_model
    )
    assert response_other.outcome == RetrievalOutcome.RESULTS
