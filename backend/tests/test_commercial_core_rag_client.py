"""Roadmap Phase 2, item 4: `HttpCommercialCoreClient.query_rag()` -- the
Public SIE -> Commercial Core RAG call, decoded against
`sie_contract.RAGAnswerDTO` (contract 0.8.0).

Mirrors `tests/test_commercial_core_client.py`: `httpx.post` is
monkeypatched, so nothing here needs a live Commercial Core. Request and
error bodies match Thundhai/SIE-Commercial-Core PR #19's
`cc_service/app.py` (`RAGQueryRequestBody`: `query`/`top_k` only, extra
fields forbidden) and `domain_service/errors.py` (RAG off -> 503,
`retryable: false`).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sie_contract import ErrorResponse, KnownErrorCode, RAGAnswerDTO, RAGOutcome

from app.integrations.commercial_core import (
    CommercialCoreAuthenticationError,
    CommercialCoreAuthorizationError,
    CommercialCoreCapabilityDisabledError,
    CommercialCoreConnectionError,
    CommercialCoreDependencyUnavailableError,
    CommercialCoreMalformedResponseError,
    CommercialCoreTimeoutError,
    CommercialCoreUnavailable,
    CommercialCoreValidationError,
    HttpCommercialCoreClient,
    NotConfiguredCommercialCoreClient,
)

_ORG_ID = uuid.uuid4()
_SECRET = "super-secret-value-must-never-leak"
_QUERY = "What PPE is required for confined-space entry at Site 7?"


def _as_of() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {"as_of": now, "generated_at": now, "window_days": None}


def _citation(**overrides) -> dict:
    body = {
        "citation_id": "E1",
        "document_id": str(uuid.uuid4()),
        "source": "29 CFR 1910",
        "document": "Permit-required confined spaces",
        "version": "2024",
        "location": "1910.146(d)",
    }
    body.update(overrides)
    return body


def _answer_body(**overrides) -> dict:
    body = {
        "organization_id": str(_ORG_ID),
        "query": _QUERY,
        "outcome": "ANSWERED",
        "answer": "A supplied-air respirator is required [E1].",
        "explanation": None,
        "citations": [_citation()],
        "as_of": _as_of(),
    }
    body.update(overrides)
    return body


def _error(status_code: int, *, error_code: str, retryable: bool, message: str = "x") -> "_FakeResponse":
    return _FakeResponse(
        status_code, ErrorResponse(error_code=error_code, message=message, request_id="r", retryable=retryable).model_dump(mode="json")
    )


class _FakeResponse:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _client(monkeypatch, post_impl) -> HttpCommercialCoreClient:
    monkeypatch.setattr(httpx, "post", post_impl)
    return HttpCommercialCoreClient(
        base_url="https://cc.example.com",
        client_id="cid",
        client_secret=_SECRET,
        timeout_seconds=2.0,
        rag_timeout_seconds=60.0,
    )


def _query(client: HttpCommercialCoreClient, **overrides):
    kwargs = dict(organization_id=_ORG_ID, query=_QUERY, top_k=5, request_id="req-1")
    kwargs.update(overrides)
    return client.query_rag(**kwargs)


def test_not_configured_client_raises_the_existing_501():
    with pytest.raises(CommercialCoreUnavailable) as excinfo:
        NotConfiguredCommercialCoreClient().query_rag(organization_id=_ORG_ID, query=_QUERY, top_k=None, request_id=None)
    assert excinfo.value.status_code == 501


def test_request_shape_carries_no_organization_in_the_body(monkeypatch):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return _FakeResponse(200, _answer_body())

    result = _query(_client(monkeypatch, fake_post))

    assert isinstance(result, RAGAnswerDTO)
    assert result.outcome is RAGOutcome.ANSWERED
    assert captured["url"] == "https://cc.example.com/internal/v1/rag/query"
    # cc_service's RAGQueryRequestBody forbids extra fields and takes the
    # organization only from its own credential's TenantContext.
    assert captured["json"] == {"query": _QUERY, "top_k": 5}
    assert captured["headers"]["X-Organization-Id"] == str(_ORG_ID)
    assert captured["headers"]["Authorization"] == f"Bearer cid:{_SECRET}"
    assert captured["headers"]["X-Request-Id"] == "req-1"
    # RAG's own budget, never the 2.0s read timeout the other methods use.
    assert captured["timeout"] == 60.0


def test_the_other_methods_keep_the_short_read_timeout(monkeypatch):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["timeout"] = timeout
        return _FakeResponse(503, ValueError("no body"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreDependencyUnavailableError):
        client.get_decision(organization_id=_ORG_ID, decision_id=uuid.uuid4(), request_id=None)
    assert captured["timeout"] == 2.0


def test_the_default_rag_timeout_outlasts_commercial_cores_own_rag_budget():
    """cc_service gives RAG 45s (CC_SERVICE_DOMAIN_CLIENT_RAG_TIMEOUT_SECONDS,
    Commercial Core PR #19). Public SIE must wait longer than that, or a slow
    but valid answer surfaces here as a retryable 503 while it is still
    being generated."""
    from app.core.config import settings
    from app.integrations.commercial_core import build_commercial_core_client

    assert settings.COMMERCIAL_CORE_RAG_TIMEOUT_SECONDS > 45.0
    built = build_commercial_core_client(base_url="https://cc.example.com", client_id="cid", client_secret=_SECRET)
    assert built._rag_timeout_seconds == settings.COMMERCIAL_CORE_RAG_TIMEOUT_SECONDS
    assert built._timeout_seconds == settings.COMMERCIAL_CORE_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "overrides",
    [
        {"outcome": "INSUFFICIENT_EVIDENCE", "answer": None, "explanation": "Not enough evidence.", "citations": []},
        {
            "outcome": "SOURCE_CONFLICT",
            "answer": "E1 and E2 disagree on the required respirator class.",
            "explanation": "The available sources disagree.",
            "citations": [_citation(), _citation(citation_id="E2", source="Company SOP 12")],
        },
        {"outcome": "UNSUPPORTED_CLAIM_REJECTED", "answer": None, "explanation": "Withheld."},
        {"outcome": "PROVIDER_FAILURE", "answer": None, "explanation": "Failed.", "citations": []},
        {"outcome": "PRIVACY_BLOCKED", "answer": None, "explanation": "Blocked.", "citations": []},
    ],
)
def test_every_non_answer_outcome_decodes(monkeypatch, overrides):
    result = _query(_client(monkeypatch, lambda *a, **k: _FakeResponse(200, _answer_body(**overrides))))
    assert result.outcome.value == overrides["outcome"]
    assert result.explanation == overrides["explanation"]


@pytest.mark.parametrize(
    "body",
    [
        _answer_body(answer=None),  # ANSWERED with no answer text
        _answer_body(answer=""),
        _answer_body(outcome="INSUFFICIENT_EVIDENCE", answer=None, explanation=None),  # no explanation
        _answer_body(outcome="INSUFFICIENT_EVIDENCE", answer="Made up.", explanation="x"),  # abstention with text
        _answer_body(outcome="NOT_A_REAL_OUTCOME"),
        _answer_body(citations=[{"citation_id": "E1"}]),
        _answer_body(citations=[]),  # an "answer" citing nothing is not evidence-grounded
        _answer_body(query="A different question?"),  # a stale or mis-correlated reply
        {"answer": "no outcome, no as_of"},
        ["not", "an", "object"],
    ],
)
def test_a_contract_violating_success_is_malformed_never_an_answer(monkeypatch, body):
    with pytest.raises(CommercialCoreMalformedResponseError):
        _query(_client(monkeypatch, lambda *a, **k: _FakeResponse(200, body)))


def test_non_json_success_is_malformed(monkeypatch):
    with pytest.raises(CommercialCoreMalformedResponseError):
        _query(_client(monkeypatch, lambda *a, **k: _FakeResponse(200, ValueError("not json"))))


def test_an_answer_for_another_organization_is_never_returned(monkeypatch):
    body = _answer_body(organization_id=str(uuid.uuid4()))
    with pytest.raises(CommercialCoreMalformedResponseError):
        _query(_client(monkeypatch, lambda *a, **k: _FakeResponse(200, body)))


def test_a_global_scoped_answer_is_never_returned_for_an_organization_query(monkeypatch):
    body = _answer_body(organization_id=None)
    with pytest.raises(CommercialCoreMalformedResponseError):
        _query(_client(monkeypatch, lambda *a, **k: _FakeResponse(200, body)))


def test_rag_switched_off_is_a_typed_capability_disabled_error(monkeypatch):
    response = _error(
        503,
        error_code=KnownErrorCode.DEPENDENCY_UNAVAILABLE,
        retryable=False,
        message="Knowledge question-answering is not available on this deployment.",
    )
    with pytest.raises(CommercialCoreCapabilityDisabledError) as excinfo:
        _query(_client(monkeypatch, lambda *a, **k: response))
    # Still a dependency-unavailable error for every existing caller.
    assert isinstance(excinfo.value, CommercialCoreDependencyUnavailableError)


def test_a_retryable_503_stays_a_plain_dependency_unavailable_error(monkeypatch):
    response = _error(503, error_code=KnownErrorCode.DEPENDENCY_UNAVAILABLE, retryable=True)
    with pytest.raises(CommercialCoreDependencyUnavailableError) as excinfo:
        _query(_client(monkeypatch, lambda *a, **k: response))
    assert not isinstance(excinfo.value, CommercialCoreCapabilityDisabledError)


def test_a_503_without_an_error_body_stays_a_plain_dependency_unavailable_error(monkeypatch):
    with pytest.raises(CommercialCoreDependencyUnavailableError) as excinfo:
        _query(_client(monkeypatch, lambda *a, **k: _FakeResponse(503, ValueError("no body"))))
    assert not isinstance(excinfo.value, CommercialCoreCapabilityDisabledError)


@pytest.mark.parametrize(
    ("status_code", "error_code", "expected"),
    [
        (401, "AUTHENTICATION_FAILURE", CommercialCoreAuthenticationError),
        (403, KnownErrorCode.AUTHORIZATION_FAILURE, CommercialCoreAuthorizationError),
        (403, KnownErrorCode.TENANT_MISMATCH, CommercialCoreAuthorizationError),
        (422, KnownErrorCode.VALIDATION_ERROR, CommercialCoreValidationError),
    ],
)
def test_error_statuses_map_to_typed_errors(monkeypatch, status_code, error_code, expected):
    response = _error(status_code, error_code=error_code, retryable=False)
    with pytest.raises(expected):
        _query(_client(monkeypatch, lambda *a, **k: response))


def test_timeout_and_connection_failures_map_to_typed_errors(monkeypatch):
    def timeout(*a, **k):
        raise httpx.ReadTimeout("slow", request=httpx.Request("POST", "https://cc.example.com"))

    def refused(*a, **k):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", "https://cc.example.com"))

    with pytest.raises(CommercialCoreTimeoutError):
        _query(_client(monkeypatch, timeout))
    with pytest.raises(CommercialCoreConnectionError):
        _query(_client(monkeypatch, refused))


def test_neither_the_secret_nor_the_query_text_appears_in_errors_or_logs(monkeypatch, caplog):
    responses = [
        _error(401, error_code="AUTHENTICATION_FAILURE", retryable=False),
        _error(503, error_code=KnownErrorCode.DEPENDENCY_UNAVAILABLE, retryable=False),
        _FakeResponse(200, _answer_body(organization_id=str(uuid.uuid4()))),
        _FakeResponse(200, {"garbage": True}),
    ]
    caplog.set_level(logging.DEBUG, logger="sie.integrations.commercial_core")
    for response in responses:
        with pytest.raises(Exception) as excinfo:
            _query(_client(monkeypatch, lambda *a, _r=response, **k: _r))
        assert _SECRET not in str(excinfo.value)
        assert _QUERY not in str(excinfo.value)
    for record in caplog.records:
        rendered = record.getMessage() + repr(record.__dict__)
        assert _SECRET not in rendered
        assert _QUERY not in rendered
