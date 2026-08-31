"""Milestone spec items 24-25: retrieval API authorization.

Authorization failures (401/403) never reach `RetrievalService.search()`
— they're rejected before any pgvector SQL runs — so those tests run on
the ordinary SQLite `client` fixture. The one success-path/tenant-
isolation-through-the-API test needs a real search to actually execute,
so it is a PostgreSQL-integration test (see tests/postgres_support.py)
that temporarily points the app's `get_db` dependency at a real
PostgreSQL + pgvector database for its duration only.
"""

import uuid

from app.core.config import settings
from app.core.database import get_db
from app.embeddings.embedding_service import embedding_service
from app.embeddings.provider import HashingEmbeddingProvider
from app.main import app
from app.models.enums import QualityStatus, ScopeType
from app.schemas.knowledge_chunk import KnowledgeChunkCreate
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.schemas.user import UserCreate
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import (
    knowledge_document_version_service,
)
from app.services.knowledge_source_service import knowledge_source_service
from app.services.user_service import user_service
from tests.conftest import dev_auth_headers
from tests.postgres_support import requires_postgres
from tests.test_ingestion_api import create_org, make_membership, make_user


def search_payload(query="What controls are required for working at height?", **overrides):
    payload = {"query": query}
    payload.update(overrides)
    return payload


# --- 24. Retrieval API authorization -------------------------------------------


def test_search_requires_authentication(client):
    response = client.post("/api/v1/knowledge/retrieval/search", json=search_payload())
    assert response.status_code == 401


def _stub_search_response(**overrides):
    from app.retrieval.results import RetrievalOutcome, RetrievalResponse

    defaults = {
        "query": "stub",
        "outcome": RetrievalOutcome.NO_RELEVANT_EVIDENCE,
        "embedding_provider": "hashing",
        "embedding_model": "sie-hashing-embedder",
        "embedding_model_version": "v1",
        "results": [],
        "result_count": 0,
        "filters_applied": {},
        "search_metadata": {},
    }
    defaults.update(overrides)
    return RetrievalResponse(**defaults)


def test_global_only_search_succeeds_for_any_authenticated_user(client, db_session, monkeypatch):
    """Global-only search requires authentication but not organization
    membership or platform-admin — see app/api/v1/retrieval.py's own
    docstring for why this deliberately departs from
    authorization_service.can()'s stricter "no org -> platform admin
    only" rule (that rule is tuned for *writing* global knowledge).

    `RetrievalService.search` itself is stubbed here (SQLite cannot run
    the real pgvector query — see this module's own docstring); the
    point of this test is that authorization lets the request *reach*
    the service at all, not the search result itself. The real 200
    happy path, with a genuine pgvector search, is
    test_search_end_to_end_over_http_returns_ranked_evidence below.
    """
    monkeypatch.setattr(
        "app.api.v1.retrieval.retrieval_service.search", lambda *a, **kw: _stub_search_response()
    )
    user = make_user(db_session, "reader@example.com")
    response = client.post(
        "/api/v1/knowledge/retrieval/search",
        json=search_payload(),
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "NO_RELEVANT_EVIDENCE"


# --- 25. Unauthorized organization access ---------------------------------------


def test_search_rejects_organization_id_the_user_has_no_membership_in(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider@example.com")

    response = client.post(
        "/api/v1/knowledge/retrieval/search",
        json=search_payload(filters={"organization_id": org["id"]}),
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_search_rejects_an_organization_the_user_belongs_to_a_different_one_of(client, db_session):
    """The core "cannot bypass authorization by passing another
    organization_id" case: the caller *is* a legitimate member of *some*
    organization, just not the one they asked to search."""
    org_a = create_org(client, name="Acme Industrial")
    org_b = create_org(client, name="Globex Corp")
    user = make_user(db_session, "member-of-a@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org_a["id"]), role="VIEWER")

    response = client.post(
        "/api/v1/knowledge/retrieval/search",
        json=search_payload(filters={"organization_id": org_b["id"]}),
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_search_allows_an_organization_the_user_is_an_active_member_of(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.retrieval.retrieval_service.search", lambda *a, **kw: _stub_search_response()
    )
    org = create_org(client)
    user = make_user(db_session, "member@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")

    response = client.post(
        "/api/v1/knowledge/retrieval/search",
        json=search_payload(filters={"organization_id": org["id"]}),
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200


# --- Full end-to-end success path (PostgreSQL) -----------------------------------


@requires_postgres
def test_search_end_to_end_over_http_returns_ranked_evidence(pg_session):
    """Overrides get_db to point the running app at a real Postgres +
    pgvector database for this one test, so the full
    request -> authorization -> RetrievalService -> pgvector round trip
    actually executes."""
    from fastapi.testclient import TestClient

    def _override():
        yield pg_session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as pg_client:
            source = knowledge_source_service.create(
                pg_session,
                obj_in=KnowledgeSourceCreate(
                    scope_type=ScopeType.GLOBAL,
                    publisher="OSHA",
                    name="Test Regs",
                    source_type="regulation",
                ),
            )
            document = knowledge_document_service.create(
                pg_session,
                obj_in=KnowledgeDocumentCreate(
                    source_id=source.id, title="Safety Manual", document_type="regulation_text"
                ),
            )
            version = knowledge_document_version_service.create(
                pg_session,
                document=document,
                obj_in=KnowledgeDocumentVersionCreate(
                    version_label="v1", content_hash="h-api-1", storage_reference="r-1"
                ),
            )
            text = "Workers must wear a full-body harness when working at height above 1.8 metres."
            (chunk,) = knowledge_chunk_service.create_many(
                pg_session,
                document_version=version,
                chunks_in=[
                    KnowledgeChunkCreate(
                        chunk_index=0,
                        content=text,
                        character_count=len(text),
                        document_id=document.id,
                        source_id=source.id,
                        quality_status=QualityStatus.HIGH,
                        source_reference="Page 1",
                    )
                ],
            )
            provider = HashingEmbeddingProvider(dimensions=settings.EMBEDDING_DIMENSIONS)
            embedding_service.embed_chunk(pg_session, chunk=chunk, provider=provider, force=True)

            user = user_service.create(
                pg_session, obj_in=UserCreate(email="api-searcher@example.com", name="Searcher")
            )

            response = pg_client.post(
                "/api/v1/knowledge/retrieval/search",
                json=search_payload(top_k=3),
                headers=dev_auth_headers(user.id),
            )

            assert response.status_code == 200
            body = response.json()
            assert body["outcome"] == "RESULTS"
            assert body["result_count"] == 1
            assert body["results"][0]["content"] == text
            assert body["results"][0]["scope"] == "GLOBAL"
            # Never a raw embedding vector in the response — only the
            # named model identity (provider/model_name/model_version).
            assert "embedding" not in body["results"][0]
            assert set(body["embedding_model"].keys()) == {"provider", "model_name", "model_version"}
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)
