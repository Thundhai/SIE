"""Knowledge Quality & Semantic Chunking Foundation v0.1 — quality
assessment, the source-authority/verification/extraction-quality
separation, and tenant scope preservation through chunking.
"""

from app.ingestion.pipeline import run_pipeline
from app.models.enums import ScopeType, VerificationStatus
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.schemas.organization import OrganizationCreate
from app.services.chunking_service import chunking_service
from app.services.ingestion_service import ingestion_service
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import (
    knowledge_document_version_service,
)
from app.services.knowledge_source_service import knowledge_source_service
from app.services.organization_service import organization_service
from tests.conftest import load_fixture


def make_source(db_session, **overrides):
    payload = {
        "scope_type": ScopeType.GLOBAL,
        "publisher": "OSHA",
        "name": "29 CFR 1910",
        "source_type": "regulation",
    }
    payload.update(overrides)
    return knowledge_source_service.create(db_session, obj_in=KnowledgeSourceCreate(**payload))


# --- Quality status calculation ----------------------------------------------


def test_well_structured_extraction_gets_a_reasonable_quality_status(db_session):
    source = make_source(db_session)
    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_procedure.docx"),
        filename="sample_procedure.docx",
        source_id=source.id,
        organization_id=None,
        title="LOTO Procedure",
    )
    version = knowledge_document_version_service.get_for_document(
        db_session, document=outcome.document, version_id=outcome.version_id
    )
    chunks = knowledge_chunk_service.list_for_version(db_session, document_version=version)

    assert len(chunks) > 0
    assert all(c.quality_status.value != "INSUFFICIENT" for c in chunks)
    # Every chunk carries a deterministic, documented reason list, not an
    # opaque score.
    assert all("quality_reasons" in (c.chunk_metadata or {}) for c in chunks)
    assert all("quality_status" in (c.chunk_metadata or {}) for c in chunks)


def test_blank_page_extraction_is_recorded_not_silently_dropped(db_session):
    source = make_source(db_session)
    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_blank.pdf"),
        filename="sample_blank.pdf",
        source_id=source.id,
        organization_id=None,
        title="Blank Scan",
    )
    version = knowledge_document_version_service.get_for_document(
        db_session, document=outcome.document, version_id=outcome.version_id
    )
    chunks = knowledge_chunk_service.list_for_version(db_session, document_version=version)

    assert len(chunks) == 1
    chunk = chunks[0]
    # A real, citable chunk exists for the blank page — it isn't discarded
    # — but its content is genuinely empty and its quality reflects that
    # honestly, rather than fabricating content or silently hiding the gap.
    assert chunk.content == ""
    assert chunk.quality_status.value == "INSUFFICIENT"
    assert "empty_or_near_empty_content" in chunk.chunk_metadata["quality_reasons"]
    assert chunk.page_number == 1


def test_quality_reasons_never_claim_to_assess_truth_or_correctness(db_session):
    """The quality label is an extraction/structure signal, never phrased
    as a judgment on whether the underlying safety content is true."""
    source = make_source(db_session)
    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_blank.pdf"),
        filename="sample_blank.pdf",
        source_id=source.id,
        organization_id=None,
        title="Blank Scan",
    )
    version = knowledge_document_version_service.get_for_document(
        db_session, document=outcome.document, version_id=outcome.version_id
    )
    chunks = knowledge_chunk_service.list_for_version(db_session, document_version=version)
    for chunk in chunks:
        for reason in chunk.chunk_metadata.get("quality_reasons", []):
            assert "truth" not in reason.lower()
            assert "correct" not in reason.lower()
            assert "accura" not in reason.lower()


# --- Source authority vs. extraction quality separation ----------------------


def test_high_authority_source_can_still_have_low_extraction_quality(db_session):
    """The milestone's own worked example: a highly authoritative source
    can still have poor extraction quality (e.g. a scanned page with no
    text layer) — the two are recorded completely separately, never
    combined into one score."""
    source = make_source(db_session, authority_level="HIGH", jurisdiction="US")
    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_blank.pdf"),
        filename="sample_blank.pdf",
        source_id=source.id,
        organization_id=None,
        title="Blank Scan",
    )
    version = knowledge_document_version_service.get_for_document(
        db_session, document=outcome.document, version_id=outcome.version_id
    )
    chunks = knowledge_chunk_service.list_for_version(db_session, document_version=version)
    chunk = chunks[0]

    # Source authority is untouched by the poor extraction outcome...
    db_session.refresh(source)
    assert source.authority_level == "HIGH"
    # ...while the chunk's own extraction quality reflects reality,
    # recorded as a distinctly-named, separate field.
    assert chunk.quality_status.value == "INSUFFICIENT"
    # And the source's authority is preserved as a read-only snapshot on
    # the chunk too, for a future evidence view to show both side by side
    # without contradicting one another.
    assert chunk.chunk_metadata["source_metadata_snapshot"]["authority_level"] == "HIGH"


def test_ingestion_never_changes_source_verification_status(db_session):
    source = make_source(db_session, verification_status=VerificationStatus.PENDING)
    ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_procedure.docx"),
        filename="sample_procedure.docx",
        source_id=source.id,
        organization_id=None,
        title="LOTO Procedure",
    )

    db_session.refresh(source)
    assert source.verification_status == VerificationStatus.PENDING


def test_ingestion_never_marks_a_source_verified(db_session):
    """Explicit milestone requirement: newly ingested content must never
    be auto-marked VERIFIED just because it was successfully chunked."""
    source = make_source(db_session)
    ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_procedure.docx"),
        filename="sample_procedure.docx",
        source_id=source.id,
        organization_id=None,
        title="LOTO Procedure",
    )

    db_session.refresh(source)
    assert source.verification_status != VerificationStatus.VERIFIED


# --- Global/organization scope preservation ----------------------------------


def test_global_source_chunks_have_no_organization_id(db_session):
    source = make_source(db_session)
    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_procedure.docx"),
        filename="sample_procedure.docx",
        source_id=source.id,
        organization_id=None,
        title="LOTO Procedure",
    )
    version = knowledge_document_version_service.get_for_document(
        db_session, document=outcome.document, version_id=outcome.version_id
    )
    chunks = knowledge_chunk_service.list_for_version(db_session, document_version=version)
    assert len(chunks) > 0
    assert all(c.organization_id is None for c in chunks)
    assert all(c.source_id == source.id for c in chunks)
    assert all(c.document_id == outcome.document.id for c in chunks)


def test_organization_source_chunks_carry_the_organization_id(db_session):
    org = organization_service.create(db_session, obj_in=OrganizationCreate(name="Acme"))
    source = make_source(
        db_session,
        scope_type=ScopeType.ORGANIZATION,
        organization_id=org.id,
        publisher="Acme Industrial",
        name="Internal LOTO Procedure",
        source_type="internal_procedure",
    )
    outcome = ingestion_service.ingest(
        db_session,
        file_bytes=load_fixture("sample_procedure.docx"),
        filename="sample_procedure.docx",
        source_id=source.id,
        organization_id=org.id,
        title="Internal LOTO Procedure",
    )
    version = knowledge_document_version_service.get_for_document(
        db_session, document=outcome.document, version_id=outcome.version_id
    )
    chunks = knowledge_chunk_service.list_for_version(db_session, document_version=version)
    assert len(chunks) > 0
    assert all(c.organization_id == org.id for c in chunks)


# --- Metadata snapshot (jurisdiction/publication_date/etc.) -----------------


def test_chunk_metadata_snapshot_captures_point_in_time_source_and_version_fields(db_session):
    source = make_source(
        db_session,
        jurisdiction="US",
        industry_sector="construction",
        authority_level="HIGH",
        publication_date="2020-01-01",
    )
    document = knowledge_document_service.create(
        db_session,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id,
            title="LOTO Procedure",
            document_type="regulation_text",
            language="en",
        ),
    )
    version = knowledge_document_version_service.create(
        db_session,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1",
            content_hash="hash-1",
            storage_reference="ref-1",
            publication_date="2021-06-15",
            effective_date="2021-07-01",
        ),
    )
    outcome = run_pipeline(load_fixture("sample_procedure.docx"), filename="sample_procedure.docx")

    chunks = chunking_service.generate_chunks(
        db_session,
        document=document,
        source=source,
        version=version,
        normalized_content=outcome.normalized_content,
        extraction_status=outcome.extraction_status,
        extraction_method=outcome.extraction_method,
        warnings=outcome.warnings,
    )

    snapshot = chunks[0].chunk_metadata["source_metadata_snapshot"]
    assert snapshot["jurisdiction"] == "US"
    assert snapshot["industry_sector"] == "construction"
    assert snapshot["authority_level"] == "HIGH"
    assert snapshot["language"] == "en"
    # Version-level dates, not the source's own publication_date.
    assert snapshot["publication_date"] == "2021-06-15"
    assert snapshot["effective_date"] == "2021-07-01"

    # None of these were promoted to real chunk columns (see
    # app/models/knowledge_chunk.py's docstring for why).
    assert not hasattr(chunks[0], "jurisdiction")
    assert not hasattr(chunks[0], "verification_status")
