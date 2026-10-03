"""Intelligence & Predictive Analytics API — milestone items 9, 10, 21,
27, 36, 37. Runs against the ordinary SQLite `client` fixture — nothing
here needs pgvector.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.test_ingestion_api import create_org, make_user


def _make_client_credential(db_session, org_id, *, scopes=None):
    scopes = scopes if scopes is not None else [Permission.SAFETY_DATA_WRITE]
    return api_client_service.create(db_session, organization_id=org_id, name="Test Integration", scopes=scopes)


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def event_payload(**overrides):
    # A real "now" timestamp, not a fixed date -- so tests that filter by
    # a trailing analysis window (e.g. the default 30-day window) never
    # depend on how far this suite's own wall-clock date has drifted
    # from any hardcoded date literal.
    payload = {
        "event_type": "INCIDENT",
        "event_time": datetime.now(timezone.utc).isoformat(),
        "source_system": "test-system",
        "source_record_id": str(uuid.uuid4()),
        "severity": "low",
    }
    payload.update(overrides)
    return payload


# --- Machine-client authentication (milestone item 10) -----------------------------


def test_ingestion_requires_authentication(client):
    response = client.post("/api/v1/intelligence/events", json=event_payload())
    assert response.status_code == 401


def test_ingestion_rejects_a_malformed_authorization_header(client):
    response = client.post(
        "/api/v1/intelligence/events", json=event_payload(), headers={"Authorization": "not-bearer-at-all"}
    )
    assert response.status_code == 401


def test_ingestion_rejects_an_invalid_credential(client):
    response = client.post(
        "/api/v1/intelligence/events",
        json=event_payload(),
        headers={"Authorization": "Bearer sie_fake:not-a-real-secret"},
    )
    assert response.status_code == 401


def test_ingestion_rejects_a_client_missing_the_write_scope(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(
        db_session, uuid.UUID(org["id"]), scopes=[Permission.SAFETY_DATA_READ]
    )
    response = client.post(
        "/api/v1/intelligence/events", json=event_payload(), headers=_bearer(credential)
    )
    assert response.status_code == 403


def test_ingestion_succeeds_with_a_valid_scoped_credential(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.post(
        "/api/v1/intelligence/events", json=event_payload(), headers=_bearer(credential)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "CREATED"
    assert body["data_quality_status"] == "VALID"


def test_the_dev_mode_human_header_never_authenticates_ingestion(client, db_session):
    """Milestone item 10: 'Do NOT use the development identity-header
    mechanism for production machine integrations.'"""
    user = make_user(db_session, "human@example.com")
    response = client.post(
        "/api/v1/intelligence/events", json=event_payload(), headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 401


# --- Batch ingestion (milestone item 38) --------------------------------------------


def test_batch_ingestion_reports_a_summary_and_per_record_results(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.post(
        "/api/v1/intelligence/events/batch",
        json={"events": [event_payload(), event_payload(source_record_id=None)]},
        headers=_bearer(credential),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 1
    assert body["rejected_count"] == 1
    assert len(body["records"]) == 2


# --- Idempotency through the full API path ------------------------------------------


def test_resending_the_same_event_through_the_api_is_idempotent(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    payload = event_payload(source_record_id="OBS-2026-00125")

    first = client.post("/api/v1/intelligence/events", json=payload, headers=_bearer(credential))
    second = client.post("/api/v1/intelligence/events", json=payload, headers=_bearer(credential))

    assert first.json()["outcome"] == "CREATED"
    assert second.json()["outcome"] == "SKIPPED_IDEMPOTENT"
    assert second.json()["event_id"] == first.json()["event_id"]


# --- Tenant isolation on reads (milestone item 36) ----------------------------------


def test_analytics_summary_requires_authentication(client):
    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={uuid.uuid4()}"
    )
    assert response.status_code == 401


def test_analytics_summary_rejects_an_unknown_dev_user_id(client):
    """TASK G1 authorization matrix: an invalid/unknown identity must
    still fail with 401, before authorization or audit logging is ever
    reached -- untouched by this task's fix, included here as a
    regression anchor for the full matrix."""
    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={uuid.uuid4()}",
        headers=dev_auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 401


def test_analytics_summary_rejects_an_organization_the_user_has_no_membership_in(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider@example.com")
    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org['id']}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_analytics_summary_rejects_a_nonexistent_organization_with_403_not_500(client, db_session):
    """TASK G1 regression: a syntactically valid but nonexistent
    `organization_id` must still fail authorization cleanly (403) --
    not crash the access-denied audit write with an `IntegrityError`
    on `AuditLog.organization_id`'s real FK to `organizations.id` (see
    `app/api/deps_context.py::_log_access_denied`)."""
    user = make_user(db_session, "no-such-org@example.com")
    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={uuid.uuid4()}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


# M43-IP-03: `test_analytics_summary_never_leaks_another_organizations_events`,
# `test_features_endpoint_succeeds_for_an_authorized_member`,
# `test_trends_endpoint_rejects_an_unknown_metric`, and
# `test_trends_endpoint_succeeds_for_a_known_metric` removed -- each
# asserted on a real computed value (event_count, feature content, metric
# validation/filtering) that no longer exists: analytics computation was
# extracted to the private Commercial Core repository and these
# endpoints now always return 501. The authorization-only checks below
# (`..._requires_intelligence_read_permission`, `..._requires_authorization`)
# are unaffected -- the permission dependency still runs, and still
# rejects, before the handler's now-501 body. See
# docs/M43_IP_03_PUBLIC_EXTRACTION.md's "Test coverage regressions"
# section.


def test_features_endpoint_requires_intelligence_read_permission(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "no-permission@example.com")
    response = client.get(
        f"/api/v1/intelligence/features?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 403


def test_signals_endpoint_requires_authorization(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "signals-outsider@example.com")
    response = client.get(
        f"/api/v1/intelligence/analytics/signals?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 403


# --- Response shape never leaks internals -------------------------------------------


def test_ingestion_response_never_exposes_an_api_secret_or_hash(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.post(
        "/api/v1/intelligence/events", json=event_payload(), headers=_bearer(credential)
    )
    body_text = response.text
    assert credential.secret not in body_text
    assert credential.api_client.hashed_secret not in body_text


# --- Attention (Task 01D-B: Public SIE Commercial Core Attention Client) ------------
#
# These exercise the API-route wiring (app/api/v1/intelligence.py's
# organization_attention/site_attention) against a fake
# CommercialCoreClient -- never a live Commercial Core deployment. The
# client's own HTTP behavior (headers, error mapping, contract decoding)
# is covered independently in tests/test_commercial_core_client.py.


class _FakeAttentionClient:
    """A `CommercialCoreClient` test double -- records every call it
    receives (for asserting tenant-security/request-id propagation) and
    either returns a canned `AttentionResultDTO` or raises whatever
    error the test configures."""

    def __init__(self, *, result=None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.calls: list[dict] = []

    def unavailable(self, capability: str):
        raise NotImplementedError

    def get_attention(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


def _attention_result(organization_id, *, scope="organization", entity_id=None):
    from datetime import datetime, timezone

    from sie_contract import AsOfWindow, AttentionResultDTO

    return AttentionResultDTO(
        organization_id=organization_id,
        scope=scope,
        entity_id=entity_id,
        as_of=AsOfWindow(
            as_of=datetime.now(timezone.utc), generated_at=datetime.now(timezone.utc), window_days=30
        ),
        items=[],
        category_status=[],
    )


def test_attention_is_501_when_commercial_core_is_not_configured(client, db_session):
    """The existing NotConfiguredCommercialCoreClient fallback (item 9's
    own "preserve the existing 501 fallback" requirement) -- this test
    runs against the real, unconfigured get_commercial_core_client(),
    no monkeypatching at all."""
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])
    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 501


def test_attention_succeeds_with_a_configured_client(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAttentionClient(result=_attention_result(org_id))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}&window_days=30",
        headers=_bearer(credential),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["organization_id"] == str(org_id)
    assert body["scope"] == "organization"

    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["organization_id"] == org_id
    assert call["scope"] == "organization"
    assert call["site_id"] is None
    assert call["window_days"] == 30


def test_site_attention_sends_site_scope_and_site_id(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    site_id = uuid.uuid4()
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAttentionClient(result=_attention_result(org_id, scope="site", entity_id=site_id))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/sites/{site_id}/attention?organization_id={org['id']}",
        headers=_bearer(credential),
    )

    assert response.status_code == 200
    assert response.json()["entity_id"] == str(site_id)
    assert fake_client.calls[0]["scope"] == "site"
    assert fake_client.calls[0]["site_id"] == site_id


def test_attention_propagates_the_public_sie_request_id_to_the_client_call(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAttentionClient(result=_attention_result(org_id))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 200
    # Public SIE's own request id is always server-generated (see
    # app/core/request_id.py) -- this asserts the *same* value the
    # response carries is exactly what reached the client call, never a
    # second, independently generated id.
    assert fake_client.calls[0]["request_id"] == response.headers["X-Request-Id"]


def test_attention_maps_a_client_integration_error_to_503_model_not_available(client, db_session, monkeypatch):
    from app.integrations.commercial_core import (
        CommercialCoreDependencyUnavailableError,
    )

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAttentionClient(
        error=CommercialCoreDependencyUnavailableError("A Commercial Core dependency is currently unavailable.")
    )
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "MODEL_NOT_AVAILABLE"


def test_attention_maps_a_commercial_core_validation_error_to_422_validation_error(
    client, db_session, monkeypatch
):
    """Follow-up to Task 01D-B: a CommercialCoreValidationError (cc_service's
    own 422 -- see sie_contract.KnownErrorCode.VALIDATION_ERROR /
    retryable=False) must surface as Public SIE's existing 422
    VALIDATION_ERROR, not the generic 503 MODEL_NOT_AVAILABLE every other
    CommercialCoreIntegrationError subclass maps to -- collapsing it into
    503 would incorrectly imply the request might succeed by simply
    retrying."""
    from app.integrations.commercial_core import CommercialCoreValidationError

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAttentionClient(
        error=CommercialCoreValidationError("Commercial Core rejected the request as invalid.")
    )
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_site_attention_also_maps_a_commercial_core_validation_error_to_422(client, db_session, monkeypatch):
    """Same mapping, exercised on the sibling site_attention route -- both
    routes call the same _map_commercial_core_attention_error() helper,
    but each has its own try/except, so each is worth locking in."""
    from app.integrations.commercial_core import CommercialCoreValidationError

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    site_id = uuid.uuid4()
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAttentionClient(
        error=CommercialCoreValidationError("Commercial Core rejected the request as invalid.")
    )
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/sites/{site_id}/attention?organization_id={org['id']}",
        headers=_bearer(credential),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_attention_tenant_security_a_machine_credential_cannot_reach_a_different_organization(
    client, db_session, monkeypatch
):
    """Item 14 (tenant security, marked critical): a machine credential
    scoped to org A must never reach org B's Attention data by asserting
    org B's id in the query string -- require_context_permission()'s
    existing machine-organization-pinning check must reject this before
    the route body (and therefore the client) is ever reached."""
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    credential = _make_client_credential(
        db_session, uuid.UUID(org_a["id"]), scopes=[Permission.INTELLIGENCE_READ]
    )
    fake_client = _FakeAttentionClient(result=_attention_result(uuid.UUID(org_b["id"])))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org_b['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 403
    assert fake_client.calls == []  # the client was never even invoked


def test_attention_response_never_exposes_a_client_secret(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAttentionClient(result=_attention_result(org_id))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential)
    )

    body_text = response.text
    assert credential.secret not in body_text
    assert credential.api_client.hashed_secret not in body_text


# --- Analytics (Task 01D-F2: Public SIE Commercial Core Analytics Client) ----------
#
# These exercise the API-route wiring (app/api/v1/intelligence.py's
# analytics_summary/analytics_trends/analytics_signals) against a fake
# CommercialCoreClient -- never a live Commercial Core deployment,
# mirroring the Attention tests above exactly. The client's own HTTP
# behavior is covered independently in
# tests/test_commercial_core_analytics_client.py.


class _FakeAnalyticsClient:
    """A `CommercialCoreClient` test double for the three Analytics
    methods -- mirrors `_FakeAttentionClient`'s identical shape."""

    def __init__(self, *, result=None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.calls: list[dict] = []

    def unavailable(self, capability: str):
        raise NotImplementedError

    def _call(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result

    def get_analytics_summary(self, **kwargs):
        return self._call(**kwargs)

    def get_analytics_trends(self, **kwargs):
        return self._call(**kwargs)

    def get_analytics_signals(self, **kwargs):
        return self._call(**kwargs)


def _analytics_summary_result(organization_id, *, entity_id=None, event_count=0, data_sufficiency="INSUFFICIENT_DATA", indicators=None, signals=None):
    from sie_contract import AnalyticsSummaryDTO, AsOfWindow

    now = datetime.now(timezone.utc)
    return AnalyticsSummaryDTO(
        organization_id=organization_id,
        entity_id=entity_id,
        as_of=AsOfWindow(as_of=now, generated_at=now, window_days=30),
        event_count=event_count,
        data_sufficiency=data_sufficiency,
        indicators=indicators or [],
        signals=signals or [],
    )


def _analytics_trend_result(organization_id, *, metric="incident_count", entity_id=None, direction="STABLE"):
    from sie_contract import AnalyticsTrendDTO, AsOfWindow

    now = datetime.now(timezone.utc)
    return AnalyticsTrendDTO(
        organization_id=organization_id,
        entity_id=entity_id,
        metric=metric,
        as_of=AsOfWindow(as_of=now, generated_at=now, window_days=30),
        direction=direction,
        periods=[],
    )


def _analytics_signals_result(organization_id, *, entity_id=None, signals=None):
    from sie_contract import AnalyticsSignalsResultDTO, AsOfWindow

    now = datetime.now(timezone.utc)
    return AnalyticsSignalsResultDTO(
        organization_id=organization_id,
        entity_id=entity_id,
        as_of=AsOfWindow(as_of=now, generated_at=now, window_days=30),
        signals=signals or [],
    )


def _analytics_signal_dto(*, signal_type="OVERDUE_ACTION_SURGE", severity="HIGH"):
    from sie_contract import AnalyticsSignalDTO

    now = datetime.now(timezone.utc)
    return AnalyticsSignalDTO(
        signal_type=signal_type, severity=severity, observed_period_start=now, observed_period_end=now, entity_id=None, evidence=[]
    )


def test_analytics_summary_is_501_when_commercial_core_is_not_configured(client, db_session):
    """The existing NotConfiguredCommercialCoreClient fallback -- runs
    against the real, unconfigured get_commercial_core_client(), no
    monkeypatching at all."""
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])
    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 501


def test_analytics_trends_is_501_when_commercial_core_is_not_configured(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])
    response = client.get(
        f"/api/v1/intelligence/analytics/trends?organization_id={org['id']}&metric=incident_count",
        headers=_bearer(credential),
    )
    assert response.status_code == 501


def test_analytics_signals_is_501_when_commercial_core_is_not_configured(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])
    response = client.get(
        f"/api/v1/intelligence/analytics/signals?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 501


def test_analytics_summary_succeeds_with_a_configured_client_and_reshapes_indicators_for_the_existing_frontend(
    client, db_session, monkeypatch
):
    """Task 01D-F2's own response-shape fix: HomePage.tsx reads
    `indicator.feature.value` -- this proves the route actually nests
    that, rather than returning the contract DTO's flat {name,
    category, value} shape verbatim."""
    from sie_contract import AnalyticsIndicatorDTO

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    indicator = AnalyticsIndicatorDTO(name="incident_count", category="LAGGING", value=5.0)
    fake_client = _FakeAnalyticsClient(result=_analytics_summary_result(org_id, event_count=12, indicators=[indicator]))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org['id']}&window_days=30",
        headers=_bearer(credential),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["organization_id"] == str(org_id)
    assert body["event_count"] == 12
    assert body["entity_type"] == "organization"
    assert body["indicators"][0]["name"] == "incident_count"
    assert body["indicators"][0]["feature"]["value"] == 5.0

    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["organization_id"] == org_id
    assert fake_client.calls[0]["window_days"] == 30


def test_analytics_summary_response_contains_every_field_homepage_reads(client, db_session, monkeypatch):
    """Task 01D-F2 review fix: `window_days` lives on `AnalyticsSummaryDTO.
    as_of.window_days` in the shared contract (never a sibling field of
    `AnalyticsSummaryDTO` itself -- see `sie_contract.common.AsOfWindow`),
    and is flattened back out to a top-level `window_days` key only by
    `_analytics_summary_response()` at this API layer. No prior test
    asserted on the *response body's* `window_days` at all (only on the
    outbound *request* sent to the CommercialCoreClient) -- this closes
    that gap, and does the same for every other field
    `src/features/home/HomePage.tsx` actually dereferences from
    `getAnalyticsSummary()`'s result: `window_days`, `event_count`,
    `data_sufficiency`, `signals` (`.length`, `.signal_type`, `.severity`,
    `.observed_period_start/end`), and `indicators` (`.category`, `.name`,
    `.feature.value`)."""
    from sie_contract import AnalyticsIndicatorDTO

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    indicator = AnalyticsIndicatorDTO(name="incident_count", category="LAGGING", value=5.0)
    signal = _analytics_signal_dto(signal_type="OVERDUE_ACTION_SURGE", severity="HIGH")
    fake_client = _FakeAnalyticsClient(
        result=_analytics_summary_result(
            org_id, event_count=12, data_sufficiency="SUFFICIENT_DATA", indicators=[indicator], signals=[signal]
        )
    )
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org['id']}&window_days=30",
        headers=_bearer(credential),
    )

    assert response.status_code == 200
    body = response.json()

    # HomePage.tsx's "At a glance" section: `Based on the last
    # ${summary.window_days} days.` -- the exact field this review fix
    # targets.
    assert "window_days" in body
    assert body["window_days"] == 30

    # Every other field HomePage.tsx's analytics-summary rendering path
    # actually reads.
    assert body["event_count"] == 12
    assert body["data_sufficiency"] == "SUFFICIENT_DATA"
    assert len(body["signals"]) == 1
    assert body["signals"][0]["signal_type"] == "OVERDUE_ACTION_SURGE"
    assert body["signals"][0]["severity"] == "HIGH"
    assert "observed_period_start" in body["signals"][0]
    assert "observed_period_end" in body["signals"][0]
    assert body["indicators"][0]["category"] == "LAGGING"
    assert body["indicators"][0]["name"] == "incident_count"
    assert body["indicators"][0]["feature"]["value"] == 5.0


def test_analytics_summary_site_scope_sets_entity_type_site(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    site_id = uuid.uuid4()
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAnalyticsClient(result=_analytics_summary_result(org_id, entity_id=site_id))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org['id']}&site_id={site_id}",
        headers=_bearer(credential),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entity_type"] == "site"
    assert body["entity_id"] == str(site_id)
    assert fake_client.calls[0]["site_id"] == site_id


def test_analytics_trends_requires_a_metric_query_parameter(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])
    response = client.get(
        f"/api/v1/intelligence/analytics/trends?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 422


def test_analytics_trends_succeeds_with_a_configured_client(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAnalyticsClient(result=_analytics_trend_result(org_id, metric="incident_count", direction="INCREASING"))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/analytics/trends?organization_id={org['id']}&metric=incident_count",
        headers=_bearer(credential),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metric"] == "incident_count"
    assert body["direction"] == "INCREASING"
    assert fake_client.calls[0]["metric"] == "incident_count"


def test_analytics_signals_succeeds_and_returns_a_bare_array_for_the_existing_frontend(client, db_session, monkeypatch):
    """`src/services/api/analytics.ts::getAnalyticsSignals()` expects a
    bare `RiskSignal[]` array, not an organization/as_of-enveloped
    object -- this proves the route unwraps the contract's own
    envelope rather than returning it verbatim."""
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    signal = _analytics_signal_dto(signal_type="OVERDUE_ACTION_SURGE")
    fake_client = _FakeAnalyticsClient(result=_analytics_signals_result(org_id, signals=[signal]))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/analytics/signals?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body[0]["signal_type"] == "OVERDUE_ACTION_SURGE"


def test_analytics_summary_propagates_the_public_sie_request_id_to_the_client_call(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAnalyticsClient(result=_analytics_summary_result(org_id))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 200
    assert fake_client.calls[0]["request_id"] == response.headers["X-Request-Id"]


@pytest.mark.parametrize(
    "path,extra",
    [
        ("analytics/summary", ""),
        ("analytics/trends", "&metric=incident_count"),
        ("analytics/signals", ""),
    ],
)
def test_analytics_maps_a_client_integration_error_to_503_model_not_available(client, db_session, monkeypatch, path, extra):
    from app.integrations.commercial_core import CommercialCoreDependencyUnavailableError

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAnalyticsClient(
        error=CommercialCoreDependencyUnavailableError("A Commercial Core dependency is currently unavailable.")
    )
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/{path}?organization_id={org['id']}{extra}", headers=_bearer(credential)
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_AVAILABLE"


@pytest.mark.parametrize(
    "path,extra",
    [
        ("analytics/summary", ""),
        ("analytics/trends", "&metric=incident_count"),
        ("analytics/signals", ""),
    ],
)
def test_analytics_maps_a_commercial_core_validation_error_to_422(client, db_session, monkeypatch, path, extra):
    from app.integrations.commercial_core import CommercialCoreValidationError

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAnalyticsClient(error=CommercialCoreValidationError("Commercial Core rejected the request as invalid."))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/{path}?organization_id={org['id']}{extra}", headers=_bearer(credential)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_analytics_summary_tenant_security_a_machine_credential_cannot_reach_a_different_organization(
    client, db_session, monkeypatch
):
    """A machine credential scoped to org A must never reach org B's
    Analytics data by asserting org B's id in the query string --
    require_context_permission()'s existing machine-organization-pinning
    check must reject this before the route body (and therefore the
    client) is ever reached."""
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    credential = _make_client_credential(db_session, uuid.UUID(org_a["id"]), scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAnalyticsClient(result=_analytics_summary_result(uuid.UUID(org_b["id"])))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org_b['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 403
    assert fake_client.calls == []  # the client was never even invoked


def test_analytics_summary_response_never_exposes_a_client_secret(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeAnalyticsClient(result=_analytics_summary_result(org_id))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org['id']}", headers=_bearer(credential)
    )

    body_text = response.text
    assert credential.secret not in body_text
    assert credential.api_client.hashed_secret not in body_text
