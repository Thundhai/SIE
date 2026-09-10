import uuid


def create_org(client, name="Acme Industrial"):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def test_create_site_belongs_to_organization(client):
    org = create_org(client)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/sites",
        json={"name": "Plant 1", "location": "Houston", "country": "US"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Plant 1"
    assert body["organization_id"] == org["id"]
    assert uuid.UUID(body["id"])


def test_list_sites_for_organization(client):
    org = create_org(client)
    client.post(f"/api/v1/organizations/{org['id']}/sites", json={"name": "Plant 1"})
    client.post(f"/api/v1/organizations/{org['id']}/sites", json={"name": "Plant 2"})

    response = client.get(f"/api/v1/organizations/{org['id']}/sites")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {s["name"] for s in body} == {"Plant 1", "Plant 2"}
    assert all(s["organization_id"] == org["id"] for s in body)


def test_create_site_under_missing_organization_returns_404(client):
    response = client.post(
        f"/api/v1/organizations/{uuid.uuid4()}/sites",
        json={"name": "Plant 1"},
    )
    assert response.status_code == 404
