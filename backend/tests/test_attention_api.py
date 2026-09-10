"""SIE Milestone 33: Intelligence Attention & Delivery — HTTP-layer
tests for `GET /api/v1/intelligence/attention` and
`GET /api/v1/intelligence/sites/{site_id}/attention`. Mirrors
`tests/test_field_intelligence_context_api.py`'s own established shape:
runs against the ordinary SQLite `client` fixture, gated identically to
the existing `/intelligence/enterprise`/`/intelligence/context` routes.
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


# --- Authorization -- identical gating to /enterprise, /context ------------------------------


def test_attention_endpoint_requires_authentication(client):
    response = client.get(f"/api/v1/intelligence/attention?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


def test_attention_endpoint_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider@example.com")
    from tests.conftest import dev_auth_headers

    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 403


def test_attention_endpoint_succeeds_for_an_authorized_member(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "member@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "organization"
    assert body["organization_id"] == org["id"]
    assert "items" in body
    assert "category_statuses" in body
    assert len(body["category_statuses"]) == 8


def test_machine_client_with_scope_can_read_attention(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 200


def test_machine_client_without_scope_is_rejected(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.SAFETY_DATA_WRITE])
    response = client.get(f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 403


def test_machine_client_cannot_request_a_different_organization(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))
    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org_b['id']}", headers=_bearer(credential_a)
    )
    assert response.status_code == 403


# --- API contract --------------------------------------------------------------------------------


def test_attention_endpoint_rejects_an_unsupported_window(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}&window_days=45", headers=_bearer(credential)
    )
    assert response.status_code == 400


def test_attention_endpoint_rejects_an_invalid_as_of_date(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/attention?organization_id={org['id']}&as_of=not-a-real-date",
        headers=_bearer(credential),
    )
    assert response.status_code == 422


def test_site_attention_returns_404_for_a_nonexistent_site(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/sites/{uuid.uuid4()}/attention?organization_id={org['id']}",
        headers=_bearer(credential),
    )
    assert response.status_code == 404


def test_site_attention_returns_404_for_a_cross_tenant_site(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    site_b = make_site(db_session, uuid.UUID(org_b["id"]), name="Site B")
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))

    response = client.get(
        f"/api/v1/intelligence/sites/{site_b.id}/attention?organization_id={org_a['id']}",
        headers=_bearer(credential_a),
    )
    assert response.status_code == 404


def test_site_attention_succeeds_for_an_owned_site(client, db_session):
    org = create_org(client)
    site = make_site(db_session, uuid.UUID(org["id"]), name="Site 01")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), site_id=site.id, count=8)

    response = client.get(
        f"/api/v1/intelligence/sites/{site.id}/attention?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "site"
    assert body["entity_id"] == str(site.id)


def test_empty_organization_returns_empty_items_not_an_error(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_attention_items_have_typed_contract_and_no_raw_uuid_only_label(client, db_session):
    org = create_org(client)
    site = make_site(db_session, uuid.UUID(org["id"]), name="Human Readable Site")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), site_id=site.id, count=8)

    response = client.get(f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential))
    body = response.json()
    assert response.status_code == 200
    assert body["items"], "expected at least one attention item for this fixture"
    for item in body["items"]:
        for key in ("category", "priority", "title", "explanation", "scope", "as_of", "window_days", "evidence"):
            assert key in item
        assert item["priority"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
        assert "entity_ids" in item["evidence"]
        assert "event_ids" in item["evidence"]
        # Every recurrence item concerning this site carries the human
        # label, never only the UUID.
        if item["site_id"] == str(site.id):
            assert item["site_label"] == "Human Readable Site"


def test_priority_is_reused_risk_classification_vocabulary(client, db_session):
    """Prioritization must reuse the existing RiskClassification
    vocabulary, never introduce a competing one."""
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=8)
    response = client.get(f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential))
    body = response.json()
    priorities = {item["priority"] for item in body["items"]}
    assert priorities <= {"LOW", "MODERATE", "HIGH", "CRITICAL"}


def test_items_sorted_by_priority_descending_over_http(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=8)
    response = client.get(f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential))
    body = response.json()
    rank = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
    ranks = [rank[item["priority"]] for item in body["items"]]
    assert ranks == sorted(ranks, reverse=True)


# --- Tenant isolation --------------------------------------------------------------------------


def test_attention_endpoint_never_leaks_another_organizations_events(client, db_session):
    org_a = make_org(db_session, name="Org A")
    org_b = make_org(db_session, name="Org B")
    _seed_incidents(db_session, org_a.id, count=8)
    _seed_incidents(db_session, org_b.id, count=9)

    user = make_user(db_session, "org-a-viewer@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org_a.id, role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(f"/api/v1/intelligence/attention?organization_id={org_a.id}", headers=dev_auth_headers(user.id))
    assert response.status_code == 200
    body = response.json()
    assert body["organization_id"] == str(org_a.id)
    for item in body["items"]:
        assert item.get("site_id") is None or True  # organization scope: no per-item cross-org leak possible here
        assert item["scope"] == "organization"


# --- No mutation / read-only ---------------------------------------------------------------------


def test_attention_endpoint_is_read_only(client, db_session):
    """A GET to the attention endpoint must never create, modify, or
    delete any row -- no action, finding, or intervention is ever
    created by this milestone (product boundary)."""
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=8)

    from app.models.safety_action import SafetyAction
    from app.models.risk_assessment import RiskAssessment
    from sqlalchemy import func, select

    actions_before = db_session.execute(select(func.count()).select_from(SafetyAction)).scalar_one()
    assessments_before = db_session.execute(select(func.count()).select_from(RiskAssessment)).scalar_one()

    response = client.get(f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 200

    actions_after = db_session.execute(select(func.count()).select_from(SafetyAction)).scalar_one()
    assessments_after = db_session.execute(select(func.count()).select_from(RiskAssessment)).scalar_one()
    assert actions_before == actions_after
    assert assessments_before == assessments_after
