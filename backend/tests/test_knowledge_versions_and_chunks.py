from app.models.enums import QualityStatus
from app.schemas.knowledge_chunk import KnowledgeChunkCreate
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import (
    knowledge_document_version_service,
)
from app.services.knowledge_provenance_service import get_chunk_provenance
from app.services.knowledge_source_service import knowledge_source_service


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


def create_document(client, source_id, **overrides):
    payload = {"source_id": source_id, "title": "1910.147", "document_type": "regulation_text"}
    payload.update(overrides)
    return client.post("/api/v1/knowledge/documents", json=payload).json()


def test_create_document_version(client):
    source = create_global_source(client)
    document = create_document(client, source["id"])

    response = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/versions",
        json={
            "version_label": "v1",
            "content_hash": "hash-1",
            "storage_reference": "placeholder://knowledge/1910.147/v1",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] == document["id"]
    assert body["ingestion_status"] == "RECEIVED"
    assert body["superseded_at"] is None


def test_new_version_becomes_current_and_supersedes_the_previous_one(client):
    source = create_global_source(client)
    document = create_document(client, source["id"])

    v1 = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/versions",
        json={
            "version_label": "v1",
            "content_hash": "hash-1",
            "storage_reference": "placeholder://v1",
        },
    ).json()

    v2 = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/versions",
        json={
            "version_label": "v2",
            "content_hash": "hash-2",
            "storage_reference": "placeholder://v2",
        },
    ).json()

    refetched_document = client.get(f"/api/v1/knowledge/documents/{document['id']}").json()
    assert refetched_document["current_version_id"] == v2["id"]

    versions = client.get(f"/api/v1/knowledge/documents/{document['id']}/versions").json()
    by_id = {v["id"]: v for v in versions}
    assert by_id[v1["id"]]["superseded_at"] is not None
    assert by_id[v2["id"]]["superseded_at"] is None


def test_list_document_versions(client):
    source = create_global_source(client)
    document = create_document(client, source["id"])
    client.post(
        f"/api/v1/knowledge/documents/{document['id']}/versions",
        json={"version_label": "v1", "content_hash": "hash-1", "storage_reference": "ref-1"},
    )
    client.post(
        f"/api/v1/knowledge/documents/{document['id']}/versions",
        json={"version_label": "v2", "content_hash": "hash-2", "storage_reference": "ref-2"},
    )

    response = client.get(f"/api/v1/knowledge/documents/{document['id']}/versions")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_duplicate_content_hash_is_idempotent_not_duplicated(client):
    source = create_global_source(client)
    document = create_document(client, source["id"])
    payload = {
        "version_label": "v1",
        "content_hash": "same-hash",
        "storage_reference": "placeholder://v1",
    }

    first = client.post(f"/api/v1/knowledge/documents/{document['id']}/versions", json=payload)
    second = client.post(f"/api/v1/knowledge/documents/{document['id']}/versions", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    versions = client.get(f"/api/v1/knowledge/documents/{document['id']}/versions").json()
    assert len(versions) == 1


def test_different_documents_may_share_a_content_hash(client):
    source = create_global_source(client)
    doc_a = create_document(client, source["id"], title="Doc A")
    doc_b = create_document(client, source["id"], title="Doc B")
    payload = {"version_label": "v1", "content_hash": "shared-hash", "storage_reference": "ref"}

    response_a = client.post(f"/api/v1/knowledge/documents/{doc_a['id']}/versions", json=payload)
    response_b = client.post(f"/api/v1/knowledge/documents/{doc_b['id']}/versions", json=payload)

    assert response_a.status_code == 201
    assert response_b.status_code == 201
    assert response_a.json()["id"] != response_b.json()["id"]


def test_create_chunks_belonging_to_a_document_version(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type="GLOBAL",
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )
    document = knowledge_document_service.create(
        db_session,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id, title="1910.147", document_type="regulation_text"
        ),
    )
    version = knowledge_document_version_service.create(
        db_session,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1", content_hash="hash-1", storage_reference="ref-1"
        ),
    )

    chunks = knowledge_chunk_service.create_many(
        db_session,
        document_version=version,
        chunks_in=[
            KnowledgeChunkCreate(
                chunk_index=0,
                content="Lockout/tagout procedures shall be established.",
                character_count=48,
                page_number=1,
                section_title="Scope",
                quality_status=QualityStatus.HIGH,
                chunk_metadata={"clause": "1910.147(a)"},
            ),
            KnowledgeChunkCreate(
                chunk_index=1,
                content="Energy control procedures.",
                character_count=27,
                quality_status=QualityStatus.HIGH,
            ),
        ],
    )

    assert len(chunks) == 2
    assert all(c.document_version_id == version.id for c in chunks)
    assert chunks[0].chunk_metadata == {"clause": "1910.147(a)"}

    listed = knowledge_chunk_service.list_for_version(db_session, document_version=version)
    assert [c.chunk_index for c in listed] == [0, 1]


def test_chunk_provenance_traces_full_lineage(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type="GLOBAL",
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )
    document = knowledge_document_service.create(
        db_session,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id, title="1910.147", document_type="regulation_text"
        ),
    )
    version = knowledge_document_version_service.create(
        db_session,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1", content_hash="hash-1", storage_reference="ref-1"
        ),
    )
    (chunk,) = knowledge_chunk_service.create_many(
        db_session,
        document_version=version,
        chunks_in=[
            KnowledgeChunkCreate(
                chunk_index=0,
                content="text",
                character_count=4,
                quality_status=QualityStatus.HIGH,
            )
        ],
    )

    provenance = get_chunk_provenance(db_session, chunk_id=chunk.id)

    assert provenance == {
        "chunk_id": chunk.id,
        "document_version_id": version.id,
        "document_id": document.id,
        "source_id": source.id,
        "organization_id": None,
        "ingestion_status": version.ingestion_status,
    }
