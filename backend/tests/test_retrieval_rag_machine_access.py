"""Machine-client access to retrieval/RAG — Intelligence Platform
Integration & Enterprise API v0.1, items 16, 20, 38.

Mirrors `tests/test_retrieval_api.py`/`test_rag_api.py`'s own
authorization-only test shape (search/query itself stubbed — SQLite
cannot run the real pgvector query — see those modules' own docstrings):
the point here is that a machine client's `Authorization: Bearer`
credential reaches (or is correctly denied reaching) the service exactly
as a human's dev-mode header already does, never a second, different
authorization outcome.
"""

import uuid

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.intelligence_test_helpers import make_org


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _make_client_credential(db_session, org_id, *, scopes):
    return api_client_service.create(db_session, organization_id=org_id, name="Integration", scopes=scopes)


def _stub_retrieval_response(**overrides):
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


def _stub_rag_response(**overrides):
    from app.rag.results import EvidenceState, RAGOutcome, RAGResponse

    defaults = {
        "query": "stub",
        "outcome": RAGOutcome.INSUFFICIENT_EVIDENCE,
        "evidence_state": EvidenceState.INSUFFICIENT,
        "answer": None,
        "citations": [],
        "conflicts": [],
        "evidence_count": 0,
        "warnings": [],
        "abstention_reason": "stub",
        "retrieval_metadata": {},
        "model_metadata": None,
        "prompt_version": "v1",
        "reproducibility": {},
    }
    defaults.update(overrides)
    return RAGResponse(**defaults)


# --- Retrieval --------------------------------------------------------------------------


def test_machine_client_global_only_search_succeeds_with_knowledge_read_scope(client, db_session, monkeypatch):
    monkeypatch.setattr("app.api.v1.retrieval.retrieval_service.search", lambda *a, **kw: _stub_retrieval_response())
    org = make_org(db_session)
    # Unlike a human caller (authentication alone is enough for a
    # GLOBAL-only read, since a human's identity carries no fixed
    # organization to check a role against), a machine client has no
    # membership-derived role to fall back on -- only whatever scopes it
    # was explicitly granted -- so `knowledge:read` is still required
    # even for GLOBAL-only content. See `app.api.deps_context.authorize_context()`.
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.KNOWLEDGE_READ])

    response = client.post(
        "/api/v1/knowledge/retrieval/search", json={"query": "PPE requirements"}, headers=_bearer(credential)
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "NO_RELEVANT_EVIDENCE"


def test_machine_client_without_knowledge_read_scope_cannot_search_global_knowledge(client, db_session):
    """A credential provisioned for something else entirely (here,
    ingestion) must not get GLOBAL knowledge access for free just
    because no `organization_id` was named -- least privilege applies to
    GLOBAL reads too, not only organization-scoped ones."""
    org = make_org(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.SAFETY_DATA_WRITE])

    response = client.post(
        "/api/v1/knowledge/retrieval/search", json={"query": "PPE requirements"}, headers=_bearer(credential)
    )
    assert response.status_code == 403


def test_machine_client_with_knowledge_read_scope_can_search_its_own_organization(client, db_session, monkeypatch):
    monkeypatch.setattr("app.api.v1.retrieval.retrieval_service.search", lambda *a, **kw: _stub_retrieval_response())
    org = make_org(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.KNOWLEDGE_READ])

    response = client.post(
        "/api/v1/knowledge/retrieval/search",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org.id)}},
        headers=_bearer(credential),
    )
    assert response.status_code == 200


def test_machine_client_without_knowledge_read_scope_cannot_search_its_own_organization(client, db_session):
    org = make_org(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.SAFETY_DATA_WRITE])

    response = client.post(
        "/api/v1/knowledge/retrieval/search",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org.id)}},
        headers=_bearer(credential),
    )
    assert response.status_code == 403


def test_machine_client_cannot_search_a_different_organization_by_naming_it(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential = _make_client_credential(db_session, org_a.id, scopes=[Permission.KNOWLEDGE_READ])

    response = client.post(
        "/api/v1/knowledge/retrieval/search",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org_b.id)}},
        headers=_bearer(credential),
    )
    assert response.status_code == 403


def test_search_still_requires_some_authentication(client):
    response = client.post("/api/v1/knowledge/retrieval/search", json={"query": "PPE requirements"})
    assert response.status_code == 401


# --- RAG ---------------------------------------------------------------------------------


def test_machine_client_global_only_rag_query_succeeds_with_knowledge_read_scope(client, db_session, monkeypatch):
    monkeypatch.setattr("app.api.v1.rag.rag_service.query", lambda *a, **kw: _stub_rag_response())
    org = make_org(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.KNOWLEDGE_READ])

    response = client.post(
        "/api/v1/knowledge/rag/query", json={"query": "PPE requirements"}, headers=_bearer(credential)
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "INSUFFICIENT_EVIDENCE"


def test_machine_client_without_knowledge_read_scope_cannot_rag_query_global_knowledge(client, db_session):
    """Same rule as retrieval search's own GLOBAL test above -- a
    `safety_data:write`-only credential (provisioned for ingestion, not
    knowledge access) must not reach GLOBAL knowledge via RAG either."""
    org = make_org(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.SAFETY_DATA_WRITE])

    response = client.post(
        "/api/v1/knowledge/rag/query", json={"query": "PPE requirements"}, headers=_bearer(credential)
    )
    assert response.status_code == 403


def test_machine_client_without_knowledge_read_scope_cannot_rag_query_its_own_organization(client, db_session):
    org = make_org(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.SAFETY_DATA_WRITE])

    response = client.post(
        "/api/v1/knowledge/rag/query",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org.id)}},
        headers=_bearer(credential),
    )
    assert response.status_code == 403


def test_machine_client_cannot_rag_query_a_different_organization_by_naming_it(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential = _make_client_credential(db_session, org_a.id, scopes=[Permission.KNOWLEDGE_READ])

    response = client.post(
        "/api/v1/knowledge/rag/query",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org_b.id)}},
        headers=_bearer(credential),
    )
    assert response.status_code == 403


def test_rag_query_still_requires_some_authentication(client):
    response = client.post("/api/v1/knowledge/rag/query", json={"query": "PPE requirements"})
    assert response.status_code == 401


def test_wrong_organization_response_carries_the_standardized_authorization_denied_code(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential = _make_client_credential(db_session, org_a.id, scopes=[Permission.KNOWLEDGE_READ])

    response = client.post(
        "/api/v1/knowledge/rag/query",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org_b.id)}},
        headers=_bearer(credential),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "AUTHORIZATION_DENIED"
    assert body["error"]["request_id"]
    assert uuid.UUID(str(org_b.id))  # sanity: a real, valid organization id, never leaked as nonexistent
