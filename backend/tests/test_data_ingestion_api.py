"""HTTP-level tests for the Enterprise Data Ingestion & Validation
Foundation v0.1 API (`POST /api/v1/data/ingestion`,
`GET /api/v1/data/ingestion/batches[/{batch_id}]`) — authentication,
tenant isolation, the response contract, idempotency, security, and
intelligence-layer compatibility.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.audit_log import AuditLog
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org
from tests.test_ingestion_api import make_membership, make_user

_URL = "/api/v1/data/ingestion"


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _record(**overrides) -> dict:
    body = {
        "event_type": "INCIDENT",
        "event_time": "2026-01-01T00:00:00Z",
        "source_system": "sap-erp",
        "source_record_id": "INC-001",
    }
    body.update(overrides)
    return body


def _org_admin(db_session, organization_id):
    admin = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    make_membership(db_session, user_id=admin.id, organization_id=organization_id, role="ORG_ADMIN")
    return admin


# --- Authentication ---------------------------------------------------------------------


def test_valid_machine_client_can_ingest(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Integration", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    response = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["total_records"] == 1
    assert body["accepted_records"] == 1


def test_missing_credentials_is_rejected(client):
    response = client.post(_URL, json={"records": [_record()]})
    assert response.status_code == 401


def test_invalid_credentials_are_rejected(client):
    response = client.post(
        _URL, json={"records": [_record()]}, headers={"Authorization": "Bearer sie_doesnotexist:whatever"}
    )
    assert response.status_code == 401


def test_revoked_client_is_rejected(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Revoked", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    api_client_service.revoke(db_session, api_client=credential.api_client)
    response = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential))
    assert response.status_code == 401


def test_expired_client_is_rejected(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session,
        organization_id=org.id,
        name="Expired",
        scopes=[Permission.SAFETY_DATA_WRITE],
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    response = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential))
    assert response.status_code == 401


def test_insufficient_permission_is_rejected(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Read-only", scopes=[Permission.SAFETY_DATA_READ]
    )
    response = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential))
    assert response.status_code == 403


def test_batch_read_endpoints_require_authentication(client):
    org_id = uuid.uuid4()
    assert client.get(f"{_URL}/batches?organization_id={org_id}").status_code == 401
    assert client.get(f"{_URL}/batches/{uuid.uuid4()}?organization_id={org_id}").status_code == 401


# --- Tenant isolation ---------------------------------------------------------------------


def test_machine_client_can_only_ever_write_into_its_own_organization(client, db_session):
    """There is no field on the request body a client could use to name
    a different organization -- the authenticated credential's own
    organization is the only one ever used."""
    org_a = make_org(db_session, "Org A")
    credential_a = api_client_service.create(
        db_session, organization_id=org_a.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    response = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential_a))
    assert response.status_code == 201

    from app.models.safety_event import SafetyEvent

    event = db_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "INC-001").one()
    assert event.organization_id == org_a.id


def test_machine_client_cannot_reference_another_organizations_source(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential_a = api_client_service.create(
        db_session, organization_id=org_a.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    admin_b = _org_admin(db_session, org_b.id)
    source_b = client.post(
        f"/api/v1/organizations/{org_b.id}/data-sources",
        json={"name": "Org B Source", "source_type": "erp"},
        headers=dev_auth_headers(admin_b.id),
    ).json()

    response = client.post(
        _URL, json={"source_id": source_b["id"], "records": [_record()]}, headers=_bearer(credential_a)
    )
    assert response.status_code == 404


def test_machine_client_cannot_read_another_organizations_batches(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential_a = api_client_service.create(
        db_session, organization_id=org_a.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE, Permission.SAFETY_DATA_READ]
    )
    credential_b = api_client_service.create(
        db_session, organization_id=org_b.id, name="B", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    created = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential_b)).json()

    listing = client.get(f"{_URL}/batches?organization_id={org_a.id}", headers=_bearer(credential_a))
    assert listing.status_code == 200
    assert listing.json() == []

    # credential_a is genuinely authorized to read *its own* organization
    # (org_a) -- but org_b's batch simply doesn't exist under org_a's
    # scope, so the lookup itself finds nothing: 404, never leaking that
    # a batch with this id exists under a different tenant.
    cross_tenant_read = client.get(
        f"{_URL}/batches/{created['batch_id']}?organization_id={org_a.id}", headers=_bearer(credential_a)
    )
    assert cross_tenant_read.status_code == 404

    # Naming org_b directly is denied at the authorization layer itself --
    # credential_a is never authorized for org_b at all, regardless of
    # which batch id is requested.
    same_org_wrong_batch = client.get(
        f"{_URL}/batches/{created['batch_id']}?organization_id={org_b.id}", headers=_bearer(credential_a)
    )
    assert same_org_wrong_batch.status_code == 403


def test_machine_client_can_read_its_own_batch(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE, Permission.SAFETY_DATA_READ]
    )
    created = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential)).json()

    response = client.get(f"{_URL}/batches/{created['batch_id']}?organization_id={org.id}", headers=_bearer(credential))
    assert response.status_code == 200
    assert response.json()["batch_id"] == created["batch_id"]
    assert len(response.json()["records"]) == 1


def test_submitting_against_a_legitimate_own_organization_source_links_the_canonical_event(client, db_session):
    org = make_org(db_session)
    admin = _org_admin(db_session, org.id)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    source = client.post(
        f"/api/v1/organizations/{org.id}/data-sources",
        json={"name": "SAP ERP", "source_type": "erp"},
        headers=dev_auth_headers(admin.id),
    ).json()

    response = client.post(
        _URL, json={"source_id": source["id"], "records": [_record()]}, headers=_bearer(credential)
    )
    assert response.status_code == 201
    assert response.json()["source_id"] == source["id"]

    from app.models.safety_event import SafetyEvent

    event = db_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "INC-001").one()
    assert str(event.ingestion_source_id) == source["id"]


def test_a_human_org_member_can_also_read_batch_status(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    admin = _org_admin(db_session, org.id)
    created = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential)).json()

    response = client.get(f"{_URL}/batches/{created['batch_id']}?organization_id={org.id}", headers=dev_auth_headers(admin.id))
    assert response.status_code == 200


# --- Response contract / batch counts ------------------------------------------------------


def test_batch_response_reports_accurate_mixed_outcome_counts(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    records = [
        _record(source_record_id="valid-1"),
        _record(source_record_id="partial-1", severity="not-a-real-severity"),
        _record(source_record_id="quarantined-1", event_time=None),
        _record(source_record_id=None),  # rejected -- missing identity field
    ]
    response = client.post(_URL, json={"records": records}, headers=_bearer(credential))
    assert response.status_code == 201
    body = response.json()
    assert body["total_records"] == 4
    assert body["accepted_records"] == 1
    assert body["partial_records"] == 1
    assert body["quarantined_records"] == 1
    assert body["rejected_records"] == 1
    assert len(body["records"]) == 4


def test_response_carries_a_request_id_header(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    response = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential))
    assert response.headers.get("X-Request-Id")


def test_oversized_batch_is_rejected_before_any_processing(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    records = [_record(source_record_id=f"r-{i}") for i in range(1001)]
    response = client.post(_URL, json={"records": records}, headers=_bearer(credential))
    assert response.status_code == 422


def test_empty_records_list_is_rejected(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    response = client.post(_URL, json={"records": []}, headers=_bearer(credential))
    assert response.status_code == 422


# --- Idempotency (item 12) -----------------------------------------------------------------


def test_repeated_idempotency_key_with_the_same_body_replays_the_first_batch(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    headers = {**_bearer(credential), "Idempotency-Key": "retry-key-1"}
    body = {"records": [_record()]}

    first = client.post(_URL, json=body, headers=headers)
    second = client.post(_URL, json=body, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["batch_id"] == second.json()["batch_id"]

    from app.models.enterprise_ingestion_batch import EnterpriseIngestionBatch

    count = db_session.query(EnterpriseIngestionBatch).filter(EnterpriseIngestionBatch.organization_id == org.id).count()
    assert count == 1  # the retry never created a second batch row


def test_repeated_idempotency_key_with_a_different_body_is_a_conflict(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    headers = {**_bearer(credential), "Idempotency-Key": "retry-key-2"}

    client.post(_URL, json={"records": [_record(source_record_id="one")]}, headers=headers)
    response = client.post(_URL, json={"records": [_record(source_record_id="two")]}, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_domain_level_dedup_still_works_without_any_idempotency_key(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential))
    second = client.post(_URL, json={"records": [_record()]}, headers=_bearer(credential))
    assert second.status_code == 201
    assert second.json()["duplicate_records"] == 1


# --- Intelligence-layer compatibility (item 18) ---------------------------------------------


def test_an_ingested_event_flows_into_existing_analytics(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    admin = _org_admin(db_session, org.id)
    now = datetime.now(timezone.utc).isoformat()
    records = [_record(source_record_id=f"analytics-{i}", event_time=now) for i in range(5)]
    ingest_response = client.post(_URL, json={"records": records}, headers=_bearer(credential))
    assert ingest_response.status_code == 201
    assert ingest_response.json()["accepted_records"] == 5

    summary = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org.id}", headers=dev_auth_headers(admin.id)
    )
    assert summary.status_code == 200
    assert summary.json()["event_count"] == 5


def test_an_ingested_events_temporal_and_provenance_fields_survive_into_the_existing_model(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    admin_b_org = make_org(db_session, "Unrelated Org")
    _ = admin_b_org  # keep organization creation isolated from the assertions below

    client.post(
        _URL,
        json={
            "records": [
                _record(
                    source_record_id="temporal-1",
                    event_time="2026-03-15T12:00:00Z",
                    source_record_version="3",
                    correlation_id="TXN-77",
                )
            ]
        },
        headers=_bearer(credential),
    )

    from app.models.safety_event import SafetyEvent

    event = db_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "temporal-1").one()
    assert event.event_time.replace(tzinfo=timezone.utc) == datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
    assert event.source_record_version == "3"
    assert event.correlation_id == "TXN-77"


# --- Security ---------------------------------------------------------------------------


def test_audit_entries_for_enterprise_ingestion_never_contain_a_secret_or_raw_description(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    sensitive_description = "Confidential: worker medical detail should never leak into audit metadata."
    client.post(
        _URL,
        json={"records": [_record(description=sensitive_description)]},
        headers=_bearer(credential),
    )

    entries = db_session.query(AuditLog).filter(AuditLog.action == "ENTERPRISE_INGESTION_BATCH_COMPLETED").all()
    assert entries
    for entry in entries:
        dumped = str(entry.event_metadata or {})
        assert credential.secret not in dumped
        assert sensitive_description not in dumped
