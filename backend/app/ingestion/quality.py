"""Extraction/structure quality assessment — deterministic, not an AI
judgment call.

**This scores how successfully SIE extracted and structured a piece of
content. It is not, and must never be conflated with, an assessment of
whether the underlying safety information is true, complete, or
authoritative.** Those are entirely separate concepts, deliberately kept
separate throughout this codebase:

  * **Source authority** (`KnowledgeSource.authority_level`, set by a
    human when the source is registered — see
    app/models/knowledge_source.py) — how authoritative the *publisher*
    is. A national regulator's standard is high-authority regardless of
    how well SIE happened to parse the PDF it was published as.
  * **Verification status** (`KnowledgeSource.verification_status` /
    `app/models/enums.py::VerificationStatus`) — SIE's own governance
    workflow state for a source (PENDING/UNDER_REVIEW/VERIFIED/...). Not
    touched by this module or by chunking at all — see
    app/services/chunking_service.py's docstring.
  * **Extraction/structure quality** (`QualityStatus`, this module) —
    did SIE actually manage to get usable, well-structured text out of
    this specific file. A highly authoritative, VERIFIED regulation can
    still have LOW extraction quality if it was a scanned PDF with no
    text layer; conversely a low-authority internal note can have HIGH
    extraction quality if it was a clean DOCX.

None of these three ever get combined into one number or one field. A
chunk carries all three, distinctly named, so a future evidence-quality
feature can reason about them independently (see the milestone's own
example: "Source Authority: HIGH but Extraction Quality: LOW").

Two assessment entry points, deliberately distinct:

  * `assess_unit_quality` — a single `NormalizedContent` item's own
    standalone quality, before chunking. Stored on `KnowledgeUnit.quality`
    (see knowledge_unit.py) — useful in its own right (e.g. inspecting
    which source pages/rows extracted poorly), but *not* what a final
    chunk's quality is computed from directly.
  * `assess_merged_quality` — used by `app/ingestion/chunking.py` once a
    chunk's final text is known (whether it came from one unit or several
    packed together). Re-runs the same length/structure checks against
    the chunk's *actual* final text rather than reusing pre-merge
    per-unit numbers, and carries forward only the reasons that remain
    true regardless of merging (e.g. "this table's extraction was
    incomplete" is still true after packing; "this fragment alone was
    short" is not, once it's been joined with a heading or a neighboring
    paragraph). Unioning raw per-unit reasons onto a merged chunk would
    otherwise mislabel a perfectly good combined chunk as
    INSUFFICIENT/short just because one of its short *ingredients* was.

The checks below are simple and explainable by design — length,
completeness signals already recorded upstream (extraction warnings,
whether OCR was needed but unavailable, ragged/malformed structured
data), not a model or a heuristic score dressed up as intelligence.
"""

from dataclasses import dataclass, field

from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType
from app.models.enums import ExtractionStatus, QualityStatus

# Deliberately small, documented thresholds — not scientifically tuned,
# same spirit as the chunking size defaults (see chunking.py).
_MIN_USABLE_CHARS = 20
_SHORT_TEXT_CHARS = 80

# Reasons that describe a real property of the underlying source content
# (not merely "this one fragment, before merging, happened to be short")
# and so remain valid to report even after a chunk combines several units.
_CARRYABLE_REASONS = frozenset(
    {
        "table_extraction_incomplete",
        "malformed_content_detected",
        "no_ocr_text_available",
    }
)

_ORDER = [QualityStatus.INSUFFICIENT, QualityStatus.LOW, QualityStatus.MEDIUM, QualityStatus.HIGH]


@dataclass
class QualityAssessment:
    status: QualityStatus
    reasons: list[str] = field(default_factory=list)

    def as_metadata(self) -> dict:
        return {"quality_status": self.status.value, "quality_reasons": list(self.reasons)}


def assess_unit_quality(
    item: NormalizedContent,
    *,
    extraction_status: ExtractionStatus,
    warnings: list[str],
) -> QualityAssessment:
    """Assess one piece of normalized content standalone (see module
    docstring — this is *not* directly reused for a merged chunk's own
    quality)."""
    if item.content_type == NormalizedContentType.IMAGE:
        # Never claim understanding of image content that was never
        # actually read — see app/ingestion/ocr.py.
        return QualityAssessment(
            status=QualityStatus.INSUFFICIENT, reasons=["no_ocr_text_available"]
        )

    if extraction_status == ExtractionStatus.FAILED:
        return QualityAssessment(status=QualityStatus.INSUFFICIENT, reasons=["extraction_failed"])

    has_structure = _has_structural_metadata(item)
    status, reasons = _length_and_structure_status(item.text, has_structure=has_structure)

    if extraction_status == ExtractionStatus.PARTIAL:
        reasons.append("file_extraction_partial")
        status = _lower(status, QualityStatus.MEDIUM)

    if item.content_type == NormalizedContentType.TABLE and (
        any("table" in w.lower() for w in warnings)
        or item.metadata.get("table_extraction_incomplete")
    ):
        reasons.append("table_extraction_incomplete")
        status = _lower(status, QualityStatus.MEDIUM)

    if item.metadata.get("malformed"):
        reasons.append("malformed_content_detected")
        status = _lower(status, QualityStatus.LOW)

    return QualityAssessment(status=status, reasons=reasons)


def assess_merged_quality(
    text: str,
    *,
    has_structure: bool,
    source_reasons: list[str],
    extraction_status: ExtractionStatus,
) -> QualityAssessment:
    """Assess a chunk's *final* text — see module docstring for why this
    is not simply the union of its constituent units' own assessments."""
    if extraction_status == ExtractionStatus.FAILED:
        return QualityAssessment(status=QualityStatus.INSUFFICIENT, reasons=["extraction_failed"])

    status, reasons = _length_and_structure_status(text, has_structure=has_structure)

    carried = sorted(r for r in set(source_reasons) if r in _CARRYABLE_REASONS)
    if carried:
        reasons = reasons + [r for r in carried if r not in reasons]
        status = _lower(status, QualityStatus.MEDIUM)

    if extraction_status == ExtractionStatus.PARTIAL and "file_extraction_partial" not in reasons:
        reasons.append("file_extraction_partial")
        status = _lower(status, QualityStatus.MEDIUM)

    return QualityAssessment(status=status, reasons=reasons)


def _length_and_structure_status(text: str, *, has_structure: bool) -> tuple[QualityStatus, list[str]]:
    stripped = text.strip()
    if not stripped:
        return QualityStatus.INSUFFICIENT, ["empty_or_near_empty_content"]
    if len(stripped) < _MIN_USABLE_CHARS:
        return QualityStatus.INSUFFICIENT, ["empty_or_near_empty_content"]

    reasons: list[str] = []
    status = QualityStatus.HIGH
    if len(stripped) < _SHORT_TEXT_CHARS:
        reasons.append("short_text")
        status = QualityStatus.MEDIUM
    if not has_structure:
        reasons.append("no_structural_metadata")
        status = _lower(status, QualityStatus.MEDIUM)
    return status, reasons


def _has_structural_metadata(item: NormalizedContent) -> bool:
    return bool(
        item.page_number
        or item.sheet_name
        or item.slide_number
        or item.row_number
        or item.section_title
    )


def lower_quality(current: QualityStatus, cap: QualityStatus) -> QualityStatus:
    """Return whichever of `current`/`cap` is worse — used to cap a score
    downward without ever accidentally raising it. Public because
    app/ingestion/chunking.py also needs it (e.g. downgrading a table
    split across multiple chunks) without duplicating the ranking."""
    return current if _ORDER.index(current) <= _ORDER.index(cap) else cap


# Internal alias kept for brevity at every in-module call site above.
_lower = lower_quality
