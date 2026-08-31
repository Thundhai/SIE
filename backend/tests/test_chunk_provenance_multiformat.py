"""Knowledge Quality & Semantic Chunking Foundation v0.1 — per-format
chunk-level provenance, document version isolation, and duplicate-
processing idempotency.

    Chunk -> Document Version -> Document -> Knowledge Source
        -> Ingested File -> Ingestion Job

Every format's chunk carries a concrete, human-readable pointer to where
in the source it came from (`source_reference`), per the milestone's own
examples: "Page 47, Section 6.2" (PDF), "Section 4.3" (DOCX), "Slide 17"
(PPTX), "Sheet Incident Register, Row 124" (XLSX), "Row 124" (CSV).
"""

from app.models.enums import ScopeType
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.ingestion_service import ingestion_service
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_version_service import (
    knowledge_document_version_service,
)
from app.services.knowledge_provenance_service import get_chunk_provenance
from app.services.knowledge_source_service import knowledge_source_service
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


def ingest(db_session, source, filename, **overrides):
    kwargs = {
        "file_bytes": load_fixture(filename),
        "filename": filename,
        "source_id": source.id,
        "organization_id": None,
        "title": filename,
    }
    kwargs.update(overrides)
    return ingestion_service.ingest(db_session, **kwargs)


def chunks_for(db_session, outcome):
    version = knowledge_document_version_service.get_for_document(
        db_session, document=outcome.document, version_id=outcome.version_id
    )
    return knowledge_chunk_service.list_for_version(db_session, document_version=version)


# --- Per-format location/provenance ------------------------------------------


def test_pdf_chunks_carry_page_level_location(db_session):
    source = make_source(db_session)
    outcome = ingest(db_session, source, "sample_procedure.pdf")
    chunks = chunks_for(db_session, outcome)

    assert all(c.page_number is not None for c in chunks)
    assert all(c.source_reference and c.source_reference.startswith("Page") for c in chunks)


def test_docx_chunks_carry_section_level_location(db_session):
    source = make_source(db_session)
    outcome = ingest(db_session, source, "sample_procedure.docx")
    chunks = chunks_for(db_session, outcome)

    equipment_chunk = next(c for c in chunks if c.section_title == "Required Equipment")
    assert equipment_chunk.section_path == ["Safety Procedure", "Required Equipment"]


def test_pptx_chunks_carry_slide_level_location(db_session):
    source = make_source(db_session)
    outcome = ingest(db_session, source, "sample_training.pptx")
    chunks = chunks_for(db_session, outcome)

    assert {c.slide_number for c in chunks} == {1, 2}
    slide_1 = next(c for c in chunks if c.slide_number == 1)
    assert slide_1.source_reference == "Slide 1"
    # Slides are never merged together, even though they're short prose
    # (see KnowledgeUnit.is_atomic) — each keeps its own crisp
    # traceability rather than blending into a neighboring slide's chunk.
    assert len(chunks) == 2


def test_xlsx_chunks_carry_sheet_and_row_level_location(db_session):
    source = make_source(db_session)
    outcome = ingest(db_session, source, "sample_incident_register.xlsx")
    chunks = chunks_for(db_session, outcome)

    assert len(chunks) == 3
    rows = sorted(c.row_number for c in chunks)
    assert rows == [2, 3, 4]
    for chunk in chunks:
        assert chunk.sheet_name == "Incident Register"
        assert chunk.source_reference == f"Sheet: Incident Register, Row {chunk.row_number}"
        assert chunk.content_type.value == "structured_record"


def test_csv_chunks_carry_row_level_location(db_session):
    source = make_source(db_session)
    outcome = ingest(db_session, source, "sample_incident_register.csv")
    chunks = chunks_for(db_session, outcome)

    assert len(chunks) == 3
    for chunk in chunks:
        assert chunk.sheet_name is None
        assert chunk.source_reference == f"Row {chunk.row_number}"


def test_structured_records_never_combine_unrelated_rows_into_one_chunk(db_session):
    source = make_source(db_session)
    outcome = ingest(db_session, source, "sample_incident_register.csv")
    chunks = chunks_for(db_session, outcome)

    # One chunk per row — each carries exactly one incident's data, not
    # several rows blended together.
    for chunk in chunks:
        assert chunk.content.count("Incident ID:") == 1


# --- Full lineage / provenance chain completeness ----------------------------


def test_chunk_provenance_traces_the_full_chain_for_every_format(db_session):
    for filename in [
        "sample_procedure.pdf",
        "sample_procedure.docx",
        "sample_training.pptx",
        "sample_incident_register.xlsx",
        "sample_incident_register.csv",
    ]:
        source = make_source(db_session, name=f"source for {filename}")
        outcome = ingest(db_session, source, filename)
        chunks = chunks_for(db_session, outcome)
        assert len(chunks) > 0

        provenance = get_chunk_provenance(db_session, chunk_id=chunks[0].id)
        assert provenance["document_version_id"] == outcome.version_id
        assert provenance["document_id"] == outcome.document.id
        assert provenance["source_id"] == source.id
        assert provenance["organization_id"] is None


def test_chunk_denormalized_columns_match_the_provenance_chain(db_session):
    source = make_source(db_session)
    outcome = ingest(db_session, source, "sample_procedure.docx")
    chunks = chunks_for(db_session, outcome)

    for chunk in chunks:
        assert chunk.document_id == outcome.document.id
        assert chunk.source_id == source.id
        assert chunk.document_version_id == outcome.version_id


# --- Document version isolation ----------------------------------------------


def test_old_chunks_stay_with_the_old_version_when_a_new_version_is_ingested(db_session):
    source = make_source(db_session)
    v1 = ingest(db_session, source, "sample_ppe_policy.txt", title="Policy")
    v1_chunks = chunks_for(db_session, v1)

    v2 = ingest(
        db_session,
        source,
        "sample_evacuation.rtf",  # genuinely different content
        document_id=v1.document.id,
        title=None,
    )
    v2_chunks = chunks_for(db_session, v2)

    assert v1.version_id != v2.version_id
    assert {c.id for c in v1_chunks}.isdisjoint({c.id for c in v2_chunks})
    # The old version's chunks are untouched — still resolvable, still
    # pointing at v1, not silently rewritten or deleted.
    still_there = knowledge_chunk_service.list_for_version(
        db_session,
        document_version=knowledge_document_version_service.get_for_document(
            db_session, document=v1.document, version_id=v1.version_id
        ),
    )
    assert {c.id for c in still_there} == {c.id for c in v1_chunks}


# --- Duplicate-processing idempotency -----------------------------------------


def test_reingesting_identical_content_does_not_duplicate_chunks(db_session):
    source = make_source(db_session)
    first = ingest(db_session, source, "sample_procedure.docx", title="LOTO")
    second = ingest(
        db_session,
        source,
        "sample_procedure.docx",
        document_id=first.document.id,
        title=None,
    )

    assert second.version_id == first.version_id
    assert second.chunk_count == first.chunk_count

    chunks = chunks_for(db_session, first)
    assert len(chunks) == first.chunk_count
    # No duplicate chunk_index values were created by the second pass.
    assert len({c.chunk_index for c in chunks}) == len(chunks)
