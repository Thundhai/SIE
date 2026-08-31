"""ChunkingStrategy — the architectural boundary for turning knowledge
units into `KnowledgeChunk` drafts, per the milestone spec:

    Knowledge Units -> ChunkingStrategy -> Knowledge Chunks

`SimpleChunkingStrategy` (from the ingestion milestone) still exists —
one chunk per paragraph-packed unit, no structure awareness — as a
minimal reference implementation of the interface. The strategy actually
used by the ingestion pipeline as of this milestone is
`StructureAwareChunkingStrategy`, which prioritizes, in order: headings
staying attached to the content they introduce, section boundaries,
paragraph boundaries, list cohesion, tables as atomic structured blocks,
and only then falls back to a character-limit split (never blindly every
N characters, and never mid-sentence unless a single unit is too large to
avoid it). Both — and any future strategy (`SemanticChunkingStrategy`,
`TableAwareChunkingStrategy`, `LegalDocumentChunkingStrategy`,
`SafetyProcedureChunkingStrategy`, per the milestone's own list) —
implement the same small `ChunkingStrategy` interface, so
`app/services/chunking_service.py` never needs to change to support a new
one.

Deliberately not semantic/embedding-aware chunking — that is explicitly
out of scope (see the README). Everything here is deterministic: the
same `KnowledgeUnit` sequence and the same `ChunkingSettings` always
produce the same chunk sequence (see the milestone's idempotency/
determinism requirement, and tests/test_chunking_determinism.py).
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

from app.ingestion.knowledge_unit import KnowledgeUnit
from app.ingestion.quality import (
    QualityAssessment,
    assess_merged_quality,
    lower_quality,
)
from app.models.enums import ContentType as NormalizedContentType
from app.models.enums import QualityStatus


@dataclass(frozen=True)
class ChunkingSettings:
    """Configurable chunk sizing — documented *initial* defaults, not
    scientifically validated optimal values (see the milestone spec and
    the README's Knowledge Quality Pipeline section). Character-based:
    no tokenizer dependency is introduced here."""

    min_chars: int = 200
    target_chars: int = 1000
    max_chars: int = 1800
    overlap_chars: int = 150

    @classmethod
    def from_app_settings(cls) -> "ChunkingSettings":
        from app.core.config import settings

        return cls(
            min_chars=settings.MIN_CHUNK_CHARACTERS,
            target_chars=settings.TARGET_CHUNK_CHARACTERS,
            max_chars=settings.MAX_CHUNK_CHARACTERS,
            overlap_chars=settings.OVERLAP_CHARACTERS,
        )


@dataclass
class ChunkDraft:
    """One chunk's worth of content, still detached from any
    KnowledgeDocumentVersion — `app/services/chunking_service.py` assigns
    `chunk_index` and the document/source/organization/version-level
    metadata (language, jurisdiction, verification_status, ...) before
    persisting these as KnowledgeChunk rows."""

    content: str
    character_count: int
    content_type: NormalizedContentType
    page_number: int | None
    sheet_name: str | None
    row_number: int | None
    slide_number: int | None
    section_title: str | None
    section_path: list[str] | None
    source_reference: str | None
    quality: QualityAssessment
    metadata: dict = field(default_factory=dict)


class ChunkingStrategy(Protocol):
    def chunk(self, units: list[KnowledgeUnit]) -> list[ChunkDraft]: ...


class SimpleChunkingStrategy:
    """Deterministic paragraph-based chunking with no structure
    awareness: each `KnowledgeUnit` is split on blank-line paragraph
    boundaries, then greedily packed up to `settings.max_chars`. Kept as
    a minimal reference implementation of `ChunkingStrategy` — the
    ingestion pipeline itself uses `StructureAwareChunkingStrategy`
    (below)."""

    def __init__(self, settings: ChunkingSettings | None = None) -> None:
        self.settings = settings or ChunkingSettings.from_app_settings()

    def chunk(self, units: list[KnowledgeUnit]) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        for unit in units:
            drafts.extend(self._chunk_one(unit))
        return drafts

    def _chunk_one(self, unit: KnowledgeUnit) -> list[ChunkDraft]:
        paragraphs = [p.strip() for p in unit.text.split("\n\n") if p.strip()]
        if not paragraphs:
            if unit.quality.status == QualityStatus.INSUFFICIENT and not (
                unit.metadata or unit.source_reference
            ):
                return []
            paragraphs = [""]

        drafts: list[ChunkDraft] = []
        buffer = ""
        for paragraph in paragraphs:
            candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            if buffer and len(candidate) > self.settings.max_chars:
                drafts.append(_draft_from_unit(buffer, unit))
                buffer = paragraph
            else:
                buffer = candidate
        if buffer or not drafts:
            drafts.append(_draft_from_unit(buffer, unit))
        return drafts


def _draft_from_unit(text: str, unit: KnowledgeUnit) -> ChunkDraft:
    return ChunkDraft(
        content=text,
        character_count=len(text),
        content_type=unit.content_type,
        page_number=unit.page_number,
        sheet_name=unit.sheet_name,
        row_number=unit.row_number,
        slide_number=unit.slide_number,
        section_title=unit.section_title,
        section_path=unit.section_path,
        source_reference=unit.source_reference,
        quality=assess_merged_quality(
            text,
            has_structure=_unit_has_structure(unit),
            source_reasons=unit.quality.reasons,
            extraction_status=unit.extraction_status,
        ),
        metadata=dict(unit.metadata),
    )


def _unit_has_structure(unit: KnowledgeUnit) -> bool:
    return bool(
        unit.page_number
        or unit.sheet_name
        or unit.slide_number
        or unit.row_number
        or unit.section_title
    )


# --- StructureAwareChunkingStrategy -----------------------------------


_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?][\"')\]]?\s+")


class StructureAwareChunkingStrategy:
    """The chunking strategy this milestone implements.

    Units are first grouped so that content which must never be blended
    together stays separate (`_group_units`): a table, a structured
    record (a spreadsheet/CSV row), an image, or a presentation slide
    each form their own atomic group, chunked on their own terms; every
    other (prose-shaped) unit joins a contiguous "prose run" that gets
    packed together, heading-attached, paragraph by paragraph.

    See each `_chunk_*` method for the specific rules that group applies.
    """

    def __init__(self, settings: ChunkingSettings | None = None) -> None:
        self.settings = settings or ChunkingSettings.from_app_settings()

    def chunk(self, units: list[KnowledgeUnit]) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        for group_units, atomic in self._group_units(units):
            if atomic:
                drafts.extend(self._chunk_atomic(group_units[0]))
            else:
                drafts.extend(self._chunk_prose_run(group_units))
        return drafts

    # -- Grouping ---------------------------------------------------

    def _group_units(
        self, units: list[KnowledgeUnit]
    ) -> list[tuple[list[KnowledgeUnit], bool]]:
        groups: list[tuple[list[KnowledgeUnit], bool]] = []
        buffer: list[KnowledgeUnit] = []
        for unit in units:
            if unit.is_atomic:
                if buffer:
                    groups.append((buffer, False))
                    buffer = []
                groups.append(([unit], True))
            else:
                buffer.append(unit)
        if buffer:
            groups.append((buffer, False))
        return groups

    # -- Atomic content: tables, structured records, images, slides -----

    def _chunk_atomic(self, unit: KnowledgeUnit) -> list[ChunkDraft]:
        if unit.content_type == NormalizedContentType.STRUCTURED_RECORD:
            return self._chunk_structured_record(unit)
        if unit.content_type == NormalizedContentType.TABLE:
            return self._chunk_table(unit)
        if unit.content_type == NormalizedContentType.IMAGE:
            return [_draft_from_unit(unit.text, unit)]
        # A presentation slide (content_type TEXT, but atomic because
        # slide_number is set — see KnowledgeUnit.is_atomic): chunk it
        # like a single prose unit, splitting only if it's oversized,
        # with overlap only against itself, never against another slide.
        return self._split_unit_text(unit, unit.text)

    def _chunk_structured_record(self, unit: KnowledgeUnit) -> list[ChunkDraft]:
        text = unit.text
        if not text.strip():
            return [_draft_from_unit(text, unit)] if (unit.metadata or unit.source_reference) else []
        if len(text) <= self.settings.max_chars:
            return [_draft_from_unit(text, unit)]

        # Too large for one chunk: split on field boundaries (", ") so
        # each piece stays a set of whole "key: value" fields, never a
        # value cut mid-way — and every piece still carries the same
        # row/sheet identity via _draft_from_unit's metadata, per "split
        # intelligently while retaining row identity". No overlap between
        # pieces: these are disjoint fields of one record, not prose
        # where repeating context helps.
        fields = text.split(", ")
        pieces = _pack_fragments(fields, self.settings.max_chars, joiner=", ")
        drafts = []
        for index, piece in enumerate(pieces):
            draft = _draft_from_unit(piece, unit)
            draft.metadata = {**draft.metadata, "row_part": index, "row_part_count": len(pieces)}
            drafts.append(draft)
        return drafts

    def _chunk_table(self, unit: KnowledgeUnit) -> list[ChunkDraft]:
        text = unit.text
        if len(text) <= self.settings.max_chars:
            return [_draft_from_unit(text, unit)]

        # Prefer splitting on the table's own row boundaries (available
        # in metadata["rows"] for adapters that extract real table
        # structure, e.g. DOCX) so a split never cuts a row in half;
        # otherwise fall back to line boundaries.
        rows = unit.metadata.get("rows")
        lines = [" | ".join(row) for row in rows] if rows else text.split("\n")
        pieces = _pack_fragments(lines, self.settings.max_chars, joiner="\n")
        drafts = []
        for index, piece in enumerate(pieces):
            draft = _draft_from_unit(piece, unit)
            draft.metadata = {**draft.metadata, "table_part": index, "table_part_count": len(pieces)}
            if len(pieces) > 1:
                draft.quality = QualityAssessment(
                    status=lower_quality(draft.quality.status, QualityStatus.MEDIUM),
                    reasons=[*draft.quality.reasons, "table_split_across_chunks"],
                )
            drafts.append(draft)
        return drafts

    # -- Prose: headings, paragraphs, lists ------------------------------

    def _chunk_prose_run(self, units: list[KnowledgeUnit]) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        buffer_text = ""
        buffer_units: list[KnowledgeUnit] = []

        def flush() -> None:
            nonlocal buffer_text, buffer_units
            if buffer_text.strip():
                starts_new_section = bool(buffer_units) and buffer_units[0].is_heading
                overlap = "" if (starts_new_section or not drafts) else self._overlap_from(drafts[-1])
                content = f"{overlap}{buffer_text}" if overlap else buffer_text
                drafts.append(_draft_from_units(content, buffer_units))
            buffer_text = ""
            buffer_units = []

        for unit in units:
            text = unit.text.strip()
            if not text:
                if unit.metadata or unit.source_reference:
                    # No text, but worth preserving for traceability (a
                    # PDF page with no extractable text): its own chunk.
                    flush()
                    drafts.append(_draft_from_unit(unit.text, unit))
                continue

            if len(text) > self.settings.max_chars:
                flush()
                drafts.extend(self._split_unit_text(unit, text))
                continue

            if unit.is_heading and buffer_text:
                flush()

            candidate = f"{buffer_text}\n\n{text}" if buffer_text else text
            if buffer_text and not (unit.is_heading and not buffer_units) and len(candidate) > self.settings.max_chars:
                flush()
                buffer_text, buffer_units = text, [unit]
            else:
                buffer_text = candidate
                buffer_units.append(unit)

            just_attached_heading = len(buffer_units) == 1 and buffer_units[0].is_heading
            if not just_attached_heading and len(buffer_text) >= self.settings.target_chars:
                flush()

        flush()
        return _enforce_min_size(drafts, self.settings)

    def _split_unit_text(self, unit: KnowledgeUnit, text: str) -> list[ChunkDraft]:
        """Split one oversized unit's own text at sentence boundaries
        where possible, with overlap only within this unit's own pieces."""
        pieces = _split_at_sentence_boundaries(
            text, self.settings.max_chars, self.settings.overlap_chars
        )
        drafts = []
        for index, piece in enumerate(pieces):
            draft = _draft_from_unit(piece, unit)
            if len(pieces) > 1:
                draft.metadata = {**draft.metadata, "unit_part": index, "unit_part_count": len(pieces)}
            drafts.append(draft)
        return drafts

    def _overlap_from(self, previous: ChunkDraft) -> str:
        if self.settings.overlap_chars <= 0 or not previous.content:
            return ""
        tail = previous.content[-self.settings.overlap_chars :].lstrip()
        return f"{tail}\n\n" if tail else ""


def _draft_from_units(text: str, units: list[KnowledgeUnit]) -> ChunkDraft:
    """Build one draft from one-or-more packed units, taking location
    metadata from the *first* (primary) unit but recording the full span
    (e.g. every page a chunk touches) for traceability. Quality is
    reassessed against the final combined `text` (see
    app/ingestion/quality.py's module docstring for why this must not be
    a blind union of each pre-merge unit's own quality)."""
    primary = units[0]
    page_numbers = sorted({u.page_number for u in units if u.page_number is not None})
    metadata = dict(primary.metadata)
    if len(page_numbers) > 1:
        metadata["page_numbers"] = page_numbers

    has_structure = any(_unit_has_structure(u) for u in units)
    source_reasons = [r for u in units for r in u.quality.reasons]
    # extraction_status is a whole-file property (see
    # build_knowledge_units) — every unit in `units` shares the same
    # value, so the primary unit's is as good as any.
    quality = assess_merged_quality(
        text,
        has_structure=has_structure,
        source_reasons=source_reasons,
        extraction_status=primary.extraction_status,
    )
    return ChunkDraft(
        content=text,
        character_count=len(text),
        content_type=primary.content_type,
        page_number=primary.page_number,
        sheet_name=primary.sheet_name,
        row_number=primary.row_number,
        slide_number=primary.slide_number,
        section_title=primary.section_title,
        section_path=primary.section_path,
        source_reference=primary.source_reference,
        quality=quality,
        metadata=metadata,
    )


def _pack_fragments(fragments: list[str], max_chars: int, *, joiner: str) -> list[str]:
    pieces: list[str] = []
    buffer = ""
    for fragment in fragments:
        candidate = f"{buffer}{joiner}{fragment}" if buffer else fragment
        if buffer and len(candidate) > max_chars:
            pieces.append(buffer)
            buffer = fragment
        else:
            buffer = candidate
    if buffer or not pieces:
        pieces.append(buffer)
    return pieces


def _split_at_sentence_boundaries(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Split `text` into pieces of at most `max_chars`, preferring to cut
    at a sentence boundary within the window rather than mid-sentence.
    Adjacent pieces overlap by up to `overlap_chars` so context survives
    the cut. Deterministic and pure — same input, same output, always."""
    if len(text) <= max_chars:
        return [text]

    pieces: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            window = text[start:end]
            boundary = None
            for match in _SENTENCE_BOUNDARY_RE.finditer(window):
                boundary = match.end()
            if boundary and boundary > max_chars * 0.5:
                end = start + boundary
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        start = max(end - overlap_chars, start + 1)
    return pieces


def _enforce_min_size(drafts: list[ChunkDraft], settings: ChunkingSettings) -> list[ChunkDraft]:
    """Merge a too-small trailing draft into its predecessor when they
    share the same section (never blend unrelated sections just to hit a
    size target), and the merge still fits within max_chars."""
    if len(drafts) < 2:
        return drafts
    merged: list[ChunkDraft] = [drafts[0]]
    for draft in drafts[1:]:
        previous = merged[-1]
        same_section = previous.section_path == draft.section_path
        if (
            draft.character_count < settings.min_chars
            and same_section
            and previous.character_count + draft.character_count <= settings.max_chars
        ):
            combined_content = f"{previous.content}\n\n{draft.content}"
            previous.content = combined_content
            previous.character_count = len(combined_content)
            previous.metadata = {**previous.metadata, **draft.metadata}
        else:
            merged.append(draft)
    return merged
