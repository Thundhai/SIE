"""Knowledge-domain tenant isolation tests.

Mirrors tests/test_tenant_isolation.py for the knowledge foundation: an
organization must never be able to see another organization's private
knowledge, and GLOBAL knowledge must be reachable independent of any
tenant.
"""

import uuid

from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.schemas.organization import OrganizationCreate
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_source_service import knowledge_source_service
from app.services.organization_service import organization_service


def create_org(client, name):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def create_org_source(client, organization_id, name="Org Source"):
    return client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "organization_id": organization_id,
            "publisher": "Acme",
            "name": name,
            "source_type": "internal_procedure",
        },
    ).json()


# --- HTTP layer -----------------------------------------------------------


def test_api_organization_a_cannot_retrieve_organization_b_source(client):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    source_a = create_org_source(client, org_a["id"])

    # Not reachable without asserting the right organization...
    assert client.get(f"/api/v1/knowledge/sources/{source_a['id']}").status_code == 404
    # ...and not reachable by asserting the wrong one either. A valid id
    # belonging to a different organization must not leak the row.
    response = client.get(
        f"/api/v1/knowledge/sources/{source_a['id']}", params={"organization_id": org_b["id"]}
    )
    assert response.status_code == 404
    # The owning organization can, of course, retrieve it.
    response = client.get(
        f"/api/v1/knowledge/sources/{source_a['id']}", params={"organization_id": org_a["id"]}
    )
    assert response.status_code == 200


def test_api_organization_source_list_never_crosses_tenants(client):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    create_org_source(client, org_a["id"], name="A Source 1")
    create_org_source(client, org_a["id"], name="A Source 2")
    create_org_source(client, org_b["id"], name="B Source")

    org_a_sources = client.get(
        "/api/v1/knowledge/sources", params={"organization_id": org_a["id"]}
    ).json()
    org_b_sources = client.get(
        "/api/v1/knowledge/sources", params={"organization_id": org_b["id"]}
    ).json()

    assert len(org_a_sources) == 2
    assert all(s["organization_id"] == org_a["id"] for s in org_a_sources)
    assert len(org_b_sources) == 1
    assert org_b_sources[0]["organization_id"] == org_b["id"]


def test_api_global_knowledge_reachable_independent_of_any_tenant(client):
    global_source = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "GLOBAL",
            "publisher": "OSHA",
            "name": "29 CFR 1910",
            "source_type": "regulation",
        },
    ).json()

    # No organization exists yet at all, and none is supplied — global
    # knowledge does not depend on tenant context to be retrievable.
    response = client.get(f"/api/v1/knowledge/sources/{global_source['id']}")
    assert response.status_code == 200
    assert response.json()["organization_id"] is None

    listing = client.get("/api/v1/knowledge/sources").json()
    assert any(s["id"] == global_source["id"] for s in listing)


# --- Service layer ----------------------------------------------------------


def test_service_source_get_returns_none_across_organizations(db_session):
    org_a = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org A"))
    org_b = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org B"))

    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type="ORGANIZATION",
            organization_id=org_a.id,
            publisher="Acme",
            name="Org A Source",
            source_type="internal_procedure",
        ),
    )

    assert knowledge_source_service.get(db_session, id=source.id, organization_id=org_b.id) is None
    assert (
        knowledge_source_service.get(db_session, id=source.id, organization_id=org_a.id)
        is not None
    )
    # And it is not reachable as if it were global, either.
    assert knowledge_source_service.get(db_session, id=source.id, organization_id=None) is None


def test_service_document_list_never_crosses_organizations(db_session):
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
    for i in range(2):
        knowledge_document_service.create(
            db_session,
            obj_in=KnowledgeDocumentCreate(
                source_id=source_a.id,
                organization_id=org_a.id,
                title=f"Doc {i}",
                document_type="procedure",
            ),
        )

    assert len(knowledge_document_service.list(db_session, organization_id=org_a.id)) == 2
    assert knowledge_document_service.list(db_session, organization_id=org_b.id) == []
    assert knowledge_document_service.list(db_session, organization_id=None) == []


def test_service_global_source_visible_with_or_without_context_lookup(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type="GLOBAL",
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )

    assert knowledge_source_service.get(db_session, id=source.id, organization_id=None) is not None
    # A random organization_id must not accidentally match a global row.
    assert (
        knowledge_source_service.get(db_session, id=source.id, organization_id=uuid.uuid4())
        is None
    )
