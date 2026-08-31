"""Milestone test item 25: provenance lineage for ingested content.

    File -> Ingestion Job -> Document -> Document Version
        -> Normalized Content -> Chunk
"""

import uuid

from app.models.enums import ScopeType
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.ingestion_service import ingestion_service
from app.services.knowledge_provenance_service import (
    get_chunk_provenance,
    get_ingestion_provenance,
)
from app.services.knowledge_source_service import knowledge_source_service
from tests.conftest import load_fixture


def test_full_lineage_from_ingestion_job_to_chunks(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )

    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_procedure.pdf"),
        filename="sample_procedure.pdf",
        source_id=source.id,
        organization_id=None,
        title="LOTO Procedure",
    )

    provenance = get_ingestion_provenance(db_session, ingestion_job_id=outcome.job.id)

    assert provenance is not None
    assert provenance["file_id"] == outcome.file.id
    assert provenance["ingestion_job_id"] == outcome.job.id
    assert provenance["document_id"] == outcome.document.id
    assert provenance["source_id"] == source.id
    assert provenance["document_version_id"] == outcome.version_id
    assert len(provenance["chunk_ids"]) == outcome.chunk_count == 2

    # And from any one of those chunks, the same chain is traceable back
    # up to the source — the two provenance helpers agree with each other.
    chunk_provenance = get_chunk_provenance(db_session, chunk_id=provenance["chunk_ids"][0])
    assert chunk_provenance["document_version_id"] == outcome.version_id
    assert chunk_provenance["document_id"] == outcome.document.id
    assert chunk_provenance["source_id"] == source.id


def test_provenance_survives_deduplicated_reingestion(db_session):
    """Uploading the same content twice still gives each job its own
    traceable provenance record, even though they share one version."""
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )
    data = load_fixture("sample_ppe_policy.txt")

    first = ingestion_service.ingest(
        db_session,
        file_bytes=data,
        filename="policy_v1.txt",
        source_id=source.id,
        organization_id=None,
        title="PPE Policy",
    )
    second = ingestion_service.ingest(
        db_session,
        file_bytes=data,
        filename="policy_v2.txt",
        source_id=source.id,
        organization_id=None,
        document_id=first.document.id,
    )

    prov_1 = get_ingestion_provenance(db_session, ingestion_job_id=first.job.id)
    prov_2 = get_ingestion_provenance(db_session, ingestion_job_id=second.job.id)

    assert prov_1["file_id"] != prov_2["file_id"]
    assert prov_1["ingestion_job_id"] != prov_2["ingestion_job_id"]
    # reused, per Knowledge Foundation dedup
    assert prov_1["document_version_id"] == prov_2["document_version_id"]
    assert prov_1["chunk_ids"] == prov_2["chunk_ids"]


def test_provenance_for_a_failed_job_has_no_version_or_chunks(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )

    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=b"%PDF-1.4\nnot a real pdf",
        filename="corrupt.pdf",
        source_id=source.id,
        organization_id=None,
        title="Corrupt Upload",
    )

    provenance = get_ingestion_provenance(db_session, ingestion_job_id=outcome.job.id)

    # document was still resolved before extraction failed
    assert provenance["document_id"] == outcome.document.id
    assert provenance["document_version_id"] is None
    assert provenance["chunk_ids"] == []


def test_provenance_returns_none_for_unknown_job(db_session):
    assert get_ingestion_provenance(db_session, ingestion_job_id=uuid.uuid4()) is None
