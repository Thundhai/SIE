"""Tenant isolation tests.

These are the tests that matter most for SIE: an organization must never be
able to see, fetch, or list another organization's data, whether through
the HTTP API or by calling the service layer directly.
"""

import uuid

from app.schemas.data_source import DataSourceCreate
from app.schemas.organization import OrganizationCreate
from app.schemas.site import SiteCreate
from app.services.data_source_service import data_source_service
from app.services.organization_service import organization_service
from app.services.site_service import site_service
from tests.conftest import dev_auth_headers
from tests.test_ingestion_api import make_membership, make_user


def create_org(client, name):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def _org_admin(db_session, organization_id):
    admin = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    make_membership(db_session, user_id=admin.id, organization_id=organization_id, role="ORG_ADMIN")
    return admin


def test_api_site_list_is_scoped_per_organization(client):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")

    client.post(f"/api/v1/organizations/{org_a['id']}/sites", json={"name": "A Plant"})

    org_b_sites = client.get(f"/api/v1/organizations/{org_b['id']}/sites").json()
    org_a_sites = client.get(f"/api/v1/organizations/{org_a['id']}/sites").json()

    assert org_b_sites == []
    assert len(org_a_sites) == 1


def test_api_data_source_list_is_scoped_per_organization(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    admin_a = _org_admin(db_session, uuid.UUID(org_a["id"]))
    admin_b = _org_admin(db_session, uuid.UUID(org_b["id"]))

    client.post(
        f"/api/v1/organizations/{org_a['id']}/data-sources",
        json={"name": "A Feed", "source_type": "scada"},
        headers=dev_auth_headers(admin_a.id),
    )

    assert (
        client.get(f"/api/v1/organizations/{org_b['id']}/data-sources", headers=dev_auth_headers(admin_b.id)).json()
        == []
    )
    assert (
        len(
            client.get(
                f"/api/v1/organizations/{org_a['id']}/data-sources", headers=dev_auth_headers(admin_a.id)
            ).json()
        )
        == 1
    )


def test_service_get_returns_none_for_wrong_organization(db_session):
    org_a = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org A"))
    org_b = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org B"))

    site = site_service.create(
        db_session,
        organization_id=org_a.id,
        obj_in=SiteCreate(name="A Plant"),
    )

    # Fetching org A's site while scoped to org B must not leak the record,
    # even though the id is valid and belongs to a real row.
    assert site_service.get(db_session, organization_id=org_b.id, id=site.id) is None
    assert site_service.get(db_session, organization_id=org_a.id, id=site.id) is not None


def test_service_list_never_crosses_organizations(db_session):
    org_a = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org A"))
    org_b = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org B"))

    for i in range(3):
        data_source_service.create(
            db_session,
            organization_id=org_a.id,
            obj_in=DataSourceCreate(name=f"Feed {i}", source_type="scada"),
        )
    data_source_service.create(
        db_session,
        organization_id=org_b.id,
        obj_in=DataSourceCreate(name="Other Org Feed", source_type="scada"),
    )

    org_a_sources = data_source_service.list(db_session, organization_id=org_a.id)
    org_b_sources = data_source_service.list(db_session, organization_id=org_b.id)

    assert len(org_a_sources) == 3
    assert all(ds.organization_id == org_a.id for ds in org_a_sources)
    assert len(org_b_sources) == 1
    assert org_b_sources[0].organization_id == org_b.id
