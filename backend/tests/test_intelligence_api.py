"""Intelligence & Predictive Analytics API — milestone items 9, 10, 21,
27, 36, 37. Runs against the ordinary SQLite `client` fixture — nothing
here needs pgvector.
"""

import uuid
from datetime import datetime, timezone

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.test_ingestion_api import create_org, make_membership, make_user


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


def test_analytics_summary_never_leaks_another_organizations_events(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))
    credential_b = _make_client_credential(db_session, uuid.UUID(org_b["id"]))

    for i in range(5):
        client.post(
            "/api/v1/intelligence/events",
            json=event_payload(source_record_id=f"a-{i}"),
            headers=_bearer(credential_a),
        )
    for i in range(9):
        client.post(
            "/api/v1/intelligence/events",
            json=event_payload(source_record_id=f"b-{i}"),
            headers=_bearer(credential_b),
        )

    user = make_user(db_session, "org-a-viewer@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org_a["id"]), role="VIEWER")

    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org_a['id']}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    assert response.json()["event_count"] == 5  # never Org B's 9


def test_features_endpoint_requires_intelligence_read_permission(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "no-permission@example.com")
    response = client.get(
        f"/api/v1/intelligence/features?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 403


def test_features_endpoint_succeeds_for_an_authorized_member(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "member@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    response = client.get(
        f"/api/v1/intelligence/features?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 200
    assert "incident_count" in response.json()["features"]


def test_signals_endpoint_requires_authorization(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "signals-outsider@example.com")
    response = client.get(
        f"/api/v1/intelligence/analytics/signals?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 403


def test_trends_endpoint_rejects_an_unknown_metric(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "trends-user@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    response = client.get(
        f"/api/v1/intelligence/analytics/trends?organization_id={org['id']}&metric=not_a_real_metric",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 400


def test_trends_endpoint_succeeds_for_a_known_metric(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "trends-user-2@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    response = client.get(
        f"/api/v1/intelligence/analytics/trends?organization_id={org['id']}&metric=incident_count",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    assert response.json()["metric"] == "incident_count"


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
