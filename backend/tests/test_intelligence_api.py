"""Intelligence & Predictive Analytics API — milestone items 9, 10, 21,
27, 36, 37. Runs against the ordinary SQLite `client` fixture — nothing
here needs pgvector.
"""

import uuid
from datetime import datetime, timezone

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


def test_analytics_summary_rejects_an_organization_the_user_has_no_membership_in(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider@example.com")
    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org['id']}",
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
