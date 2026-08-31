"""The generic ingestion pipeline, DB-independent and directly testable:

    file bytes -> detect -> (adapter selection) -> validate -> hash
        -> extract -> normalize -> structure detection -> PipelineOutcome

This module has no database dependency and never touches
`StorageProvider` — it is pure transformation of bytes into
`PipelineOutcome`, which is what makes it independently testable (see
tests/test_ingestion_pipeline.py) without a database or storage fixture.
Persistence (IngestedFile/IngestionJob/KnowledgeDocument/
KnowledgeDocumentVersion rows, storage, audit) is
`app/services/ingestion_service.py`'s job, one layer up; turning this
module's `normalized_content` into `KnowledgeChunk` rows is
`app/services/chunking_service.py`'s job, a further layer up still — see
that module's docstring for why chunking itself (not just persistence)
happens after the database version exists rather than here.

The stages above map directly onto the milestone's pipeline diagram:

    INPUT -> File/type detection -> Validation -> Hashing
        -> Source/document association -> Format adapter
        -> Content extraction -> Structure detection -> Normalization
        -> Quality checks -> Persistence -> Provenance

everything up to and including "Structure detection" happens here (via
`app/ingestion/structure.py`, itself pure); "Source/document
association", the "Knowledge Units"/chunking stages, "Persistence", and
"Provenance" happen above this module, since they need the database and
the authorized tenant context this module deliberately has no access to.

Detection is split into its own cheap, no-parsing step
(`detect_supported_type`) precisely so `ingestion_service.py` can reject
an unsupported upload *before* resolving source/document association or
writing anything to the database, while still resolving that association
(and therefore attributing a job to the right source/document) *before*
attempting the possibly-failing parse in `extract_and_normalize`.
"""

from dataclasses import dataclass, field

from app.ingestion.adapters import get_adapter
from app.ingestion.adapters.base import (
    AdapterExtractionError,
    AdapterValidationError,
    DocumentAdapter,
)
from app.ingestion.detection import DetectedFileType, detect_file_type
from app.ingestion.hashing import sha256_hex
from app.ingestion.normalized_content import NormalizedContent
from app.ingestion.structure import detect_structure
from app.models.enums import ExtractionMethod, ExtractionStatus


class UnsupportedFileTypeError(Exception):
    """Raised when detection finds nothing recognizable, or finds a
    recognized-but-not-yet-supported type (see detection.py's future
    extension table) with no registered adapter."""


class FileValidationError(Exception):
    """Wraps AdapterValidationError — the file's format is supported, but
    this particular file is too malformed to safely process."""


class FileExtractionError(Exception):
    """Wraps AdapterExtractionError — a hard extraction failure, not a
    quality/completeness issue (those are recorded as warnings, not
    raised)."""


@dataclass
class PipelineOutcome:
    content_hash: str
    adapter_format_id: str
    content_category: str
    extraction_method: ExtractionMethod
    extraction_status: ExtractionStatus
    warnings: list[str] = field(default_factory=list)
    normalized_content: list[NormalizedContent] = field(default_factory=list)
    extraction_metadata: dict = field(default_factory=dict)


def detect_supported_type(
    file_bytes: bytes, *, filename: str
) -> tuple[DetectedFileType, DocumentAdapter]:
    """Detect the file's type and resolve its adapter, without parsing
    the file at all. Raises UnsupportedFileTypeError if either step
    fails — cheap enough to call before any database write."""
    detected = detect_file_type(file_bytes, filename=filename)
    if detected is None:
        raise UnsupportedFileTypeError(f"Could not detect a supported file type for {filename!r}.")

    adapter = get_adapter(media_type=detected.media_type, extension=detected.extension)
    if adapter is None:
        raise UnsupportedFileTypeError(
            f"Detected type {detected.media_type!r} ({detected.extension}) is recognized but "
            "has no ingestion adapter in this release."
        )
    return detected, adapter


def extract_and_normalize(
    file_bytes: bytes,
    *,
    filename: str,
    adapter: DocumentAdapter,
) -> PipelineOutcome:
    """Run validate -> hash -> extract -> normalize -> structure detection
    for a file whose adapter has already been resolved via
    `detect_supported_type`. Raises FileValidationError /
    FileExtractionError for a hard failure; anything short of that is
    recorded in the returned warnings rather than raised.
    """
    content_hash = sha256_hex(file_bytes)

    try:
        validation_warnings = adapter.validate(file_bytes, filename=filename)
    except AdapterValidationError as exc:
        raise FileValidationError(str(exc)) from exc

    try:
        extraction = adapter.extract(file_bytes)
    except AdapterExtractionError as exc:
        raise FileExtractionError(str(exc)) from exc

    normalized = adapter.normalize(extraction)
    normalized = detect_structure(normalized)

    return PipelineOutcome(
        content_hash=content_hash,
        adapter_format_id=adapter.format_id,
        content_category=adapter.content_category,
        extraction_method=_determine_extraction_method(adapter, extraction),
        extraction_status=_determine_extraction_status(adapter, normalized),
        warnings=[*validation_warnings, *extraction.warnings],
        normalized_content=normalized,
        extraction_metadata=extraction.metadata,
    )


def run_pipeline(file_bytes: bytes, *, filename: str) -> PipelineOutcome:
    """Convenience wrapper running the full detect -> ... -> structure
    detection pipeline in one call, for callers (tests, one-off tooling)
    that don't need the two-step split `ingestion_service.py` uses."""
    _detected, adapter = detect_supported_type(file_bytes, filename=filename)
    return extract_and_normalize(file_bytes, filename=filename, adapter=adapter)


def _determine_extraction_method(adapter: DocumentAdapter, extraction) -> ExtractionMethod:
    if adapter.content_category == "image":
        if extraction.metadata.get("ocr_available"):
            return ExtractionMethod.OCR
        return ExtractionMethod.NONE
    if adapter.content_category in {"spreadsheet", "structured_data"}:
        return ExtractionMethod.STRUCTURED_PARSE
    return ExtractionMethod.TEXT_EXTRACTION


def _determine_extraction_status(
    adapter: DocumentAdapter, normalized: list[NormalizedContent]
) -> ExtractionStatus:
    if adapter.content_category == "image":
        # Nothing was attempted, not merely incomplete — see ocr.py.
        return ExtractionStatus.PENDING
    if not normalized:
        return ExtractionStatus.FAILED

    empty_items = sum(1 for item in normalized if not item.text.strip())
    if empty_items > 0:
        # Covers both "some pages/rows came up empty" and "every one
        # did" — either way the pipeline completed but the result is
        # degraded, never silently reported as a clean success.
        return ExtractionStatus.PARTIAL
    return ExtractionStatus.SUCCEEDED
