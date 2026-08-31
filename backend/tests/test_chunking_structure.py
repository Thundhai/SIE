"""Knowledge Quality & Semantic Chunking Foundation v0.1 — structural
chunking behavior for `StructureAwareChunkingStrategy`
(app/ingestion/chunking.py).

Covers: heading preservation and heading-stays-with-content, section
hierarchy (section_path), paragraph-aware packing, list cohesion, table
structure preservation, min/max chunk size enforcement, configurable
chunk settings, limited prose overlap, no inappropriate overlap for
structured records, and deterministic generation.
"""

import itertools
import uuid

from app.ingestion.chunking import ChunkingSettings, StructureAwareChunkingStrategy
from app.ingestion.knowledge_unit import KnowledgeUnit, build_knowledge_units
from app.ingestion.pipeline import run_pipeline
from app.ingestion.quality import QualityAssessment
from app.models.enums import ContentType, ExtractionStatus, QualityStatus
from tests.conftest import load_fixture


def chunk_fixture(filename, *, settings=None):
    outcome = run_pipeline(load_fixture(filename), filename=filename)
    units = build_knowledge_units(
        outcome.normalized_content,
        document_version_id=uuid.uuid4(),
        extraction_status=outcome.extraction_status,
        warnings=outcome.warnings,
    )
    strategy = StructureAwareChunkingStrategy(settings or ChunkingSettings.from_app_settings())
    return strategy.chunk(units)


# --- Heading preservation / heading-stays-with-content ----------------------


def test_heading_text_appears_in_the_chunk_it_introduces():
    drafts = chunk_fixture("sample_procedure.docx")
    first = drafts[0]
    assert first.content.startswith("Safety Procedure")
    assert "This document describes the working-at-height procedure." in first.content


def test_no_chunk_is_a_lone_heading_with_no_content():
    """A heading is never separated from the content it introduces — every
    chunk that starts with a section heading also carries body text, not
    just the heading string on its own."""
    drafts = chunk_fixture("sample_procedure.docx")
    for draft in drafts:
        if draft.section_title and draft.content.strip() == draft.section_title:
            raise AssertionError(f"chunk is a lone heading: {draft.content!r}")


# --- Section hierarchy (section_path) ---------------------------------------


def test_section_hierarchy_recorded_as_breadcrumb_path():
    drafts = chunk_fixture("sample_procedure.docx")
    equipment_chunk = next(d for d in drafts if d.section_title == "Required Equipment")
    assert equipment_chunk.section_path == ["Safety Procedure", "Required Equipment"]

    intro_chunk = next(d for d in drafts if d.section_title == "Safety Procedure")
    assert intro_chunk.section_path == ["Safety Procedure"]


def test_low_confidence_structure_still_preserves_available_metadata():
    """PDF has no real heading markup — structure detection falls back to
    a single-element, low-confidence guess rather than claiming a
    hierarchy it can't support (see app/ingestion/structure.py)."""
    drafts = chunk_fixture("sample_procedure.pdf")
    assert all(d.metadata.get("structure_confidence") == "low" for d in drafts)
    assert all(d.section_path is not None and len(d.section_path) == 1 for d in drafts)


# --- Paragraph-aware chunking / list cohesion --------------------------------


def test_paragraphs_pack_together_within_a_section_rather_than_one_per_chunk():
    drafts = chunk_fixture("sample_procedure.docx")
    equipment_chunk = next(d for d in drafts if d.section_title == "Required Equipment")
    # The section's intro sentence and its list of required items are
    # small enough to belong in the same chunk together, not one
    # paragraph per chunk.
    assert "Harness, lanyard, and anchor point" in equipment_chunk.content
    assert "Full-body harness rated to EN 361." in equipment_chunk.content


def test_list_items_stay_together_not_arbitrarily_split_across_chunks():
    """The three bulleted equipment items (see
    app/ingestion/adapters/docx_adapter.py's list-style detection) land in
    one chunk together, never scattered one-bullet-per-chunk."""
    drafts = chunk_fixture("sample_procedure.docx")
    bullets = [
        "Full-body harness rated to EN 361.",
        "Shock-absorbing lanyard rated to EN 355.",
        "Fixed anchor point rated to at least 22 kN.",
    ]
    containing_chunks = {
        bullet: next((d for d in drafts if bullet in d.content), None) for bullet in bullets
    }
    assert all(chunk is not None for chunk in containing_chunks.values())
    assert len({id(chunk) for chunk in containing_chunks.values()}) == 1


# --- Table structure preservation --------------------------------------------


def test_table_becomes_its_own_atomic_structured_chunk():
    drafts = chunk_fixture("sample_procedure.docx")
    table_chunks = [d for d in drafts if d.content_type.value == "table"]
    assert len(table_chunks) == 1
    table = table_chunks[0]
    # Preserved as row-structured text ("Equipment | Inspection Interval"),
    # not flattened into misleading prose.
    assert table.content == "Equipment | Inspection Interval\nHarness | Monthly"
    assert table.metadata["rows"] == [["Equipment", "Inspection Interval"], ["Harness", "Monthly"]]
    # Never merged with the surrounding prose paragraphs.
    assert "Full-body harness rated to EN 361." not in table.content


# --- Min/max chunk size enforcement ------------------------------------------


def test_max_chunk_size_is_never_exceeded_by_more_than_sentence_overflow():
    long_paragraph = " ".join(
        f"Sentence number {i} describes a safety requirement in detail." for i in range(60)
    )
    settings = ChunkingSettings(min_chars=50, target_chars=200, max_chars=300, overlap_chars=20)
    unit = KnowledgeUnit(
        content_type=ContentType.TEXT,
        text=long_paragraph,
        sequence=0,
        extraction_status=ExtractionStatus.SUCCEEDED,
        quality=QualityAssessment(status=QualityStatus.HIGH),
    )
    drafts = StructureAwareChunkingStrategy(settings).chunk([unit])
    assert len(drafts) > 1
    # A little overflow beyond max_chars is allowed only when a single
    # sentence itself doesn't fit; no chunk should be wildly larger than
    # the configured ceiling.
    for draft in drafts:
        assert draft.character_count <= settings.max_chars + 200


def test_min_chunk_size_encourages_merging_small_adjacent_units():
    settings = ChunkingSettings(min_chars=100, target_chars=500, max_chars=800, overlap_chars=0)
    units = [
        KnowledgeUnit(
            content_type=ContentType.TEXT,
            text=f"Short note {i}.",
            sequence=i,
            extraction_status=ExtractionStatus.SUCCEEDED,
            section_title="Notes",
            quality=QualityAssessment(status=QualityStatus.MEDIUM),
        )
        for i in range(4)
    ]
    drafts = StructureAwareChunkingStrategy(settings).chunk(units)
    # Four tiny units well under min_chars merge into a single chunk
    # rather than staying as four separate under-sized chunks.
    assert len(drafts) == 1
    assert drafts[0].character_count >= len("Short note 0.")


# --- Configurable chunk settings ---------------------------------------------


def test_smaller_max_chars_setting_produces_more_chunks_for_the_same_content():
    generous = ChunkingSettings(min_chars=50, target_chars=1000, max_chars=1800, overlap_chars=100)
    strict = ChunkingSettings(min_chars=20, target_chars=150, max_chars=250, overlap_chars=20)

    drafts_generous = chunk_fixture("sample_procedure.docx", settings=generous)
    drafts_strict = chunk_fixture("sample_procedure.docx", settings=strict)

    assert len(drafts_strict) > len(drafts_generous)


def test_chunking_settings_are_read_from_app_settings_by_default(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.TARGET_CHUNK_CHARACTERS", 42)
    settings = ChunkingSettings.from_app_settings()
    assert settings.target_chars == 42


# --- Prose overlap vs. no overlap for structured records ---------------------


def test_prose_split_chunks_carry_limited_overlap():
    long_paragraph = " ".join(
        f"Requirement {i}: workers must wear certified fall protection." for i in range(60)
    )
    settings = ChunkingSettings(min_chars=50, target_chars=200, max_chars=300, overlap_chars=40)
    unit = KnowledgeUnit(
        content_type=ContentType.TEXT,
        text=long_paragraph,
        sequence=0,
        extraction_status=ExtractionStatus.SUCCEEDED,
        quality=QualityAssessment(status=QualityStatus.HIGH),
    )
    drafts = StructureAwareChunkingStrategy(settings).chunk([unit])
    assert len(drafts) > 1
    # Each chunk after the first repeats a small tail of the previous
    # chunk's content, for continuity across the cut.
    for previous, current in itertools.pairwise(drafts):
        tail = previous.content[-settings.overlap_chars :].strip()
        assert tail[:20] in current.content


def test_structured_records_are_never_duplicated_for_overlap():
    """Spreadsheet/CSV rows are structured records, not prose — applying
    prose-style overlap to them would duplicate row data, which is never
    correct (see app/ingestion/chunking.py's _chunk_structured_record)."""
    settings = ChunkingSettings(min_chars=10, target_chars=40, max_chars=60, overlap_chars=100)
    drafts = chunk_fixture("sample_incident_register.csv", settings=settings)
    assert len(drafts) >= 3
    # No two chunks share any duplicated row content.
    seen_texts: set[str] = set()
    for draft in drafts:
        for fragment in seen_texts:
            assert fragment not in draft.content or fragment == ""
        seen_texts.add(draft.content)


# --- Deterministic generation -------------------------------------------------


def test_chunking_is_deterministic_for_the_same_input_and_settings():
    first = chunk_fixture("sample_procedure.docx")
    second = chunk_fixture("sample_procedure.docx")
    assert [d.content for d in first] == [d.content for d in second]
    assert [d.section_path for d in first] == [d.section_path for d in second]
    assert [d.quality.status for d in first] == [d.quality.status for d in second]
