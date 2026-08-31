import uuid

from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_source_service import knowledge_source_service


def create_org(client, name="Acme Industrial"):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def create_global_source(client):
    return client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "GLOBAL",
            "publisher": "OSHA",
            "name": "29 CFR 1910",
            "source_type": "regulation",
        },
    ).json()


def create_org_source(client, organization_id):
    return client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "organization_id": organization_id,
            "publisher": "Acme Industrial",
            "name": "Internal LOTO Procedure",
            "source_type": "internal_procedure",
        },
    ).json()


def test_create_document_under_global_source(client):
    source = create_global_source(client)

    response = client.post(
        "/api/v1/knowledge/documents",
        json={"source_id": source["id"], "title": "1910.147", "document_type": "regulation_text"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_id"] == source["id"]
    assert body["organization_id"] is None
    assert body["current_version_id"] is None


def test_create_document_under_organization_source(client):
    org = create_org(client)
    source = create_org_source(client, org["id"])

    response = client.post(
        "/api/v1/knowledge/documents",
        json={
            "source_id": source["id"],
            "organization_id": org["id"],
            "title": "LOTO Procedure v1",
            "document_type": "internal_procedure",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["organization_id"] == org["id"]


def test_document_under_organization_source_requires_organization_id(client):
    org = create_org(client)
    source = create_org_source(client, org["id"])

    response = client.post(
        "/api/v1/knowledge/documents",
        json={"source_id": source["id"], "title": "LOTO Procedure", "document_type": "procedure"},
    )

    assert response.status_code == 400


def test_document_cannot_be_attached_to_a_different_organization_than_its_source(client):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    source_a = create_org_source(client, org_a["id"])

    response = client.post(
        "/api/v1/knowledge/documents",
        json={
            "source_id": source_a["id"],
            "organization_id": org_b["id"],
            "title": "LOTO Procedure",
            "document_type": "procedure",
        },
    )

    assert response.status_code == 400


def test_document_under_global_source_rejects_organization_id(client):
    org = create_org(client)
    source = create_global_source(client)

    response = client.post(
        "/api/v1/knowledge/documents",
        json={
            "source_id": source["id"],
            "organization_id": org["id"],
            "title": "1910.147",
            "document_type": "regulation_text",
        },
    )

    assert response.status_code == 400


def test_create_document_under_missing_source_returns_404(client):
    response = client.post(
        "/api/v1/knowledge/documents",
        json={"source_id": str(uuid.uuid4()), "title": "Ghost", "document_type": "procedure"},
    )
    assert response.status_code == 404


def test_get_document_requires_matching_organization_context(client):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    source_a = create_org_source(client, org_a["id"])
    document = client.post(
        "/api/v1/knowledge/documents",
        json={
            "source_id": source_a["id"],
            "organization_id": org_a["id"],
            "title": "LOTO Procedure",
            "document_type": "procedure",
        },
    ).json()

    # Org B cannot fetch org A's document, whether by omitting tenant
    # context entirely or by asserting the wrong organization.
    assert client.get(f"/api/v1/knowledge/documents/{document['id']}").status_code == 404
    assert (
        client.get(
            f"/api/v1/knowledge/documents/{document['id']}",
            params={"organization_id": org_b["id"]},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/knowledge/documents/{document['id']}",
            params={"organization_id": org_a["id"]},
        ).status_code
        == 200
    )


def test_organization_a_cannot_list_organization_b_documents_via_service_layer(db_session):
    # Build orgs/sources/documents directly through the service layer to
    # exercise isolation independent of the HTTP layer (item 14: isolation
    # must hold at both layers).
    from app.schemas.organization import OrganizationCreate
    from app.services.organization_service import organization_service

    org_a = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org A"))
    org_b = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org B"))

    source_a = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type="ORGANIZATION",
            organization_id=org_a.id,
            publisher="Acme",
            name="Org A Source",
            source_type="internal_procedure",
        ),
    )
    knowledge_document_service.create(
        db_session,
        obj_in=KnowledgeDocumentCreate(
            source_id=source_a.id,
            organization_id=org_a.id,
            title="Org A Doc",
            document_type="procedure",
        ),
    )

    org_a_docs = knowledge_document_service.list(db_session, organization_id=org_a.id)
    org_b_docs = knowledge_document_service.list(db_session, organization_id=org_b.id)

    assert len(org_a_docs) == 1
    assert org_b_docs == []
