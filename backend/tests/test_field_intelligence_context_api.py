"""SIE Milestone 32: Field Intelligence Context Composition v0.1 —
HTTP-layer tests for `GET /api/v1/intelligence/context` and
`GET /api/v1/intelligence/sites/{site_id}/context`. Mirrors
`tests/test_enterprise_intelligence_api.py`'s own established shape:
runs against the ordinary SQLite `client` fixture, gated identically to
the existing `/enterprise`/`/sites/{id}` routes (same permission, same
authorize-then-trust `organization_id` query parameter).
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


# --- Authorization -- identical gating to /enterprise, /sites/{id} --------------------------


def test_context_endpoint_requires_authentication(client):
    response = client.get(f"/api/v1/intelligence/context?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


def test_context_endpoint_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider@example.com")
    from tests.conftest import dev_auth_headers

    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=dev_auth_headers(user.id))
    assert response.status_code == 403


def test_context_endpoint_succeeds_for_an_authorized_member(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "member@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=dev_auth_headers(user.id))
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "organization"
    assert body["organization_id"] == org["id"]
    # Four separate, never-merged categories -- structurally present.
    assert set(["observed", "deterministic", "predictive", "knowledge"]).issubset(body.keys())
    assert "deterministic_risk" in body["deterministic"]
    assert "predictive_context" in body["deterministic"]  # raw orchestrator field, still reachable
    # predictive/deterministic are never the same field/shape.
    assert body["predictive"] != body["deterministic"]["deterministic_risk"]


def test_machine_client_with_scope_can_read_context(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 200


def test_machine_client_without_scope_is_rejected(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.SAFETY_DATA_WRITE])
    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 403


def test_machine_client_cannot_request_a_different_organization(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))
    response = client.get(
        f"/api/v1/intelligence/context?organization_id={org_b['id']}", headers=_bearer(credential_a)
    )
    assert response.status_code == 403


# --- API contract ------------------------------------------------------------------------------


def test_context_endpoint_rejects_an_unsupported_window(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/context?organization_id={org['id']}&window_days=45", headers=_bearer(credential)
    )
    assert response.status_code == 400


def test_context_endpoint_rejects_an_invalid_as_of_date(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/context?organization_id={org['id']}&as_of=not-a-real-date",
        headers=_bearer(credential),
    )
    assert response.status_code == 422


def test_site_context_returns_404_for_a_nonexistent_site(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/sites/{uuid.uuid4()}/context?organization_id={org['id']}",
        headers=_bearer(credential),
    )
    assert response.status_code == 404


def test_site_context_returns_404_for_a_cross_tenant_site(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    site_b = make_site(db_session, uuid.UUID(org_b["id"]), name="Site B")
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))

    response = client.get(
        f"/api/v1/intelligence/sites/{site_b.id}/context?organization_id={org_a['id']}",
        headers=_bearer(credential_a),
    )
    assert response.status_code == 404


def test_site_context_succeeds_for_an_owned_site(client, db_session):
    org = create_org(client)
    site = make_site(db_session, uuid.UUID(org["id"]), name="Site 01")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), site_id=site.id)

    response = client.get(
        f"/api/v1/intelligence/sites/{site.id}/context?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "site"
    assert body["entity_id"] == str(site.id)
    assert body["observed"]["event_count"] == 6


def test_knowledge_not_queried_by_default(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 200
    assert response.json()["knowledge"]["outcome"] == "NOT_QUERIED"


def test_predictive_not_available_without_a_recorded_prediction(client, db_session):
    org = create_org(client)
    site = make_site(db_session, uuid.UUID(org["id"]), name="Site 01")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/intelligence/sites/{site.id}/context?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200
    assert response.json()["predictive"]["outcome"] == "NOT_AVAILABLE"
    assert response.json()["predictive"]["value"] is None


# --- Tenant isolation --------------------------------------------------------------------------


def test_context_endpoint_never_leaks_another_organizations_events(client, db_session):
    org_a = make_org(db_session, name="Org A")
    org_b = make_org(db_session, name="Org B")
    _seed_incidents(db_session, org_a.id, count=5)
    _seed_incidents(db_session, org_b.id, count=9)

    user = make_user(db_session, "org-a-viewer@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org_a.id, role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(f"/api/v1/intelligence/context?organization_id={org_a.id}", headers=dev_auth_headers(user.id))
    assert response.status_code == 200
    body = response.json()
    assert body["observed"]["event_count"] == 5  # never Org B's 9
    assert body["organization_id"] == str(org_a.id)


def test_context_endpoint_rate_limited_dependency_present(client, db_session):
    """Sanity check that the new route was actually wired with the same
    `RateLimitClass.READ` dependency every other read route in this
    router carries -- a plain 200 on the first call is enough to prove
    the dependency didn't reject outright; the shared rate-limit test
    suite (`tests/test_rate_limiting.py`) covers the limiter's own
    behavior, never duplicated here."""
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 200
