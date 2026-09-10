"""HTTP-level ingestion-source tests — Enterprise Data Ingestion &
Validation Foundation v0.1, item 3. `DataSource` (reused as the
"ingestion source" concept) now requires authentication end to end,
closing a pre-existing zero-auth gap -- see
`app/api/v1/data_sources.py`'s own docstring.
"""

import uuid

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.test_ingestion_api import create_org, make_membership, make_user


def _org_admin(db_session, organization_id):
    admin = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    make_membership(db_session, user_id=admin.id, organization_id=organization_id, role="ORG_ADMIN")
    return admin


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def test_create_data_source_belongs_to_organization(client, db_session):
    org = create_org(client)
    admin = _org_admin(db_session, uuid.UUID(org["id"]))

    response = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "SCADA Feed", "source_type": "scada"},
        headers=dev_auth_headers(admin.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "SCADA Feed"
    assert body["source_type"] == "scada"
    assert body["organization_id"] == org["id"]
    assert body["last_sync_at"] is None
    assert body["system_identifier"] is None
    assert body["config_metadata"] == {}


def test_create_data_source_accepts_the_new_optional_fields(client, db_session):
    org = create_org(client)
    admin = _org_admin(db_session, uuid.UUID(org["id"]))

    response = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={
            "name": "SAP ERP",
            "source_type": "erp",
            "system_identifier": "sap-prod-us1",
            "schema_version": "v3",
            "config_metadata": {"timezone": "America/Chicago"},
        },
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["system_identifier"] == "sap-prod-us1"
    assert body["schema_version"] == "v3"
    assert body["config_metadata"] == {"timezone": "America/Chicago"}


def test_create_data_source_can_link_an_api_client_in_the_same_organization(client, db_session):
    org = create_org(client)
    admin = _org_admin(db_session, uuid.UUID(org["id"]))
    credential = api_client_service.create(
        db_session, organization_id=uuid.UUID(org["id"]), name="Integration", scopes=[Permission.SAFETY_DATA_WRITE]
    )

    response = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "SAP ERP", "source_type": "erp", "api_client_id": str(credential.api_client.id)},
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 201
    assert response.json()["api_client_id"] == str(credential.api_client.id)


def test_create_data_source_rejects_an_api_client_from_a_different_organization(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    admin_a = _org_admin(db_session, uuid.UUID(org_a["id"]))
    credential_b = api_client_service.create(
        db_session, organization_id=uuid.UUID(org_b["id"]), name="Org B Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )

    response = client.post(
        f"/api/v1/organizations/{org_a['id']}/data-sources",
        json={"name": "Cross-tenant", "source_type": "erp", "api_client_id": str(credential_b.api_client.id)},
        headers=dev_auth_headers(admin_a.id),
    )
    assert response.status_code == 404


def test_list_data_sources_for_organization(client, db_session):
    org = create_org(client)
    admin = _org_admin(db_session, uuid.UUID(org["id"]))
    client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "SCADA Feed", "source_type": "scada"},
        headers=dev_auth_headers(admin.id),
    )

    response = client.get(f"/api/v1/organizations/{org['id']}/data-sources", headers=dev_auth_headers(admin.id))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["organization_id"] == org["id"]


def test_create_data_source_under_missing_organization_returns_404(client, db_session):
    someone = make_user(db_session, "someone@example.com")
    response = client.post(
        f"/api/v1/organizations/{uuid.uuid4()}/data-sources",
        json={"name": "SCADA Feed", "source_type": "scada"},
        headers=dev_auth_headers(someone.id),
    )
    assert response.status_code == 404


def test_create_data_source_requires_authentication(client):
    org = create_org(client)
    response = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources", json={"name": "SCADA Feed", "source_type": "scada"}
    )
    assert response.status_code == 401


def test_list_data_sources_requires_authentication(client):
    org = create_org(client)
    response = client.get(f"/api/v1/organizations/{org['id']}/data-sources")
    assert response.status_code == 401


def test_get_data_source_requires_safety_data_read_in_the_organization(client, db_session):
    org = create_org(client)
    admin = _org_admin(db_session, uuid.UUID(org["id"]))
    created = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "SCADA Feed", "source_type": "scada"},
        headers=dev_auth_headers(admin.id),
    ).json()

    response = client.get(
        f"/api/v1/organizations/{org['id']}/data-sources/{created['id']}", headers=dev_auth_headers(admin.id)
    )
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_data_source_404s_for_an_unknown_id(client, db_session):
    org = create_org(client)
    admin = _org_admin(db_session, uuid.UUID(org["id"]))
    response = client.get(
        f"/api/v1/organizations/{org['id']}/data-sources/{uuid.uuid4()}", headers=dev_auth_headers(admin.id)
    )
    assert response.status_code == 404


def test_update_data_source_status_toggles_active_inactive(client, db_session):
    org = create_org(client)
    admin = _org_admin(db_session, uuid.UUID(org["id"]))
    created = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "SCADA Feed", "source_type": "scada"},
        headers=dev_auth_headers(admin.id),
    ).json()
    assert created["status"] == "active"

    response = client.patch(
        f"/api/v1/organizations/{org['id']}/data-sources/{created['id']}/status",
        json={"status": "inactive"},
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "inactive"


# --- Cross-tenant ---------------------------------------------------------------------------


def test_org_a_cannot_read_or_list_org_bs_data_sources(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    admin_a = _org_admin(db_session, uuid.UUID(org_a["id"]))
    admin_b = _org_admin(db_session, uuid.UUID(org_b["id"]))
    source_b = client.post(
        f"/api/v1/organizations/{org_b['id']}/data-sources",
        json={"name": "Org B Source", "source_type": "erp"},
        headers=dev_auth_headers(admin_b.id),
    ).json()

    assert (
        client.get(
            f"/api/v1/organizations/{org_b['id']}/data-sources/{source_b['id']}", headers=dev_auth_headers(admin_a.id)
        ).status_code
        == 403
    )
    listing = client.get(f"/api/v1/organizations/{org_a['id']}/data-sources", headers=dev_auth_headers(admin_a.id))
    assert listing.status_code == 200
    assert listing.json() == []


def test_machine_client_scoped_to_org_a_cannot_create_a_source_in_org_b(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    credential_a = api_client_service.create(
        db_session, organization_id=uuid.UUID(org_a["id"]), name="A", scopes=[Permission.SAFETY_DATA_WRITE]
    )

    response = client.post(
        f"/api/v1/organizations/{org_b['id']}/data-sources",
        json={"name": "Cross-tenant", "source_type": "erp"},
        headers=_bearer(credential_a),
    )
    assert response.status_code == 403


def test_machine_client_with_safety_data_write_can_create_its_own_organizations_source(client, db_session):
    org = create_org(client)
    credential = api_client_service.create(
        db_session, organization_id=uuid.UUID(org["id"]), name="Integration", scopes=[Permission.SAFETY_DATA_WRITE]
    )

    response = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "Integration Source", "source_type": "erp"},
        headers=_bearer(credential),
    )
    assert response.status_code == 201


def test_machine_client_without_safety_data_write_cannot_create_a_source(client, db_session):
    org = create_org(client)
    credential = api_client_service.create(
        db_session, organization_id=uuid.UUID(org["id"]), name="Read-only", scopes=[Permission.SAFETY_DATA_READ]
    )

    response = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "Integration Source", "source_type": "erp"},
        headers=_bearer(credential),
    )
    assert response.status_code == 403
