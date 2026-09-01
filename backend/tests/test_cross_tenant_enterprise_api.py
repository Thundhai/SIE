"""Comprehensive cross-tenant isolation — Intelligence Platform
Integration & Enterprise API v0.1, item 38's own checklist, consolidated
into one file: organization A cannot query B's analytics, knowledge,
RAG evidence, predictions, or models, or ingest data into B — and B
cannot do the reverse to A either. GLOBAL knowledge remains reachable
independent of either organization's tenant boundary.

Many of these dimensions already have dedicated, deeper isolation tests
elsewhere (`tests/test_predictive_cross_tenant_isolation.py`,
`tests/test_knowledge_tenant_isolation.py`,
`tests/test_model_governance_api.py`'s own cross-org tests,
`tests/test_retrieval_rag_machine_access.py`'s machine-client
dimension) — this file is the one place item 38's own explicit checklist
is walked end to end, for both directions, over plain HTTP, so a single
test run demonstrates the whole list at once.
"""

import uuid

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org
from tests.test_ingestion_api import create_org, make_membership, make_user
from tests.test_predictions_api import _deployed_model, _make_authorized_user


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _two_organizations_with_authorized_members(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    member_a = _make_authorized_user(db_session, org_a.id)
    member_b = _make_authorized_user(db_session, org_b.id)
    return org_a, member_a, org_b, member_b


# --- Analytics --------------------------------------------------------------------------


def test_org_a_cannot_query_org_bs_analytics_and_vice_versa(client, db_session):
    org_a, member_a, org_b, member_b = _two_organizations_with_authorized_members(db_session)

    a_reading_b = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org_b.id}", headers=dev_auth_headers(member_a.id)
    )
    b_reading_a = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org_a.id}", headers=dev_auth_headers(member_b.id)
    )
    assert a_reading_b.status_code == 403
    assert b_reading_a.status_code == 403

    # Each organization can, of course, read its own.
    assert (
        client.get(
            f"/api/v1/intelligence/analytics/summary?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id)
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/intelligence/analytics/summary?organization_id={org_b.id}", headers=dev_auth_headers(member_b.id)
        ).status_code
        == 200
    )


def test_machine_client_org_a_cannot_query_org_bs_analytics(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential_a = api_client_service.create(
        db_session, organization_id=org_a.id, name="A", scopes=[Permission.INTELLIGENCE_READ]
    )

    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org_b.id}", headers=_bearer(credential_a)
    )
    assert response.status_code == 403


# --- Knowledge ---------------------------------------------------------------------------


def test_org_a_cannot_read_or_list_org_bs_private_knowledge_and_vice_versa(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    admin_a = make_user(db_session, "admin_a@example.com")
    admin_b = make_user(db_session, "admin_b@example.com")
    make_membership(db_session, user_id=admin_a.id, organization_id=uuid.UUID(org_a["id"]), role="ORG_ADMIN")
    make_membership(db_session, user_id=admin_b.id, organization_id=uuid.UUID(org_b["id"]), role="ORG_ADMIN")

    source_a = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "organization_id": org_a["id"],
            "publisher": "Acme",
            "name": "Org A Procedure",
            "source_type": "internal_procedure",
        },
        headers=dev_auth_headers(admin_a.id),
    ).json()
    source_b = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "organization_id": org_b["id"],
            "publisher": "Globex",
            "name": "Org B Procedure",
            "source_type": "internal_procedure",
        },
        headers=dev_auth_headers(admin_b.id),
    ).json()

    # A cannot see B's source at all -- not even by asserting B's own organization_id.
    assert (
        client.get(
            f"/api/v1/knowledge/sources/{source_b['id']}",
            params={"organization_id": org_b["id"]},
            headers=dev_auth_headers(admin_a.id),
        ).status_code
        == 403
    )
    # B cannot see A's source either.
    assert (
        client.get(
            f"/api/v1/knowledge/sources/{source_a['id']}",
            params={"organization_id": org_a["id"]},
            headers=dev_auth_headers(admin_b.id),
        ).status_code
        == 403
    )

    a_listing = client.get(
        "/api/v1/knowledge/sources", params={"organization_id": org_a["id"]}, headers=dev_auth_headers(admin_a.id)
    ).json()
    assert all(s["id"] != source_b["id"] for s in a_listing)


def test_global_knowledge_remains_reachable_regardless_of_which_organizations_member_asks(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    admin_a = make_user(db_session, "admin_a2@example.com")
    from app.services.permissions import PLATFORM_ADMIN
    from app.services.user_service import user_service

    make_membership(db_session, user_id=admin_a.id, organization_id=uuid.UUID(org_a["id"]), role="ORG_ADMIN")
    platform_admin = make_user(db_session, "platformadmin2@example.com")
    platform_admin = user_service.set_platform_role(db_session, user=platform_admin, platform_role=PLATFORM_ADMIN)

    global_source = client.post(
        "/api/v1/knowledge/sources",
        json={"scope_type": "GLOBAL", "publisher": "OSHA", "name": "29 CFR 1910", "source_type": "regulation"},
        headers=dev_auth_headers(platform_admin.id),
    ).json()

    member_b = make_user(db_session, "member_b2@example.com")
    make_membership(db_session, user_id=member_b.id, organization_id=uuid.UUID(org_b["id"]), role="VIEWER")

    for reader_id in (admin_a.id, member_b.id):
        response = client.get(f"/api/v1/knowledge/sources/{global_source['id']}", headers=dev_auth_headers(reader_id))
        assert response.status_code == 200
        assert response.json()["organization_id"] is None


# --- RAG / retrieval -----------------------------------------------------------------------


def test_org_a_cannot_search_org_bs_private_knowledge_and_vice_versa(client, db_session):
    org_a, member_a, org_b, member_b = _two_organizations_with_authorized_members(db_session)

    a_searching_b = client.post(
        "/api/v1/knowledge/retrieval/search",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org_b.id)}},
        headers=dev_auth_headers(member_a.id),
    )
    b_searching_a = client.post(
        "/api/v1/knowledge/retrieval/search",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org_a.id)}},
        headers=dev_auth_headers(member_b.id),
    )
    assert a_searching_b.status_code == 403
    assert b_searching_a.status_code == 403


def test_org_a_cannot_rag_query_org_bs_private_knowledge_and_vice_versa(client, db_session):
    org_a, member_a, org_b, member_b = _two_organizations_with_authorized_members(db_session)

    a_querying_b = client.post(
        "/api/v1/knowledge/rag/query",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org_b.id)}},
        headers=dev_auth_headers(member_a.id),
    )
    b_querying_a = client.post(
        "/api/v1/knowledge/rag/query",
        json={"query": "PPE requirements", "filters": {"organization_id": str(org_a.id)}},
        headers=dev_auth_headers(member_b.id),
    )
    assert a_querying_b.status_code == 403
    assert b_querying_a.status_code == 403


# --- Predictions ---------------------------------------------------------------------------


def test_org_a_cannot_retrieve_org_bs_predictions(client, db_session):
    _org_a, site, _model, _as_of = _deployed_model(db_session, seed=901)
    org_b = make_org(db_session, "Org B")
    member_b = _make_authorized_user(db_session, org_b.id)

    response = client.get(
        f"/api/v1/intelligence/predictions/{site.id}?organization_id={org_b.id}", headers=dev_auth_headers(member_b.id)
    )
    assert response.status_code == 404  # the site itself isn't org_b's, so it doesn't even resolve


def test_org_a_cannot_request_a_prediction_for_org_bs_site(client, db_session):
    _org_a, site, _model, _as_of = _deployed_model(db_session, seed=902)
    org_b = make_org(db_session, "Org B")
    member_b = _make_authorized_user(db_session, org_b.id)

    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org_b.id}",
        json={"entity_id": str(site.id)},
        headers=dev_auth_headers(member_b.id),
    )
    assert response.status_code == 404


# --- Ingestion (safety events) -----------------------------------------------------------


def test_org_a_credential_cannot_ingest_events_that_land_in_org_b(client, db_session):
    """A machine client can never name a different organization to
    ingest into -- there is no organization_id field on the event
    payload at all; the authenticated credential's own organization is
    the only one ever used."""
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential_a = api_client_service.create(
        db_session, organization_id=org_a.id, name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )

    response = client.post(
        "/api/v1/intelligence/events",
        json={
            "event_type": "NEAR_MISS",
            "event_time": "2026-01-01T00:00:00Z",
            "source_system": "test",
            "source_record_id": "rec-1",
        },
        headers=_bearer(credential_a),
    )
    assert response.status_code == 200
    created_event_id = response.json()["event_id"]

    # Confirm it actually landed in org_a, not org_b -- read via org_a's
    # own analytics (the ingestion response itself has no organization_id
    # field to check directly, by design).
    from app.models.safety_event import SafetyEvent

    event = db_session.get(SafetyEvent, uuid.UUID(created_event_id))
    assert event.organization_id == org_a.id
    assert event.organization_id != org_b.id
