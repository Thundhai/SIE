import uuid


def create_org(client, name="Acme Industrial"):
    return client.post(
        "/api/v1/organizations",
        json={"name": name, "industry": "manufacturing", "country": "US"},
    )


def test_create_organization(client):
    response = create_org(client)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Industrial"
    assert body["industry"] == "manufacturing"
    assert body["status"] == "active"
    assert uuid.UUID(body["id"])
    assert "created_at" in body
    assert "updated_at" in body


def test_get_organization(client):
    created = create_org(client).json()

    response = client.get(f"/api/v1/organizations/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_organization_not_found(client):
    response = client.get(f"/api/v1/organizations/{uuid.uuid4()}")
    assert response.status_code == 404
