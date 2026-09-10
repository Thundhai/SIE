"""KnowledgeUnit — a meaningful piece of source content, positioned and
quality-assessed, ready for chunking.

    Normalized Content -> Structure Detection -> Knowledge Units -> Chunking

**Design decision: KnowledgeUnit is an in-memory dataclass, not a
database table.** It is deliberately transient — constructed for the
duration of one chunking pass and discarded once its `KnowledgeChunk`
row(s) exist. Reasons this is the simplest architecture that still
preserves the concept cleanly, rather than adding a `knowledge_units`
table:

  * It has no independent lifecycle. Nothing ever queries "give me the
    knowledge units for this version" as a stable, addressable resource
    the way it queries chunks, documents, or sources — a unit exists
    only to become one or more chunks, in the same request, and is never
    referenced again afterward.
  * It would duplicate KnowledgeChunk's job. A persisted `KnowledgeUnit`
    table would need nearly the same columns (content_type, text,
    page/sheet/row/slide/section, metadata) as `KnowledgeChunk` already
    has, with `KnowledgeChunk` then usually holding a near-1:1 subset of
    the same data — exactly the "do not duplicate large amounts of data
    unnecessarily" the milestone warns against.
  * This mirrors a pattern already established in this codebase:
    `NormalizedContent` (app/ingestion/normalized_content.py) is the
    identical kind of thing one pipeline stage earlier — an in-memory
    Pydantic model with no table — and nothing about the ingestion
    architecture has needed it to be one. `KnowledgeUnit` is a natural,
    consistent continuation of that same choice, one stage further down
    the pipeline, not a new precedent.
  * If a future milestone ever needs to *inspect* pre-chunking structure
    (e.g. a debugging/QA view), the existing `IngestionJob` +
    `KnowledgeDocumentVersion.extracted_text` already retain enough of
    the raw material to reconstruct it — a persisted intermediate table
    isn't needed to make that possible later.

`document_version_id` is `None` until `app/services/chunking_service.py`
constructs units for an actual, already-created `KnowledgeDocumentVersion`
— units built purely for testing structure/chunking logic (see
tests/test_knowledge_units.py) never need one.
"""

import uuid
from dataclasses import dataclass, field

from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType
from app.ingestion.quality import QualityAssessment, assess_unit_quality
from app.models.enums import ExtractionStatus


@dataclass
class KnowledgeUnit:
    content_type: NormalizedContentType
    text: str
    sequence: int
    extraction_status: ExtractionStatus

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    document_version_id: uuid.UUID | None = None

    title: str | None = None
    page_number: int | None = None
    section_title: str | None = None
    section_path: list[str] | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    slide_number: int | None = None
    source_reference: str | None = None
    metadata: dict = field(default_factory=dict)

    # kw_only so this stays a required field (no meaningful default
    # exists for it) despite following fields that do have defaults —
    # every KnowledgeUnit must be constructed with a real assessment;
    # build_knowledge_units() below is the one place that does so.
    quality: QualityAssessment = field(kw_only=True)

    @property
    def is_atomic(self) -> bool:
        """Whether this unit must never be merged with a neighboring unit
        during chunking (see StructureAwareChunkingStrategy's grouping
        rule in app/ingestion/chunking.py): structured records, tables,
        and images are each their own self-contained piece of evidence;
        slides are conceptually discrete even though they're plain text,
        so "Slide 17" always maps to its own group of chunks and is never
        blended with slide 16 or 18."""
        return self.content_type != NormalizedContentType.TEXT or self.slide_number is not None

    @property
    def is_heading(self) -> bool:
        return self.metadata.get("heading_level") is not None


def build_knowledge_units(
    items: list[NormalizedContent],
    *,
    document_version_id: uuid.UUID | None,
    extraction_status: ExtractionStatus,
    warnings: list[str],
) -> list[KnowledgeUnit]:
    """Wrap an ordered, structure-detected `NormalizedContent` list into
    `KnowledgeUnit`s: stamps `document_version_id`, assigns `sequence`
    (this list's order — the deterministic backbone chunk ordering is
    built from, see chunking.py), and assesses quality per item."""
    units: list[KnowledgeUnit] = []
    for index, item in enumerate(items):
        assessment = assess_unit_quality(item, extraction_status=extraction_status, warnings=warnings)
        units.append(
            KnowledgeUnit(
                content_type=item.content_type,
                text=item.text,
                sequence=index,
                extraction_status=extraction_status,
                document_version_id=document_version_id,
                title=item.title,
                page_number=item.page_number,
                section_title=item.section_title,
                section_path=item.section_path,
                sheet_name=item.sheet_name,
                row_number=item.row_number,
                slide_number=item.slide_number,
                source_reference=item.source_reference,
                metadata=dict(item.metadata),
                quality=assessment,
            )
        )
    return units
