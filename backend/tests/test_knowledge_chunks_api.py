"""HTTP-level tests for the one read-only chunk endpoint:

    GET /api/v1/knowledge/documents/{document_id}/versions/{version_id}/chunks

No chunk-writing endpoint exists anywhere in this API — see
app/services/chunking_service.py's docstring — chunks here are always
produced by a direct `ingestion_service.ingest()` call (mirroring how
other API test files, e.g. tests/test_knowledge_versions_and_chunks.py,
mix `db_session` setup with `client` HTTP assertions).
"""

import uuid

from app.models.enums import ScopeType
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.ingestion_service import ingestion_service
from app.services.knowledge_source_service import knowledge_source_service
from tests.conftest import dev_auth_headers, load_fixture
from tests.intelligence_test_helpers import make_org_member, make_platform_admin_user


def create_org(client, name="Acme Industrial"):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def make_global_source(db_session, name="29 CFR 1910"):
    return knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL, publisher="OSHA", name=name, source_type="regulation"
        ),
    )


def make_org_source(db_session, organization_id, name="Internal Procedure"):
    return knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.ORGANIZATION,
            organization_id=organization_id,
            publisher="Acme Industrial",
            name=name,
            source_type="internal_procedure",
        ),
    )


def ingest(db_session, source, organization_id=None, filename="sample_procedure.docx"):
    if organization_id is not None:
        organization_id = uuid.UUID(str(organization_id))
    return ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture(filename),
        filename=filename,
        source_id=source.id,
        organization_id=organization_id,
        title="Procedure",
    )


def test_list_chunks_for_a_global_document_version(client, db_session):
    source = make_global_source(db_session)
    outcome = ingest(db_session, source)
    admin = make_platform_admin_user(db_session)

    response = client.get(
        f"/api/v1/knowledge/documents/{outcome.document.id}/versions/{outcome.version_id}/chunks",
        headers=dev_auth_headers(admin.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == outcome.chunk_count
    assert all(c["document_version_id"] == str(outcome.version_id) for c in body)
    assert all(c["document_id"] == str(outcome.document.id) for c in body)
    assert all(c["organization_id"] is None for c in body)
    # Full response shape — the fields a future citation UI needs.
    first = body[0]
    for field in [
        "content_type",
        "quality_status",
        "section_title",
        "section_path",
        "source_reference",
        "chunk_metadata",
    ]:
        assert field in first


def test_list_chunks_for_an_organization_document_requires_the_right_organization_id(
    client, db_session
):
    org = create_org(client)
    source = make_org_source(db_session, org["id"])
    outcome = ingest(db_session, source, organization_id=org["id"])
    member = make_org_member(db_session, uuid.UUID(org["id"]))

    ok = client.get(
        f"/api/v1/knowledge/documents/{outcome.document.id}/versions/{outcome.version_id}/chunks",
        params={"organization_id": org["id"]},
        headers=dev_auth_headers(member.id),
    )
    assert ok.status_code == 200
    assert len(ok.json()) == outcome.chunk_count


def test_list_chunks_404s_without_organization_id_for_an_org_scoped_document(client, db_session):
    org = create_org(client)
    source = make_org_source(db_session, org["id"])
    outcome = ingest(db_session, source, organization_id=org["id"])
    member = make_org_member(db_session, uuid.UUID(org["id"]))

    response = client.get(
        f"/api/v1/knowledge/documents/{outcome.document.id}/versions/{outcome.version_id}/chunks",
        headers=dev_auth_headers(member.id),
    )
    assert response.status_code == 404


def test_list_chunks_404s_for_a_different_organizations_id(client, db_session):
    """Cross-org isolation: another organization's id never reaches this
    document's chunks, even though it's a syntactically valid
    organization_id belonging to a real organization."""
    org_a = create_org(client, name="Acme Industrial")
    org_b = create_org(client, name="Globex Corp")
    source = make_org_source(db_session, org_a["id"])
    outcome = ingest(db_session, source, organization_id=org_a["id"])
    member_b = make_org_member(db_session, uuid.UUID(org_b["id"]))

    response = client.get(
        f"/api/v1/knowledge/documents/{outcome.document.id}/versions/{outcome.version_id}/chunks",
        params={"organization_id": org_b["id"]},
        headers=dev_auth_headers(member_b.id),
    )
    assert response.status_code == 404


def test_list_chunks_404s_for_a_version_belonging_to_a_different_document(client, db_session):
    source = make_global_source(db_session)
    outcome_a = ingest(db_session, source, filename="sample_ppe_policy.txt")
    outcome_b = ingest(db_session, source, filename="sample_evacuation.rtf")
    admin = make_platform_admin_user(db_session)

    # document_a's id, but version_b's id — must not leak document_b's
    # version/chunks just because both belong to the same source.
    response = client.get(
        "/api/v1/knowledge/documents/"
        f"{outcome_a.document.id}/versions/{outcome_b.version_id}/chunks",
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 404


def test_list_chunks_404s_for_an_unknown_document(client, db_session):
    admin = make_platform_admin_user(db_session)
    response = client.get(
        f"/api/v1/knowledge/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}/chunks",
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 404


def test_list_chunks_requires_authentication(client, db_session):
    source = make_global_source(db_session)
    outcome = ingest(db_session, source)

    response = client.get(
        f"/api/v1/knowledge/documents/{outcome.document.id}/versions/{outcome.version_id}/chunks"
    )
    assert response.status_code == 401
