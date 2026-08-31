"""Milestone test items 8, 10-14: content hashing, and per-format
structure preservation (page numbers, headings/sections, sheet/row/
column metadata, slide metadata) — all against real fixture files, all
through the pure `app/ingestion/pipeline.py` (no database).

Item 9 ("duplicate file handling") is covered at the service/HTTP layer
in test_ingestion_service.py, since "duplicate" is a statement about what
happens across two ingestion calls, not about the pipeline in isolation.
"""

from app.ingestion.hashing import sha256_hex
from app.ingestion.normalized_content import NormalizedContentType
from app.ingestion.pipeline import run_pipeline
from tests.conftest import load_fixture


# --- 8. Content hash generation -------------------------------------------


def test_content_hash_is_sha256_and_deterministic():
    data = load_fixture("sample_ppe_policy.txt")

    outcome = run_pipeline(data, filename="sample_ppe_policy.txt")

    assert outcome.content_hash == sha256_hex(data)
    assert len(outcome.content_hash) == 64  # hex-encoded sha256 digest


def test_content_hash_differs_for_different_content():
    a = run_pipeline(load_fixture("sample_ppe_policy.txt"), filename="a.txt")
    b = run_pipeline(load_fixture("sample_evacuation.rtf"), filename="b.rtf")

    assert a.content_hash != b.content_hash


def test_content_hash_is_identical_for_byte_identical_uploads_under_different_names():
    """Two files with different filenames but identical bytes must hash
    the same — filename is never part of a document's identity."""
    data = load_fixture("sample_ppe_policy.txt")

    a = run_pipeline(data, filename="policy_v1.txt")
    b = run_pipeline(data, filename="policy_copy.txt")

    assert a.content_hash == b.content_hash


# --- 10. PDF page metadata preservation -----------------------------------


def test_pdf_page_metadata_is_preserved():
    outcome = run_pipeline(load_fixture("sample_procedure.pdf"), filename="sample_procedure.pdf")

    pages = outcome.normalized_content
    assert len(pages) == 2
    assert [p.page_number for p in pages] == [1, 2]
    assert all(p.content_type == NormalizedContentType.TEXT for p in pages)
    assert all(p.source_reference == f"Page {p.page_number}" for p in pages)
    assert "Lockout/Tagout" in pages[0].text
    assert "Section 2" in pages[1].text


def test_pdf_with_no_extractable_text_reports_a_quality_warning():
    outcome = run_pipeline(load_fixture("sample_blank.pdf"), filename="sample_blank.pdf")

    assert any("no extractable text" in w for w in outcome.warnings)
    assert outcome.extraction_status.value == "PARTIAL"
    assert outcome.extraction_method.value == "TEXT_EXTRACTION"  # attempted, not OCR


def test_pdf_does_not_claim_table_extraction():
    outcome = run_pipeline(load_fixture("sample_procedure.pdf"), filename="sample_procedure.pdf")

    assert outcome.extraction_metadata["table_extraction"] == "not_attempted"


# --- 11. DOCX heading/section preservation --------------------------------


def test_docx_heading_and_section_preservation():
    outcome = run_pipeline(load_fixture("sample_procedure.docx"), filename="sample_procedure.docx")

    contents = outcome.normalized_content
    texts = [c.text for c in contents]
    assert "Safety Procedure" in texts
    assert "Required Equipment" in texts

    # The paragraph after "Safety Procedure" carries it as section_title.
    para = next(c for c in contents if c.text.startswith("This document describes"))
    assert para.section_title == "Safety Procedure"

    # The table appearing after "Required Equipment" carries *that*
    # section, not the first heading — proving true document-order
    # interleaving, not "all headings first, then all paragraphs/tables".
    table = next(c for c in contents if c.content_type == NormalizedContentType.TABLE)
    assert table.section_title == "Required Equipment"
    assert "Equipment" in table.text and "Inspection Interval" in table.text


# --- 12. CSV sheet/row/column metadata ------------------------------------


def test_csv_row_and_column_metadata():
    outcome = run_pipeline(
        load_fixture("sample_incident_register.csv"), filename="sample_incident_register.csv"
    )

    records = outcome.normalized_content
    assert len(records) == 3
    assert all(r.content_type == NormalizedContentType.STRUCTURED_RECORD for r in records)
    assert [r.row_number for r in records] == [2, 3, 4]  # header occupies row 1
    assert records[0].metadata["columns"] == [
        "Incident ID",
        "Date",
        "Description",
        "Severity",
    ]
    assert records[0].metadata["values"]["Incident ID"] == "INC-001"
    assert records[0].source_reference == "Row 2"
    assert outcome.extraction_metadata["row_count"] == 3
    assert outcome.extraction_metadata["column_names"][0] == "Incident ID"


# --- 13. XLSX worksheet and row metadata ----------------------------------


def test_xlsx_worksheet_and_row_metadata():
    outcome = run_pipeline(
        load_fixture("sample_incident_register.xlsx"), filename="sample_incident_register.xlsx"
    )

    records = outcome.normalized_content
    assert len(records) == 3
    assert all(r.sheet_name == "Incident Register" for r in records)
    assert [r.row_number for r in records] == [2, 3, 4]
    assert records[0].source_reference == "Sheet: Incident Register, Row 2"
    assert records[0].metadata["values"]["Severity"] == "Low"
    assert outcome.extraction_metadata["sheet_names"] == ["Incident Register"]


# --- 14. PPTX slide metadata -----------------------------------------------


def test_pptx_slide_metadata():
    outcome = run_pipeline(load_fixture("sample_training.pptx"), filename="sample_training.pptx")

    slides = outcome.normalized_content
    assert len(slides) == 2
    assert slides[0].slide_number == 1
    assert slides[0].title == "Working at Height"
    assert "Fall protection" in slides[0].text
    assert slides[0].metadata["speaker_notes"] == "Remind trainees to inspect harnesses before use."
    assert slides[0].source_reference == "Slide 1"

    assert slides[1].slide_number == 2
    assert slides[1].title == "Anchor Points"
    assert "damaged anchor points" in slides[1].text.lower()
