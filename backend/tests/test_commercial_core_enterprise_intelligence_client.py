"""Task 01D-F3: the Public SIE -> Commercial Core Enterprise
Intelligence HTTP client
(`app/integrations/commercial_core.py`'s `get_enterprise_intelligence()`).

Mirrors `tests/test_commercial_core_analytics_client.py`'s own
structure and fakes exactly (`_FakeResponse`,
`monkeypatch.setattr(httpx, "post", ...)`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
import sie_contract
from sie_contract import EnterpriseIntelligenceResultDTO, ErrorResponse, KnownErrorCode

from app.integrations.commercial_core import (
    CommercialCoreAuthenticationError,
    CommercialCoreAuthorizationError,
    CommercialCoreConnectionError,
    CommercialCoreDependencyUnavailableError,
    CommercialCoreMalformedResponseError,
    CommercialCoreTimeoutError,
    CommercialCoreUnavailable,
    CommercialCoreUnexpectedStatusError,
    CommercialCoreValidationError,
    HttpCommercialCoreClient,
    NotConfiguredCommercialCoreClient,
)

_ORG_ID = uuid.uuid4()
_SECRET = "super-secret-value-must-never-leak"


def _as_of_dict() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {"as_of": now, "generated_at": now, "window_days": 30}


def _result_body(**overrides) -> dict:
    now = _as_of_dict()
    body = {
        "organization_id": str(_ORG_ID),
        "scope": "organization",
        "entity_id": None,
        "as_of": now,
        "data_sufficiency": "INSUFFICIENT_DATA",
        "event_count": 0,
        "deterministic_risk": {"score": None, "classification": None, "components": [], "insufficient_data_reason": None},
        "trend": {
            "classification": "INSUFFICIENT_DATA",
            "metric": "incident_count",
            "current_value": 0,
            "previous_value": 0,
            "absolute_change": 0,
            "percentage_change": None,
            "current_period_start": now["as_of"],
            "current_period_end": now["as_of"],
            "previous_period_start": now["as_of"],
            "previous_period_end": now["as_of"],
        },
        "indicators": [],
        "patterns": [],
        "concentrations": [],
        "anomalies": [],
        "associations": [],
        "explanations": [],
        "provenance": {"window_start": now["as_of"], "window_end": now["as_of"], "event_count": 0, "total_supporting_events": 0, "evidence_sample": []},
        "actions_context": None,
    }
    body.update(overrides)
    return body


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
        base_url="https://cc.example.com", client_id="cid", client_secret=_SECRET, timeout_seconds=2.0
    )


def _call(client, **kwargs):
    defaults = dict(organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None)
    defaults.update(kwargs)
    return client.get_enterprise_intelligence(**defaults)


# --- NotConfiguredCommercialCoreClient preserves the existing 501 fallback -----------------------


def test_not_configured_client_raises_the_existing_unavailable_error():
    client = NotConfiguredCommercialCoreClient()
    with pytest.raises(CommercialCoreUnavailable) as exc_info:
        _call(client)
    assert exc_info.value.status_code == 501
    assert "Enterprise intelligence" in exc_info.value.detail


# --- HttpCommercialCoreClient -- the real HTTP call -----------------------------------------------


def test_successful_call_sends_the_expected_request_and_decodes_the_contract_dto(monkeypatch):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(200, _result_body())

    client = _client(monkeypatch, fake_post)
    result = _call(client, request_id="req-123")

    assert isinstance(result, EnterpriseIntelligenceResultDTO)
    assert result.organization_id == _ORG_ID
    assert captured["url"] == "https://cc.example.com/internal/v1/intelligence/enterprise"
    assert captured["json"]["scope"] == "organization"
    assert captured["headers"]["Authorization"] == f"Bearer cid:{_SECRET}"
    assert captured["headers"]["X-SIE-Contract-Version"] == sie_contract.__version__
    assert captured["headers"]["X-Organization-Id"] == str(_ORG_ID)
    assert captured["headers"]["X-Request-Id"] == "req-123"
    assert "organization_id" not in captured["json"]  # sent via X-Organization-Id, never in the body


def test_site_scope_carries_site_id(monkeypatch):
    site_id = uuid.uuid4()
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["json"] = json
        return _FakeResponse(200, _result_body(scope="site", entity_id=str(site_id)))

    client = _client(monkeypatch, fake_post)
    _call(client, scope="site", site_id=site_id)
    assert captured["json"]["scope"] == "site"
    assert captured["json"]["site_id"] == str(site_id)


def test_no_request_id_omits_the_header(monkeypatch):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["headers"] = headers
        return _FakeResponse(200, _result_body())

    client = _client(monkeypatch, fake_post)
    _call(client, request_id=None)
    assert "X-Request-Id" not in captured["headers"]


# --- Error mapping ----------------------------------------------------------------------------------


def test_authentication_failure_maps_to_a_typed_error_without_leaking_the_secret(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(401, ErrorResponse(error_code="AUTHENTICATION_FAILURE", message="x", request_id="r", retryable=False).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreAuthenticationError) as exc_info:
        _call(client)
    assert _SECRET not in str(exc_info.value)


def test_authorization_failure_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(403, ErrorResponse(error_code=KnownErrorCode.AUTHORIZATION_FAILURE, message="x", request_id="r", retryable=False).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreAuthorizationError):
        _call(client)


def test_validation_failure_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(422, ErrorResponse(error_code=KnownErrorCode.VALIDATION_ERROR, message="x", request_id="r", retryable=False).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreValidationError):
        _call(client)


def test_dependency_unavailable_503_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(503, ErrorResponse(error_code=KnownErrorCode.DEPENDENCY_UNAVAILABLE, message="x", request_id="r", retryable=True).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreDependencyUnavailableError):
        _call(client)


def test_timeout_maps_to_a_typed_error_with_severed_context(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        raise httpx.ReadTimeout("timed out")

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreTimeoutError) as exc_info:
        _call(client)
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None


def test_connection_failure_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        raise httpx.ConnectError("could not connect")

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreConnectionError):
        _call(client)


def test_malformed_json_on_success_status_is_a_protocol_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(200, ValueError("not json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreMalformedResponseError):
        _call(client)


def test_json_failing_dto_validation_is_a_protocol_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(200, {"organization_id": "not-a-uuid"})

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreMalformedResponseError):
        _call(client)


def test_unexpected_status_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(418, {"detail": "teapot"})

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreUnexpectedStatusError):
        _call(client)


def test_secret_never_appears_in_any_raised_exception_message(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(401, ErrorResponse(error_code="AUTHENTICATION_FAILURE", message="x", request_id="r", retryable=False).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(Exception) as exc_info:
        _call(client)
    assert _SECRET not in str(exc_info.value)
    assert f"cid:{_SECRET}" not in str(exc_info.value)
