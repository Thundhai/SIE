import uuid


def create_org(client, name="Acme Industrial"):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def test_create_data_source_belongs_to_organization(client):
    org = create_org(client)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "SCADA Feed", "source_type": "scada"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "SCADA Feed"
    assert body["source_type"] == "scada"
    assert body["organization_id"] == org["id"]
    assert body["last_sync_at"] is None


def test_list_data_sources_for_organization(client):
    org = create_org(client)
    client.post(
        f"/api/v1/organizations/{org['id']}/data-sources",
        json={"name": "SCADA Feed", "source_type": "scada"},
    )

    response = client.get(f"/api/v1/organizations/{org['id']}/data-sources")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["organization_id"] == org["id"]


def test_create_data_source_under_missing_organization_returns_404(client):
    response = client.post(
        f"/api/v1/organizations/{uuid.uuid4()}/data-sources",
        json={"name": "SCADA Feed", "source_type": "scada"},
    )
    assert response.status_code == 404
