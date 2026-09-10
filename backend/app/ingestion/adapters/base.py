"""The common format-adapter interface.

    detect()  -> can this adapter handle this media type/extension
    validate() -> is this specific file well-formed enough to attempt
    extract()  -> parse raw bytes into an adapter-specific intermediate form
    normalize() -> translate that intermediate form into NormalizedContent

`extract()` and `normalize()` are deliberately two separate steps rather
than one: `extract()` is where a format's own library does its parsing
and can fail in format-specific ways (a corrupt PDF, a workbook with no
sheets); `normalize()` is pure translation into the common representation
and should not itself fail for a successfully-extracted document. Keeping
them separate is what makes "structure detection" and "normalization" the
distinct pipeline stages the milestone asks for, rather than one opaque
step.

Every concrete adapter in this package (pdf_adapter.py, docx_adapter.py,
...) implements this structurally (Python's `Protocol` does not require
explicit inheritance) — see registry.py for how one gets selected for a
given upload.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ingestion.normalized_content import NormalizedContent


class AdapterValidationError(Exception):
    """Raised by `validate()` for a file that is the right general format
    but too malformed to safely attempt extraction (e.g. a zip that
    claims to be .xlsx but isn't a valid workbook). Distinct from an
    *unsupported* format, which never reaches an adapter at all — see
    registry.py."""


class AdapterExtractionError(Exception):
    """Raised by `extract()` when parsing fails outright (not merely
    incomplete — see the ExtractionResult.warnings for that case). The
    ingestion pipeline catches this and marks the job FAILED rather than
    letting it propagate as a 500."""


@dataclass
class ExtractionResult:
    """Raw, adapter-specific extraction output, before normalization.

    `raw` is intentionally untyped (adapter-internal) — each adapter puts
    whatever intermediate structure suits it there (a list of page
    texts, a list of worksheet row-dicts, ...) and is the only code that
    ever reads it back, in its own `normalize()`. `warnings` and
    `metadata` are the common part every adapter contributes to: e.g. a
    PDF adapter appends a warning like "3 of 5 pages contained no
    extractable text" rather than silently producing an empty page —
    see the ingestion engine's fail-safely principle.
    """

    raw: Any
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentAdapter(Protocol):
    #: Short, stable identifier, e.g. "pdf", "docx", "csv".
    format_id: str
    #: One of "document", "spreadsheet", "presentation", "structured_data",
    #: "image" — used only for defaulting KnowledgeDocument.document_type
    #: when the caller doesn't supply one; not a hard classification.
    content_category: str

    def detect(self, *, media_type: str, extension: str) -> bool:
        """Whether this adapter is the right one for a file already
        identified as `media_type`/`extension` by
        app/ingestion/detection.py. Adapters do their own sniffing here
        (matching against declared supported types), separate from that
        module's job of guessing the type in the first place."""
        ...

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        """Return non-fatal validation warnings, or raise
        AdapterValidationError for a file too malformed to proceed."""
        ...

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        """Parse `file_bytes` into this adapter's intermediate
        representation. Raises AdapterExtractionError on hard failure."""
        ...

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        """Translate `extraction.raw` into the common representation."""
        ...
