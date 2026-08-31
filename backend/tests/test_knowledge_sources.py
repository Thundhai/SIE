import uuid


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


def test_create_global_knowledge_source(client):
    response = client.post("/api/v1/knowledge/sources", json=global_source_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["scope_type"] == "GLOBAL"
    assert body["organization_id"] is None
    assert body["verification_status"] == "PENDING"
    assert uuid.UUID(body["id"])


def test_create_organization_knowledge_source(client):
    org = create_org(client)

    response = client.post("/api/v1/knowledge/sources", json=org_source_payload(org["id"]))

    assert response.status_code == 201
    body = response.json()
    assert body["scope_type"] == "ORGANIZATION"
    assert body["organization_id"] == org["id"]


def test_global_source_has_no_organization_id(client):
    body = client.post("/api/v1/knowledge/sources", json=global_source_payload()).json()
    assert body["organization_id"] is None


def test_global_source_rejects_organization_id(client):
    org = create_org(client)

    response = client.post(
        "/api/v1/knowledge/sources",
        json=global_source_payload(organization_id=org["id"]),
    )

    # Rejected by the Pydantic model_validator before it ever reaches the
    # service layer.
    assert response.status_code == 422


def test_organization_source_requires_organization_id(client):
    response = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "publisher": "Acme Industrial",
            "name": "Internal Procedure",
            "source_type": "internal_procedure",
        },
    )

    assert response.status_code == 422


def test_organization_source_requires_existing_organization(client):
    response = client.post(
        "/api/v1/knowledge/sources",
        json=org_source_payload(str(uuid.uuid4())),
    )

    assert response.status_code == 400


def test_global_source_retrievable_without_any_tenant_context(client):
    created = client.post("/api/v1/knowledge/sources", json=global_source_payload()).json()

    response = client.get(f"/api/v1/knowledge/sources/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_global_listing_excludes_organization_sources(client):
    org = create_org(client)
    client.post("/api/v1/knowledge/sources", json=global_source_payload())
    client.post("/api/v1/knowledge/sources", json=org_source_payload(org["id"]))

    response = client.get("/api/v1/knowledge/sources")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["scope_type"] == "GLOBAL"


def test_organization_listing_excludes_global_sources(client):
    org = create_org(client)
    client.post("/api/v1/knowledge/sources", json=global_source_payload())
    client.post("/api/v1/knowledge/sources", json=org_source_payload(org["id"]))

    response = client.get("/api/v1/knowledge/sources", params={"organization_id": org["id"]})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["scope_type"] == "ORGANIZATION"
    assert body[0]["organization_id"] == org["id"]
