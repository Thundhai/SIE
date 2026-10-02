"""Task 01D-F2: the Public SIE -> Commercial Core Analytics HTTP client
(`app/integrations/commercial_core.py`'s `get_analytics_summary()`/
`get_analytics_trends()`/`get_analytics_signals()`).

Mirrors `tests/test_commercial_core_client.py`'s own structure and
fakes exactly (`_FakeResponse`, `monkeypatch.setattr(httpx, "post",
...)`), parametrized across the three new methods rather than
tripling every test, since all three share the identical
`_post_and_decode()` request/response mechanics.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
import sie_contract
from sie_contract import AnalyticsSignalsResultDTO, AnalyticsSummaryDTO, AnalyticsTrendDTO, ErrorResponse, KnownErrorCode

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


def _summary_body(**overrides) -> dict:
    body = {
        "organization_id": str(_ORG_ID),
        "entity_id": None,
        "as_of": _as_of_dict(),
        "event_count": 0,
        "data_sufficiency": "INSUFFICIENT_DATA",
        "indicators": [],
        "signals": [],
    }
    body.update(overrides)
    return body


def _trend_body(**overrides) -> dict:
    body = {
        "organization_id": str(_ORG_ID),
        "entity_id": None,
        "metric": "incident_count",
        "as_of": _as_of_dict(),
        "direction": "STABLE",
        "periods": [],
    }
    body.update(overrides)
    return body


def _signals_body(**overrides) -> dict:
    body = {
        "organization_id": str(_ORG_ID),
        "entity_id": None,
        "as_of": _as_of_dict(),
        "signals": [],
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


def _call_summary(client, **kwargs):
    defaults = dict(organization_id=_ORG_ID, site_id=None, as_of=None, window_days=None, request_id=None)
    defaults.update(kwargs)
    return client.get_analytics_summary(**defaults)


def _call_trends(client, **kwargs):
    defaults = dict(organization_id=_ORG_ID, metric="incident_count", site_id=None, as_of=None, window_days=None, request_id=None)
    defaults.update(kwargs)
    return client.get_analytics_trends(**defaults)


def _call_signals(client, **kwargs):
    defaults = dict(organization_id=_ORG_ID, site_id=None, as_of=None, window_days=None, request_id=None)
    defaults.update(kwargs)
    return client.get_analytics_signals(**defaults)


_CASES = [
    (_call_summary, _summary_body, AnalyticsSummaryDTO, "/internal/v1/analytics/summary", "Analytics summary"),
    (_call_trends, _trend_body, AnalyticsTrendDTO, "/internal/v1/analytics/trends", "Analytics trends"),
    (_call_signals, _signals_body, AnalyticsSignalsResultDTO, "/internal/v1/analytics/signals", "Analytics signals"),
]


# --- NotConfiguredCommercialCoreClient preserves the existing 501 fallback -----------------------


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_not_configured_client_raises_the_existing_unavailable_error(call, body_fn, dto_type, path, capability):
    client = NotConfiguredCommercialCoreClient()
    with pytest.raises(CommercialCoreUnavailable) as exc_info:
        call(client)
    assert exc_info.value.status_code == 501
    assert capability in exc_info.value.detail


# --- HttpCommercialCoreClient -- the real HTTP call -----------------------------------------------


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_successful_call_sends_the_expected_request_and_decodes_the_contract_dto(monkeypatch, call, body_fn, dto_type, path, capability):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(200, body_fn())

    client = _client(monkeypatch, fake_post)
    result = call(client, request_id="req-123")

    assert isinstance(result, dto_type)
    assert result.organization_id == _ORG_ID
    assert captured["url"] == f"https://cc.example.com{path}"
    assert captured["headers"]["Authorization"] == f"Bearer cid:{_SECRET}"
    assert captured["headers"]["X-SIE-Contract-Version"] == sie_contract.__version__
    assert captured["headers"]["X-Organization-Id"] == str(_ORG_ID)
    assert captured["headers"]["X-Request-Id"] == "req-123"
    assert "organization_id" not in captured["json"]  # sent via X-Organization-Id, never in the body


def test_trend_request_body_carries_the_metric(monkeypatch):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["json"] = json
        return _FakeResponse(200, _trend_body(metric="overdue_action_count"))

    client = _client(monkeypatch, fake_post)
    result = _call_trends(client, metric="overdue_action_count")
    assert captured["json"]["metric"] == "overdue_action_count"
    assert result.metric == "overdue_action_count"


def test_no_request_id_omits_the_header(monkeypatch):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["headers"] = headers
        return _FakeResponse(200, _summary_body())

    client = _client(monkeypatch, fake_post)
    _call_summary(client, request_id=None)
    assert "X-Request-Id" not in captured["headers"]


# --- Error mapping, parametrized across all three methods -----------------------------------------


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_authentication_failure_maps_to_a_typed_error_without_leaking_the_secret(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(401, ErrorResponse(error_code="AUTHENTICATION_FAILURE", message="x", request_id="r", retryable=False).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreAuthenticationError) as exc_info:
        call(client)
    assert _SECRET not in str(exc_info.value)


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_authorization_failure_maps_to_a_typed_error(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(403, ErrorResponse(error_code=KnownErrorCode.AUTHORIZATION_FAILURE, message="x", request_id="r", retryable=False).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreAuthorizationError):
        call(client)


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_validation_failure_maps_to_a_typed_error(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(422, ErrorResponse(error_code=KnownErrorCode.VALIDATION_ERROR, message="x", request_id="r", retryable=False).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreValidationError):
        call(client)


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_dependency_unavailable_503_maps_to_a_typed_error(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(503, ErrorResponse(error_code=KnownErrorCode.DEPENDENCY_UNAVAILABLE, message="x", request_id="r", retryable=True).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreDependencyUnavailableError):
        call(client)


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_timeout_maps_to_a_typed_error_with_severed_context(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        raise httpx.ReadTimeout("timed out")

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreTimeoutError) as exc_info:
        call(client)
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_connection_failure_maps_to_a_typed_error(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        raise httpx.ConnectError("could not connect")

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreConnectionError):
        call(client)


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_malformed_json_on_success_status_is_a_protocol_error(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(200, ValueError("not json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreMalformedResponseError):
        call(client)


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_json_failing_dto_validation_is_a_protocol_error(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(200, {"organization_id": "not-a-uuid"})

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreMalformedResponseError):
        call(client)


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_unexpected_status_maps_to_a_typed_error(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(418, {"detail": "teapot"})

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreUnexpectedStatusError):
        call(client)


@pytest.mark.parametrize("call,body_fn,dto_type,path,capability", _CASES)
def test_secret_never_appears_in_any_raised_exception_message(monkeypatch, call, body_fn, dto_type, path, capability):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(401, ErrorResponse(error_code="AUTHENTICATION_FAILURE", message="x", request_id="r", retryable=False).model_dump(mode="json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(Exception) as exc_info:
        call(client)
    assert _SECRET not in str(exc_info.value)
    assert f"cid:{_SECRET}" not in str(exc_info.value)
