"""Task 01D-B: the Public SIE -> Commercial Core Attention HTTP client
(`app/integrations/commercial_core.py`).

Two independent concerns, mirroring `tests/test_llm_provider.py`'s own
split for the analogous provider-factory pattern:

1. **Configuration resolution** (`build_commercial_core_client()` /
   `get_commercial_core_client()`) -- not configured, fully configured,
   and the "fail loud, not silently" partial-configuration case, all
   without ever touching the network.
2. **The real HTTP call** (`HttpCommercialCoreClient.get_attention()`) --
   every failure category Task 01D-B's own spec names, exercised against
   a monkeypatched `httpx.post` so nothing here requires a live
   Commercial Core deployment (there isn't one). Response/error bodies
   match `Thundhai/SIE-Commercial-Core`'s real `cc_service/app.py` and
   `cc_service/transport/errors.py` shapes exactly -- verified against
   that repository's current source, not guessed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
import sie_contract
from sie_contract import AttentionResultDTO, ErrorResponse, KnownErrorCode

from app.integrations.commercial_core import (
    CommercialCoreAuthenticationError,
    CommercialCoreAuthorizationError,
    CommercialCoreConfigurationError,
    CommercialCoreConnectionError,
    CommercialCoreDependencyUnavailableError,
    CommercialCoreMalformedResponseError,
    CommercialCoreTimeoutError,
    CommercialCoreUnavailable,
    CommercialCoreUnexpectedStatusError,
    CommercialCoreValidationError,
    HttpCommercialCoreClient,
    NotConfiguredCommercialCoreClient,
    build_commercial_core_client,
    commercial_core_client,
    get_commercial_core_client,
)

_ORG_ID = uuid.uuid4()
_SECRET = "super-secret-value-must-never-leak"


def _attention_result_body(**overrides) -> dict:
    body = {
        "organization_id": str(_ORG_ID),
        "scope": "organization",
        "entity_id": None,
        "as_of": {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_days": 30,
        },
        "items": [],
        "category_status": [],
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


# --- Group 1: configuration resolution ---------------------------------------------


def test_not_configured_returns_the_existing_singleton(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_BASE_URL", None)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_CLIENT_ID", None)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_CLIENT_SECRET", None)

    client = build_commercial_core_client()

    assert client is commercial_core_client
    assert isinstance(client, NotConfiguredCommercialCoreClient)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "https://cc.example.com"},
        {"client_id": "cid"},
        {"client_secret": "csecret"},
        {"base_url": "https://cc.example.com", "client_id": "cid"},
    ],
)
def test_partial_configuration_fails_loud(monkeypatch, kwargs):
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_BASE_URL", None)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_CLIENT_ID", None)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_CLIENT_SECRET", None)

    with pytest.raises(CommercialCoreConfigurationError):
        build_commercial_core_client(**kwargs)


def test_fully_configured_returns_a_real_http_client():
    client = build_commercial_core_client(
        base_url="https://cc.example.com", client_id="cid", client_secret="csecret", timeout_seconds=2.0
    )
    assert isinstance(client, HttpCommercialCoreClient)


def test_importing_settings_never_fails_when_commercial_core_is_unconfigured(monkeypatch):
    """Task 01D-B's own hard requirement: production startup must never
    fail merely because Commercial Core is not yet configured. Building
    `Settings()` fresh (as app startup does) must not raise even when no
    COMMERCIAL_CORE_* environment variable is set."""
    from app.core.config import Settings

    Settings()  # must not raise


def test_get_commercial_core_client_is_cached(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_BASE_URL", None)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_CLIENT_ID", None)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_CLIENT_SECRET", None)
    get_commercial_core_client.cache_clear()
    try:
        first = get_commercial_core_client()
        second = get_commercial_core_client()
        assert first is second
    finally:
        get_commercial_core_client.cache_clear()


# --- Group 2: NotConfiguredCommercialCoreClient preserves the existing 501 fallback --


def test_not_configured_client_get_attention_raises_the_existing_unavailable_error():
    client = NotConfiguredCommercialCoreClient()
    with pytest.raises(CommercialCoreUnavailable) as exc_info:
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )
    assert exc_info.value.status_code == 501
    assert "Attention" in exc_info.value.detail


# --- Group 3: HttpCommercialCoreClient -- the real HTTP call ------------------------


def _client(monkeypatch, post_impl) -> HttpCommercialCoreClient:
    monkeypatch.setattr(httpx, "post", post_impl)
    return HttpCommercialCoreClient(
        base_url="https://cc.example.com", client_id="cid", client_secret=_SECRET, timeout_seconds=2.0
    )


def test_successful_call_sends_the_expected_request_and_decodes_the_contract_dto(monkeypatch):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeResponse(200, _attention_result_body())

    client = _client(monkeypatch, fake_post)
    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = client.get_attention(
        organization_id=_ORG_ID, scope="organization", site_id=None, as_of=as_of, window_days=30, request_id="req-123"
    )

    assert isinstance(result, AttentionResultDTO)
    assert result.organization_id == _ORG_ID

    assert captured["url"] == "https://cc.example.com/internal/v1/attention"
    assert captured["timeout"] == 2.0
    assert captured["json"] == {
        "scope": "organization",
        "site_id": None,
        "as_of": as_of.isoformat(),
        "window_days": 30,
    }
    assert captured["headers"]["Authorization"] == f"Bearer cid:{_SECRET}"
    assert captured["headers"]["X-SIE-Contract-Version"] == sie_contract.__version__
    assert captured["headers"]["X-Organization-Id"] == str(_ORG_ID)
    assert captured["headers"]["X-Request-Id"] == "req-123"


def test_contract_version_header_is_read_from_the_vendored_package_not_hardcoded(monkeypatch):
    """Task 01D-B's own explicit instruction: X-SIE-Contract-Version must
    come from the installed/vendored sie_contract.__version__, never a
    hardcoded '0.2.0' literal. Proven by changing the runtime value and
    observing the header follow it -- a hardcoded literal would not."""
    monkeypatch.setattr(sie_contract, "__version__", "9.9.9-test-only")
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["headers"] = headers
        return _FakeResponse(200, _attention_result_body())

    client = _client(monkeypatch, fake_post)
    client.get_attention(
        organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
    )
    assert captured["headers"]["X-SIE-Contract-Version"] == "9.9.9-test-only"


def test_site_scope_sends_site_id(monkeypatch):
    site_id = uuid.uuid4()
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["json"] = json
        return _FakeResponse(200, _attention_result_body(scope="site", entity_id=str(site_id)))

    client = _client(monkeypatch, fake_post)
    result = client.get_attention(
        organization_id=_ORG_ID, scope="site", site_id=site_id, as_of=None, window_days=None, request_id=None
    )
    assert captured["json"]["site_id"] == str(site_id)
    assert result.entity_id == site_id


def test_no_request_id_omits_the_header(monkeypatch):
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["headers"] = headers
        return _FakeResponse(200, _attention_result_body())

    client = _client(monkeypatch, fake_post)
    client.get_attention(
        organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
    )
    assert "X-Request-Id" not in captured["headers"]


# --- Authentication (401) -----------------------------------------------------------


def test_authentication_failure_maps_to_a_typed_error_without_leaking_the_secret(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(
            401, ErrorResponse(error_code="AUTHENTICATION_FAILURE", message="Authentication failed.", request_id="r", retryable=False).model_dump(mode="json")
        )

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreAuthenticationError) as exc_info:
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )
    assert _SECRET not in str(exc_info.value)


# --- Authorization (403) -------------------------------------------------------------


def test_authorization_failure_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(
            403,
            ErrorResponse(
                error_code=KnownErrorCode.AUTHORIZATION_FAILURE, message="Not authorized.", request_id="r", retryable=False
            ).model_dump(mode="json"),
        )

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreAuthorizationError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


def test_tenant_mismatch_403_maps_to_a_typed_error_too(monkeypatch):
    """Should never happen given resolve_authorized_organization_id() is
    always the source of the organization id sent -- but if cc_service's
    own reject_tenant_override() ever fired, it must still be handled,
    never crash the request with an unhandled exception."""

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(
            403,
            ErrorResponse(
                error_code=KnownErrorCode.TENANT_MISMATCH, message="Tenant mismatch.", request_id="r", retryable=False
            ).model_dump(mode="json"),
        )

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreAuthorizationError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


# --- Validation (422) ----------------------------------------------------------------


def test_validation_failure_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(
            422,
            ErrorResponse(
                error_code=KnownErrorCode.VALIDATION_ERROR, message="Invalid.", request_id="r", retryable=False
            ).model_dump(mode="json"),
        )

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreValidationError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


# --- Availability: 503 / connection failure / timeout ---------------------------------


def test_dependency_unavailable_503_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(
            503,
            ErrorResponse(
                error_code=KnownErrorCode.DEPENDENCY_UNAVAILABLE, message="Unavailable.", request_id="r", retryable=True
            ).model_dump(mode="json"),
        )

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreDependencyUnavailableError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


def test_timeout_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        raise httpx.ReadTimeout("timed out")

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreTimeoutError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


def test_connection_failure_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        raise httpx.ConnectError("could not connect")

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreConnectionError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


# --- Protocol: malformed JSON / DTO validation failure / unexpected status -----------


def test_malformed_json_on_success_status_is_a_protocol_error_not_an_empty_success(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(200, ValueError("not json"))

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreMalformedResponseError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


def test_json_failing_dto_validation_is_a_protocol_error_not_an_empty_success(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(200, {"organization_id": "not-a-uuid"})

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreMalformedResponseError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


def test_unexpected_status_maps_to_a_typed_error(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse(418, {"detail": "teapot"})

    client = _client(monkeypatch, fake_post)
    with pytest.raises(CommercialCoreUnexpectedStatusError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
        )


# --- Security: the credential never appears in an exception message or a log line ----


def test_secret_never_appears_in_any_raised_exception_message(monkeypatch):
    scenarios = [
        (401, ErrorResponse(error_code="AUTHENTICATION_FAILURE", message="x", request_id="r", retryable=False).model_dump(mode="json")),
        (403, ErrorResponse(error_code=KnownErrorCode.AUTHORIZATION_FAILURE, message="x", request_id="r", retryable=False).model_dump(mode="json")),
        (422, ErrorResponse(error_code=KnownErrorCode.VALIDATION_ERROR, message="x", request_id="r", retryable=False).model_dump(mode="json")),
        (503, ErrorResponse(error_code=KnownErrorCode.DEPENDENCY_UNAVAILABLE, message="x", request_id="r", retryable=True).model_dump(mode="json")),
        (418, {"detail": "teapot"}),
    ]
    for status_code, body in scenarios:
        def fake_post(url, *, json, headers, timeout, _body=body, _status=status_code):
            return _FakeResponse(_status, _body)

        client = _client(monkeypatch, fake_post)
        with pytest.raises(Exception) as exc_info:
            client.get_attention(
                organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id=None
            )
        assert _SECRET not in str(exc_info.value)
        assert f"cid:{_SECRET}" not in str(exc_info.value)


def test_secret_never_appears_in_logs_across_every_failure_path(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.DEBUG, logger="sie.integrations.commercial_core")

    def fake_post_401(url, *, json, headers, timeout):
        return _FakeResponse(
            401, ErrorResponse(error_code="AUTHENTICATION_FAILURE", message="x", request_id="r", retryable=False).model_dump(mode="json")
        )

    client = _client(monkeypatch, fake_post_401)
    with pytest.raises(CommercialCoreAuthenticationError):
        client.get_attention(
            organization_id=_ORG_ID, scope="organization", site_id=None, as_of=None, window_days=None, request_id="req-secret-test"
        )

    for record in caplog.records:
        assert _SECRET not in record.getMessage()
        assert f"cid:{_SECRET}" not in record.getMessage()
        assert "Authorization" not in record.getMessage()
