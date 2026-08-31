"""The common representation every format adapter's `normalize()` produces.

This is deliberately *not* an attempt to force every format into
identical semantics — a PDF page, a spreadsheet row, and a slide are
different things. It is a common *envelope* around format-specific
location information: every field below except `content_type` and `text`
is optional, and each adapter only ever populates the fields that are
meaningful for its format (a CSV row sets `row_number`, never
`page_number`; a PDF page sets `page_number`, never `sheet_name`). This
is what lets a future evidence citation read "Sheet: Incident Register,
Row 124" for one source and "Page 47" for another, from the same
downstream code, instead of every format being reduced to an
undifferentiated blob of text.

One `NormalizedContent` roughly corresponds to one `KnowledgeUnit`
(app/ingestion/knowledge_unit.py) — the next stage in the pipeline, which
adds document-version identity, ordering, and quality assessment before
chunking. For text formats a `NormalizedContent` is usually coarser than
a final `KnowledgeChunk` (e.g. one per page/section, subdivided further
at chunking time); for row/record-shaped formats it is already
chunk-grained (one per row/slide).

`section_path` (added in the Knowledge Quality & Semantic Chunking
milestone) is deliberately left for adapters to populate only where they
can track true hierarchy cheaply (currently: DOCX, via its heading-level
stack — see docx_adapter.py). Where an adapter has no reliable way to
build a multi-level path, it leaves this `None` and
`app/ingestion/structure.py`'s generic structure-detection pass fills in
a best-effort single-element path from `section_title` instead, at lower
confidence — see that module for the full reasoning.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ContentType

# Kept as the name this module has always exported; the enum itself now
# lives in app/models/enums.py (as `ContentType`) so app/models — which
# KnowledgeChunk needs to reuse the same values from — doesn't have to
# import from app/ingestion. See that module's docstring.
NormalizedContentType = ContentType


class NormalizedContent(BaseModel):
    content_type: NormalizedContentType
    text: str

    title: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    slide_number: int | None = None
    section_title: str | None = None
    section_path: list[str] | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    # A short, human-readable locator for this piece of content, derived
    # from whichever of the fields above apply — e.g. "Page 47",
    # "Sheet: Incident Register, Row 124", "Slide 17". Computed by the
    # adapter that knows which fields are meaningful for its format,
    # rather than reconstructed generically downstream.
    source_reference: str | None = None
