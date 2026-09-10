import uuid

from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org_member, make_platform_admin_user


def create_org(client, name="Acme Industrial"):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def global_source_payload(**overrides):
    payload = {
        "scope_type": "GLOBAL",
        "publisher": "OSHA",
        "name": "29 CFR 1910",
        "source_type": "regulation",
        "jurisdiction": "US",
    }
    payload.update(overrides)
    return payload


def org_source_payload(organization_id, **overrides):
    payload = {
        "scope_type": "ORGANIZATION",
        "organization_id": organization_id,
        "publisher": "Acme Industrial",
        "name": "Internal Lockout/Tagout Procedure",
        "source_type": "internal_procedure",
    }
    payload.update(overrides)
    return payload


def test_create_global_knowledge_source(client, db_session):
    admin = make_platform_admin_user(db_session)
    response = client.post(
        "/api/v1/knowledge/sources", json=global_source_payload(), headers=dev_auth_headers(admin.id)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["scope_type"] == "GLOBAL"
    assert body["organization_id"] is None
    assert body["verification_status"] == "PENDING"
    assert uuid.UUID(body["id"])


def test_create_global_knowledge_source_requires_authentication(client):
    response = client.post("/api/v1/knowledge/sources", json=global_source_payload())
    assert response.status_code == 401


def test_create_global_knowledge_source_requires_platform_admin_not_just_any_authenticated_user(client, db_session):
    org = create_org(client)
    ordinary_member = make_org_member(db_session, uuid.UUID(org["id"]))
    response = client.post(
        "/api/v1/knowledge/sources", json=global_source_payload(), headers=dev_auth_headers(ordinary_member.id)
    )
    assert response.status_code == 403


def test_create_organization_knowledge_source(client, db_session):
    org = create_org(client)
    member = make_org_member(db_session, uuid.UUID(org["id"]))

    response = client.post(
        "/api/v1/knowledge/sources", json=org_source_payload(org["id"]), headers=dev_auth_headers(member.id)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["scope_type"] == "ORGANIZATION"
    assert body["organization_id"] == org["id"]


def test_create_organization_knowledge_source_requires_knowledge_manage_in_that_organization(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    member_of_b_only = make_org_member(db_session, uuid.UUID(org_b["id"]))

    response = client.post(
        "/api/v1/knowledge/sources", json=org_source_payload(org_a["id"]), headers=dev_auth_headers(member_of_b_only.id)
    )
    assert response.status_code == 403


def test_global_source_has_no_organization_id(client, db_session):
    admin = make_platform_admin_user(db_session)
    body = client.post(
        "/api/v1/knowledge/sources", json=global_source_payload(), headers=dev_auth_headers(admin.id)
    ).json()
    assert body["organization_id"] is None


def test_global_source_rejects_organization_id(client, db_session):
    org = create_org(client)
    admin = make_platform_admin_user(db_session)

    response = client.post(
        "/api/v1/knowledge/sources",
        json=global_source_payload(organization_id=org["id"]),
        headers=dev_auth_headers(admin.id),
    )

    # Rejected by the Pydantic model_validator before it ever reaches the
    # service layer.
    assert response.status_code == 422


def test_organization_source_requires_organization_id(client, db_session):
    org = create_org(client)
    member = make_org_member(db_session, uuid.UUID(org["id"]))

    response = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "publisher": "Acme Industrial",
            "name": "Internal Procedure",
            "source_type": "internal_procedure",
        },
        headers=dev_auth_headers(member.id),
    )

    assert response.status_code == 422


def test_organization_source_requires_existing_organization(client, db_session):
    admin = make_platform_admin_user(db_session)

    response = client.post(
        "/api/v1/knowledge/sources", json=org_source_payload(str(uuid.uuid4())), headers=dev_auth_headers(admin.id)
    )

    # A platform admin's own authorization check never depends on the
    # named organization actually existing (app/services/authorization_service.py's
    # `can()` grants ALL_PERMISSIONS to a PLATFORM_ADMIN before it ever
    # looks up membership) -- so this reaches the service layer exactly
    # as before this milestone, which still reports 400 for a
    # nonexistent organization.
    assert response.status_code == 400


def test_global_source_retrievable_without_any_tenant_context(client, db_session):
    admin = make_platform_admin_user(db_session)
    created = client.post(
        "/api/v1/knowledge/sources", json=global_source_payload(), headers=dev_auth_headers(admin.id)
    ).json()

    # Retrieval only requires *authentication*, not platform-admin --
    # any authenticated caller reads already-published GLOBAL knowledge.
    other_org = create_org(client)
    ordinary_member = make_org_member(db_session, uuid.UUID(other_org["id"]))
    response = client.get(f"/api/v1/knowledge/sources/{created['id']}", headers=dev_auth_headers(ordinary_member.id))

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_global_listing_excludes_organization_sources(client, db_session):
    org = create_org(client)
    admin = make_platform_admin_user(db_session)
    member = make_org_member(db_session, uuid.UUID(org["id"]))
    client.post("/api/v1/knowledge/sources", json=global_source_payload(), headers=dev_auth_headers(admin.id))
    client.post("/api/v1/knowledge/sources", json=org_source_payload(org["id"]), headers=dev_auth_headers(member.id))

    response = client.get("/api/v1/knowledge/sources", headers=dev_auth_headers(member.id))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["scope_type"] == "GLOBAL"


def test_organization_listing_excludes_global_sources(client, db_session):
    org = create_org(client)
    admin = make_platform_admin_user(db_session)
    member = make_org_member(db_session, uuid.UUID(org["id"]))
    client.post("/api/v1/knowledge/sources", json=global_source_payload(), headers=dev_auth_headers(admin.id))
    client.post("/api/v1/knowledge/sources", json=org_source_payload(org["id"]), headers=dev_auth_headers(member.id))

    response = client.get(
        "/api/v1/knowledge/sources", params={"organization_id": org["id"]}, headers=dev_auth_headers(member.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["scope_type"] == "ORGANIZATION"
    assert body[0]["organization_id"] == org["id"]
