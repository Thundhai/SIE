"""Roadmap Phase 2, item 4: `POST /api/v1/knowledge/rag/query` wired to
Commercial Core's RAG through `CommercialCoreClient.query_rag()`, against
`sie_contract.RAGAnswerDTO` (contract 0.8.0).

Mirrors `tests/test_intelligence_decisions_api.py`: a fake client is
monkeypatched over `app.api.v1.rag.get_commercial_core_client`, so these
tests exercise this route's own authorization, tenant resolution, request
checks, outcome mapping and error mapping, never a live Commercial Core.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sie_contract import AsOfWindow, CitationReferenceDTO, RAGAnswerDTO, RAGOutcome

from app.integrations.commercial_core import (
    CommercialCoreAuthenticationError,
    CommercialCoreAuthorizationError,
    CommercialCoreCapabilityDisabledError,
    CommercialCoreConnectionError,
    CommercialCoreDependencyUnavailableError,
    CommercialCoreMalformedResponseError,
    CommercialCoreTimeoutError,
    CommercialCoreUnexpectedStatusError,
    CommercialCoreValidationError,
)
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_authorized_user, make_org
from tests.test_ingestion_api import make_user
from tests.test_intelligence_api import _bearer, _make_client_credential

_URL = "/api/v1/knowledge/rag/query"
_QUERY = "What PPE is required for confined-space entry?"

_PRIVATE_FIELDS = (
    "similarity",
    "source_authority_level",
    "extraction_quality",
    "evidence_state",
    "evidence_count",
    "warnings",
    "abstention_reason",
    "retrieval_metadata",
    "model_metadata",
    "prompt_version",
    "reproducibility",
    "chunk_id",
    "conflicts",
)


class _FakeRAGClient:
    def __init__(self, *, result: RAGAnswerDTO | None = None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.calls: list[dict] = []

    def unavailable(self, capability: str):
        raise NotImplementedError

    def query_rag(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


def _citation(citation_id="E1", source="29 CFR 1910") -> CitationReferenceDTO:
    return CitationReferenceDTO(
        citation_id=citation_id,
        document_id=uuid.uuid4(),
        source=source,
        document="Permit-required confined spaces",
        version="2024",
        location="1910.146(d)",
    )


def _dto(organization_id, **overrides) -> RAGAnswerDTO:
    now = datetime.now(timezone.utc)
    fields = dict(
        organization_id=organization_id,
        query=_QUERY,
        outcome=RAGOutcome.ANSWERED,
        answer="A supplied-air respirator is required [E1].",
        explanation=None,
        citations=[_citation()],
        as_of=AsOfWindow(as_of=now, generated_at=now),
    )
    fields.update(overrides)
    return RAGAnswerDTO(**fields)


def _body(organization_id=None, **overrides) -> dict:
    body = {"query": _QUERY, "filters": {}}
    if organization_id is not None:
        body["filters"]["organization_id"] = str(organization_id)
    body.update(overrides)
    return body


def _install(monkeypatch, fake: _FakeRAGClient) -> _FakeRAGClient:
    monkeypatch.setattr("app.api.v1.rag.get_commercial_core_client", lambda: fake)
    return fake


@pytest.fixture
def member(db_session):
    org = make_org(db_session, "RAG Org")
    return org, make_authorized_user(db_session, org.id)


# --- Not configured: the existing 501 -----------------------------------------------------------


def test_is_501_when_commercial_core_is_not_configured(client, member):
    org, user = member
    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))
    assert response.status_code == 501


def test_a_global_only_query_is_501_and_never_reaches_commercial_core(client, member, monkeypatch):
    _, user = member
    fake = _install(monkeypatch, _FakeRAGClient(result=None))
    response = client.post(_URL, json=_body(), headers=dev_auth_headers(user.id))
    assert response.status_code == 501
    assert response.json()["error"]["details"]["reason"] == "GLOBAL_QUERY_NOT_SUPPORTED"
    assert fake.calls == []


# --- Authentication / authorization / tenant isolation ------------------------------------------


def test_requires_authentication(client):
    response = client.post(_URL, json=_body(uuid.uuid4()))
    assert response.status_code == 401


def test_a_member_of_another_organization_is_403_and_commercial_core_is_never_called(client, db_session, monkeypatch):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    member_a = make_authorized_user(db_session, org_a.id)
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org_b.id)))

    response = client.post(_URL, json=_body(org_b.id), headers=dev_auth_headers(member_a.id))

    assert response.status_code == 403
    assert fake.calls == []


def test_a_user_with_no_membership_is_403(client, db_session, monkeypatch):
    org = make_org(db_session, "Org")
    outsider = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(outsider.id))
    assert response.status_code == 403
    assert fake.calls == []


def test_a_machine_credential_without_knowledge_read_is_403(client, db_session, monkeypatch):
    org = make_org(db_session, "Org")
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.SAFETY_DATA_WRITE])
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    response = client.post(_URL, json=_body(org.id), headers=_bearer(credential))
    assert response.status_code == 403
    assert fake.calls == []


def test_a_machine_credential_cannot_query_another_organization(client, db_session, monkeypatch):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential = _make_client_credential(db_session, org_a.id, scopes=[Permission.KNOWLEDGE_READ])
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org_b.id)))
    response = client.post(_URL, json=_body(org_b.id), headers=_bearer(credential))
    assert response.status_code == 403
    assert fake.calls == []


def test_a_machine_credential_queries_its_own_organization(client, db_session, monkeypatch):
    org = make_org(db_session, "Org")
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.KNOWLEDGE_READ])
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    response = client.post(_URL, json=_body(org.id), headers=_bearer(credential))
    assert response.status_code == 200
    assert fake.calls[0]["organization_id"] == org.id


def test_the_client_gets_the_authorized_organization_and_only_query_and_top_k(client, member, monkeypatch):
    org, user = member
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    response = client.post(_URL, json=_body(org.id, top_k=7), headers=dev_auth_headers(user.id))
    assert response.status_code == 200
    call = fake.calls[0]
    assert set(call) == {"organization_id", "query", "top_k", "request_id"}
    assert call["organization_id"] == org.id
    assert call["query"] == _QUERY
    assert call["top_k"] == 7


# --- Request checks the boundary cannot honour yet ----------------------------------------------


@pytest.mark.parametrize(
    "extra_filter",
    [
        {"source_id": str(uuid.uuid4())},
        {"jurisdiction": "US-CA"},
        {"effective_date_from": "2024-01-01"},
    ],
)
def test_a_retrieval_filter_is_rejected_rather_than_silently_dropped(client, member, monkeypatch, extra_filter):
    org, user = member
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    body = _body(org.id)
    body["filters"].update(extra_filter)
    response = client.post(_URL, json=body, headers=dev_auth_headers(user.id))
    assert response.status_code == 422
    assert response.json()["error"]["details"]["unsupported_filters"] == list(extra_filter)
    assert fake.calls == []


def test_top_k_above_commercial_cores_limit_is_rejected(client, member, monkeypatch):
    org, user = member
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    response = client.post(_URL, json=_body(org.id, top_k=21), headers=dev_auth_headers(user.id))
    assert response.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize("query", ["   ", "\n\t "])
def test_a_whitespace_only_query_is_rejected(client, member, monkeypatch, query):
    """Commercial Core rejects it too (PR #19), but it must never reach the
    boundary: an embedding provider raises on blank text."""
    org, user = member
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    response = client.post(_URL, json=_body(org.id, query=query), headers=dev_auth_headers(user.id))
    assert response.status_code == 422
    assert fake.calls == []


def test_surrounding_whitespace_on_a_real_question_is_accepted_unchanged(client, member, monkeypatch):
    org, user = member
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    response = client.post(_URL, json=_body(org.id, query="  What PPE?  "), headers=dev_auth_headers(user.id))
    assert response.status_code == 200
    assert fake.calls[0]["query"] == "  What PPE?  "


def test_an_empty_query_is_rejected(client, member, monkeypatch):
    org, user = member
    fake = _install(monkeypatch, _FakeRAGClient(result=_dto(org.id)))
    response = client.post(_URL, json=_body(org.id, query=""), headers=dev_auth_headers(user.id))
    assert response.status_code == 422
    assert fake.calls == []


# --- Outcomes: every one is a 200, none is turned into an answer --------------------------------


def test_an_answered_query_returns_the_answer_and_citation_identity_only(client, member, monkeypatch):
    org, user = member
    dto = _dto(org.id)
    _install(monkeypatch, _FakeRAGClient(result=dto))

    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "ANSWERED"
    assert body["answer"] == dto.answer
    assert body["explanation"] is None
    assert body["organization_id"] == str(org.id)
    assert body["citations"] == [
        {
            "citation_id": "E1",
            "document_id": str(dto.citations[0].document_id),
            "source": "29 CFR 1910",
            "document": "Permit-required confined spaces",
            "version": "2024",
            "location": "1910.146(d)",
        }
    ]
    assert set(body) == {"organization_id", "query", "outcome", "answer", "explanation", "citations", "as_of", "generated_at"}
    for field in _PRIVATE_FIELDS:
        assert field not in body
        assert field not in body["citations"][0]


def test_insufficient_evidence_carries_no_answer(client, member, monkeypatch):
    org, user = member
    explanation = "SIE did not find enough supporting evidence in its knowledge base to answer this question."
    _install(
        monkeypatch,
        _FakeRAGClient(
            result=_dto(org.id, outcome=RAGOutcome.INSUFFICIENT_EVIDENCE, answer=None, explanation=explanation, citations=[])
        ),
    )
    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert body["answer"] is None
    assert body["explanation"] == explanation
    assert body["citations"] == []


def test_a_source_conflict_keeps_both_sources_and_never_picks_one(client, member, monkeypatch):
    org, user = member
    description = "E1 requires a supplied-air respirator; E2 allows an air-purifying respirator."
    _install(
        monkeypatch,
        _FakeRAGClient(
            result=_dto(
                org.id,
                outcome=RAGOutcome.SOURCE_CONFLICT,
                answer=description,
                explanation="The available sources disagree, so SIE will not pick one.",
                citations=[_citation("E1"), _citation("E2", source="Company SOP 12")],
            )
        ),
    )
    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "SOURCE_CONFLICT"
    assert body["answer"] == description
    assert body["explanation"]
    assert [c["citation_id"] for c in body["citations"]] == ["E1", "E2"]
    assert "conflicts" not in body


@pytest.mark.parametrize(
    "outcome",
    [RAGOutcome.UNSUPPORTED_CLAIM_REJECTED, RAGOutcome.PROVIDER_FAILURE, RAGOutcome.PRIVACY_BLOCKED],
)
def test_other_abstentions_are_reported_as_themselves(client, member, monkeypatch, outcome):
    org, user = member
    _install(monkeypatch, _FakeRAGClient(result=_dto(org.id, outcome=outcome, answer=None, explanation="Why.", citations=[])))
    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))
    assert response.status_code == 200
    assert response.json()["outcome"] == outcome.value
    assert response.json()["answer"] is None


# --- Dependency failures and malformed upstream responses ---------------------------------------


def test_rag_switched_off_on_commercial_core_is_503_not_enabled(client, member, monkeypatch):
    org, user = member
    _install(monkeypatch, _FakeRAGClient(error=CommercialCoreCapabilityDisabledError("x")))
    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "MODEL_NOT_AVAILABLE"
    assert error["details"] == {"reason": "RAG_NOT_ENABLED", "retryable": False}


@pytest.mark.parametrize(
    "error",
    [
        CommercialCoreAuthenticationError("Commercial Core rejected this deployment's own service credential."),
        CommercialCoreAuthorizationError("Commercial Core rejected this request's tenant binding."),
        CommercialCoreDependencyUnavailableError("A Commercial Core dependency is currently unavailable."),
        CommercialCoreTimeoutError("Commercial Core did not respond in time."),
        CommercialCoreConnectionError("Could not reach Commercial Core."),
        CommercialCoreMalformedResponseError("Commercial Core returned a successful response that does not match the expected contract shape."),
        CommercialCoreUnexpectedStatusError("Commercial Core returned an unexpected HTTP status (500)."),
    ],
)
def test_integration_failures_are_503_with_the_clients_fixed_message(client, member, monkeypatch, error):
    org, user = member
    _install(monkeypatch, _FakeRAGClient(error=error))
    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))
    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "MODEL_NOT_AVAILABLE"
    assert body["message"] == str(error)
    assert body["details"] == {"retryable": True}


def test_commercial_core_validation_rejection_is_422(client, member, monkeypatch):
    org, user = member
    _install(monkeypatch, _FakeRAGClient(error=CommercialCoreValidationError("Commercial Core rejected the request as invalid.")))
    response = client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))
    assert response.status_code == 422


def test_an_unexpected_exception_does_not_leak_its_text(client, member, monkeypatch):
    org, user = member
    secret = "provider=acme-llm detail=must-never-leak"
    from fastapi.testclient import TestClient

    from app.main import app

    # `client` (the fixture) re-raises server exceptions; this one renders the 500 the way production does.
    with TestClient(app, raise_server_exceptions=False) as raw_client:
        monkeypatch.setattr("app.api.v1.rag.get_commercial_core_client", lambda: _FakeRAGClient(error=RuntimeError(secret)))
        response = raw_client.post(_URL, json=_body(org.id), headers=dev_auth_headers(user.id))
    assert response.status_code == 500
    assert secret not in response.text
