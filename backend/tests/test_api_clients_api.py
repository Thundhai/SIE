"""Machine-client (API client) management API — milestone item 10. Runs
against the ordinary SQLite `client` fixture.
"""

import uuid

from tests.conftest import dev_auth_headers
from tests.test_ingestion_api import create_org, make_membership, make_user


def _org_admin(client, db_session, org_id: str):
    user = make_user(db_session, f"admin-{uuid.uuid4()}@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org_id), role="ORG_ADMIN")
    return user


def test_creating_an_api_client_requires_authentication(client):
    org = create_org(client)
    response = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Integration", "scopes": ["safety_data:write"]},
    )
    assert response.status_code == 401


def test_creating_an_api_client_requires_users_manage_permission(client, db_session):
    org = create_org(client)
    viewer = make_user(db_session, "viewer@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    response = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Integration", "scopes": ["safety_data:write"]},
        headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_org_admin_can_create_an_api_client_and_receives_the_secret_once(client, db_session):
    org = create_org(client)
    admin = _org_admin(client, db_session, org["id"])
    response = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Safelytic Integration", "scopes": ["safety_data:write"]},
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 201
    body = response.json()
    assert "secret" in body
    assert len(body["secret"]) > 20
    assert body["organization_id"] == org["id"]


def test_listing_api_clients_never_exposes_the_secret(client, db_session):
    org = create_org(client)
    admin = _org_admin(client, db_session, org["id"])
    client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Integration", "scopes": ["safety_data:write"]},
        headers=dev_auth_headers(admin.id),
    )
    response = client.get(
        f"/api/v1/organizations/{org['id']}/api-clients", headers=dev_auth_headers(admin.id)
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert "secret" not in body[0]
    assert "hashed_secret" not in body[0]
    assert "secret_prefix" in body[0]


def test_rotating_a_secret_returns_a_new_one_and_invalidates_the_old(client, db_session):
    org = create_org(client)
    admin = _org_admin(client, db_session, org["id"])
    created = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Integration", "scopes": ["safety_data:write"]},
        headers=dev_auth_headers(admin.id),
    ).json()

    rotated = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients/{created['id']}/rotate",
        headers=dev_auth_headers(admin.id),
    )
    assert rotated.status_code == 200
    assert rotated.json()["secret"] != created["secret"]

    old_secret_ingest = client.post(
        "/api/v1/intelligence/events",
        json={
            "event_type": "INCIDENT", "event_time": "2026-06-01T00:00:00Z",
            "source_system": "s", "source_record_id": "1",
        },
        headers={"Authorization": f"Bearer {created['client_id']}:{created['secret']}"},
    )
    assert old_secret_ingest.status_code == 401


def test_revoking_an_api_client_blocks_further_ingestion(client, db_session):
    org = create_org(client)
    admin = _org_admin(client, db_session, org["id"])
    created = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Integration", "scopes": ["safety_data:write"]},
        headers=dev_auth_headers(admin.id),
    ).json()

    revoked = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients/{created['id']}/revoke",
        headers=dev_auth_headers(admin.id),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"

    blocked_ingest = client.post(
        "/api/v1/intelligence/events",
        json={
            "event_type": "INCIDENT", "event_time": "2026-06-01T00:00:00Z",
            "source_system": "s", "source_record_id": "1",
        },
        headers={"Authorization": f"Bearer {created['client_id']}:{created['secret']}"},
    )
    assert blocked_ingest.status_code == 401


def test_an_api_client_cannot_be_looked_up_under_a_different_organization(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    admin_a = _org_admin(client, db_session, org_a["id"])
    admin_b = _org_admin(client, db_session, org_b["id"])

    created = client.post(
        f"/api/v1/organizations/{org_a['id']}/api-clients",
        json={"name": "Integration", "scopes": ["safety_data:write"]},
        headers=dev_auth_headers(admin_a.id),
    ).json()

    response = client.post(
        f"/api/v1/organizations/{org_b['id']}/api-clients/{created['id']}/revoke",
        headers=dev_auth_headers(admin_b.id),
    )
    assert response.status_code == 404
