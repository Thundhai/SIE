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

One `NormalizedContent` roughly corresponds to one future `KnowledgeChunk`
(via a `ChunkingStrategy` — see chunking.py) — for text formats it's
usually coarser than a chunk (e.g. one per page/section, subdivided
further at chunking time); for row/record-shaped formats it's already
chunk-grained (one per row/slide).
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NormalizedContentType(str, Enum):
    """What kind of thing this piece of normalized content is — not the
    source file format (that's on the adapter/IngestedFile), but the
    shape of this particular piece of content within it."""

    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    STRUCTURED_RECORD = "structured_record"


class NormalizedContent(BaseModel):
    content_type: NormalizedContentType
    text: str

    title: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    slide_number: int | None = None
    section_title: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    # A short, human-readable locator for this piece of content, derived
    # from whichever of the fields above apply — e.g. "Page 47",
    # "Sheet: Incident Register, Row 124", "Slide 17". Computed by the
    # adapter that knows which fields are meaningful for its format,
    # rather than reconstructed generically downstream.
    source_reference: str | None = None
