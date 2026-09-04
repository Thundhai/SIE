"""SIE Milestone 22: Enterprise Intelligence & Risk Analytics Foundation
v0.1 — HTTP-layer tests for `GET /api/v1/intelligence/enterprise` and
`GET /api/v1/intelligence/sites/{site_id}`: authorization, tenant
isolation, and API-contract coverage (milestone items 15, 16, 20).
Mirrors `tests/test_intelligence_api.py`'s own established shape; runs
against the ordinary SQLite `client` fixture.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site
from tests.test_ingestion_api import create_org, make_membership, make_user

AS_OF = datetime.now(timezone.utc)


def _make_client_credential(db_session, org_id, *, scopes=None):
    scopes = scopes if scopes is not None else [Permission.INTELLIGENCE_READ]
    return api_client_service.create(db_session, organization_id=org_id, name="Test Integration", scopes=scopes)


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _seed_incidents(db_session, org_id, *, site_id=None, count=6):
    for i in range(count):
        event = make_safety_event(
            organization_id=org_id,
            site_id=site_id,
            event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i),
            ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    db_session.commit()


# --- Authorization (milestone item 15) -----------------------------------------------


def test_enterprise_endpoint_requires_authentication(client):
    response = client.get(f"/api/v1/intelligence/enterprise?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


def test_enterprise_endpoint_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider@example.com")
    from tests.conftest import dev_auth_headers

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 403


def test_enterprise_endpoint_succeeds_for_an_authorized_member(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "member@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "organization"
    assert body["organization_id"] == org["id"]
    assert "deterministic_risk" in body
    assert "provenance" in body
    assert "data_sufficiency" in body


def test_machine_client_with_scope_can_read_enterprise_intelligence(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200


def test_machine_client_without_scope_is_rejected(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.SAFETY_DATA_WRITE])
    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 403


def test_machine_client_cannot_request_a_different_organization(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))
    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org_b['id']}", headers=_bearer(credential_a)
    )
    assert response.status_code == 403


# --- API contract (milestone item 20) -------------------------------------------------


def test_enterprise_endpoint_rejects_an_unsupported_window(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}&window_days=45", headers=_bearer(credential)
    )
    assert response.status_code == 400


def test_enterprise_endpoint_accepts_every_documented_window(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    for window in (7, 30, 90, 180):
        response = client.get(
            f"/api/v1/intelligence/enterprise?organization_id={org['id']}&window_days={window}",
            headers=_bearer(credential),
        )
        assert response.status_code == 200
        assert response.json()["window_days"] == window


def test_enterprise_endpoint_rejects_an_invalid_as_of_date(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}&as_of=not-a-real-date",
        headers=_bearer(credential),
    )
    assert response.status_code == 422


def test_site_endpoint_returns_404_for_a_nonexistent_site(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/sites/{uuid.uuid4()}?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 404


def test_site_endpoint_returns_404_for_a_cross_tenant_site(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    site_b = make_site(db_session, uuid.UUID(org_b["id"]), name="Site B")
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))

    response = client.get(
        f"/api/v1/intelligence/sites/{site_b.id}?organization_id={org_a['id']}", headers=_bearer(credential_a)
    )
    assert response.status_code == 404


def test_site_endpoint_succeeds_for_an_owned_site(client, db_session):
    org = create_org(client)
    site = make_site(db_session, uuid.UUID(org["id"]), name="Site 01")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), site_id=site.id)

    response = client.get(
        f"/api/v1/intelligence/sites/{site.id}?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "site"
    assert body["entity_id"] == str(site.id)


# --- Tenant isolation (milestone item 16) ---------------------------------------------


def test_enterprise_endpoint_never_leaks_another_organizations_events(client, db_session):
    org_a = make_org(db_session, name="Org A")
    org_b = make_org(db_session, name="Org B")
    _seed_incidents(db_session, org_a.id, count=5)
    _seed_incidents(db_session, org_b.id, count=9)

    user = make_user(db_session, "org-a-viewer@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org_a.id, role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org_a.id}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data_sufficiency"]["event_count"] == 5  # never Org B's 9
    assert body["organization_id"] == str(org_a.id)


def test_provenance_never_leaks_a_foreign_organizations_event_ids(client, db_session):
    org_a = make_org(db_session, name="Org A")
    org_b = make_org(db_session, name="Org B")
    _seed_incidents(db_session, org_a.id, count=2)
    b_events = []
    for i in range(3):
        event = make_safety_event(
            organization_id=org_b.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
        b_events.append(event)
    db_session.commit()

    user = make_user(db_session, "org-a-viewer-2@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org_a.id, role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org_a.id}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 200
    evidence_ids = set(response.json()["provenance"]["evidence_sample_event_ids"])
    assert evidence_ids.isdisjoint({str(e.id) for e in b_events})


def test_org_a_cannot_read_org_bs_site_via_the_site_endpoint(client, db_session):
    org_a = create_org(client, name="Org A2")
    org_b = create_org(client, name="Org B2")
    site_b = make_site(db_session, uuid.UUID(org_b["id"]), name="Site B2")
    user = make_user(db_session, "org-a2-viewer@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org_a["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(
        f"/api/v1/intelligence/sites/{site_b.id}?organization_id={org_a['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 404
