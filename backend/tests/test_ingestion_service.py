"""Service-layer ingestion tests — milestone items 9, 17 (real
enforcement), 21, 22, 23, 24.
"""

import pytest

from app.models.enums import IngestionJobStatus, ScopeType
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.ingestion_service import IngestionRequestError, ingestion_service
from app.services.knowledge_document_version_service import knowledge_document_version_service
from app.services.knowledge_source_service import knowledge_source_service
from tests.conftest import load_fixture


def make_global_source(db_session, name="29 CFR 1910"):
    return knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL, publisher="OSHA", name=name, source_type="regulation"
        ),
    )


# --- 23. Document version creation -----------------------------------------


def test_ingest_creates_document_and_version(db_session):
    source = make_global_source(db_session)
    data = load_fixture("sample_procedure.pdf")

    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=data,
        filename="sample_procedure.pdf",
        source_id=source.id,
        organization_id=None,
        title="LOTO Procedure",
    )

    assert outcome.document is not None
    assert outcome.document.source_id == source.id
    assert outcome.document.title == "LOTO Procedure"
    assert outcome.version_id is not None
    assert outcome.chunk_count == 2
    assert outcome.job.status == IngestionJobStatus.COMPLETED


# --- 9 / 24. Duplicate file / duplicate content_hash handling -------------


def test_duplicate_content_hash_reuses_the_existing_version_not_a_new_one(db_session):
    source = make_global_source(db_session)
    data = load_fixture("sample_procedure.pdf")

    first = ingestion_service.ingest(
        db_session,
        file_bytes=data,
        filename="upload_1.pdf",
        source_id=source.id,
        organization_id=None,
        title="LOTO Procedure",
    )
    second = ingestion_service.ingest(
        db_session,
        file_bytes=data,  # byte-identical, different filename
        filename="upload_2.pdf",
        source_id=source.id,
        organization_id=None,
        document_id=first.document.id,
    )

    # Same version reused, not duplicated...
    assert second.version_id == first.version_id
    assert second.chunk_count == first.chunk_count
    versions = knowledge_document_version_service.list_for_document(
        db_session, document=first.document
    )
    assert len(versions) == 1

    # ...but each upload is still its own traceable file + job event.
    assert second.file.id != first.file.id
    assert second.job.id != first.job.id


def test_different_content_under_the_same_document_creates_a_second_version(db_session):
    source = make_global_source(db_session)
    first = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_ppe_policy.txt"),
        filename="policy_v1.txt",
        source_id=source.id,
        organization_id=None,
        title="PPE Policy",
    )
    second = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_evacuation.rtf"),  # genuinely different content
        filename="policy_v2.rtf",
        source_id=source.id,
        organization_id=None,
        document_id=first.document.id,
    )

    assert second.version_id != first.version_id
    versions = knowledge_document_version_service.list_for_document(
        db_session, document=first.document
    )
    assert len(versions) == 2


# --- 21. Ingestion job lifecycle -------------------------------------------


def test_ingestion_job_lifecycle_reaches_completed(db_session):
    source = make_global_source(db_session)

    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_ppe_policy.txt"),
        filename="sample_ppe_policy.txt",
        source_id=source.id,
        organization_id=None,
        title="PPE Policy",
    )

    job = outcome.job
    assert job.status == IngestionJobStatus.COMPLETED
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.completed_at >= job.started_at
    assert job.file_id == outcome.file.id
    assert job.source_id == source.id
    assert job.document_id == outcome.document.id
    assert job.error_message is None


# --- 22. Failed ingestion handling ------------------------------------------


def test_corrupt_file_produces_a_failed_job_not_an_exception(db_session):
    source = make_global_source(db_session)
    fake_pdf = b"%PDF-1.4\nthis is not actually a valid pdf body"

    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=fake_pdf,
        filename="corrupt.pdf",
        source_id=source.id,
        organization_id=None,
        title="Corrupt Upload",
    )

    assert outcome.job.status == IngestionJobStatus.FAILED
    assert outcome.job.error_message is not None
    assert outcome.file.ingestion_status == IngestionJobStatus.FAILED
    assert outcome.version_id is None
    assert outcome.chunk_count == 0

    # No version was created for the failed attempt.
    versions = knowledge_document_version_service.list_for_document(
        db_session, document=outcome.document
    )
    assert versions == []


def test_failed_ingestion_still_creates_a_traceable_file_and_job(db_session):
    """Failure is recorded, not discarded — the file and job rows exist
    and are queryable even though processing didn't succeed."""
    source = make_global_source(db_session)

    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=b"%PDF-1.4\nnot a real pdf",
        filename="corrupt.pdf",
        source_id=source.id,
        organization_id=None,
        title="Corrupt Upload",
    )

    assert outcome.file.original_filename == "corrupt.pdf"
    assert outcome.file.detected_media_type == "application/pdf"
    assert outcome.job.file_id == outcome.file.id


# --- 17. File size validation (real enforcement) ---------------------------


def test_oversized_file_is_rejected_before_any_processing(db_session, monkeypatch):
    monkeypatch.setattr("app.services.ingestion_service.settings.MAX_UPLOAD_SIZE_BYTES", 100)
    source = make_global_source(db_session)

    with pytest.raises(IngestionRequestError):
        ingestion_service.ingest(
            db_session,
            file_bytes=b"x" * 200,
            filename="too_big.txt",
            source_id=source.id,
            organization_id=None,
            title="Too Big",
        )


def test_empty_file_is_rejected(db_session):
    source = make_global_source(db_session)

    with pytest.raises(IngestionRequestError):
        ingestion_service.ingest(
            db_session,
            file_bytes=b"",
            filename="empty.txt",
            source_id=source.id,
            organization_id=None,
            title="Empty",
        )


def test_new_document_without_a_title_is_rejected(db_session):
    source = make_global_source(db_session)

    with pytest.raises(IngestionRequestError):
        ingestion_service.ingest(
            db_session,
            file_bytes=load_fixture("sample_ppe_policy.txt"),
            filename="sample_ppe_policy.txt",
            source_id=source.id,
            organization_id=None,
            title=None,
        )


def test_document_id_must_belong_to_the_given_source_id(db_session):
    source_a = make_global_source(db_session, name="Source A")
    source_b = make_global_source(db_session, name="Source B")
    existing = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_ppe_policy.txt"),
        filename="sample_ppe_policy.txt",
        source_id=source_a.id,
        organization_id=None,
        title="Doc under Source A",
    )

    with pytest.raises(IngestionRequestError):
        ingestion_service.ingest(
            db_session,
            file_bytes=load_fixture("sample_evacuation.rtf"),
            filename="sample_evacuation.rtf",
            source_id=source_b.id,  # wrong source for this document_id
            organization_id=None,
            document_id=existing.document.id,
        )
