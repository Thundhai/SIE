"""ChunkingStrategy — the architectural boundary for turning normalized
content into KnowledgeChunk rows, per the milestone spec:

    Normalized content -> ChunkingStrategy -> KnowledgeChunk

Only the interface and one simple, deterministic default implementation
are built in this milestone — no semantic/embedding-aware chunking (that
is explicitly out of scope; see the README). `SimpleChunkingStrategy`
below chunks each `NormalizedContent` on paragraph boundaries with a
maximum character size, and — this is the part that actually matters for
this milestone — carries every location field
(page/sheet/row/slide/section/source_reference) from the source content
straight through onto each resulting chunk, split or not. Losing that
metadata during chunking would defeat the whole point of the location
tracking the format adapters just did.
"""

from dataclasses import dataclass
from typing import Protocol

from app.ingestion.normalized_content import NormalizedContent

_DEFAULT_MAX_CHUNK_CHARS = 1500


@dataclass
class ChunkDraft:
    """One chunk's worth of content, still detached from any
    KnowledgeDocumentVersion — the ingestion service assigns
    `chunk_index` and persists these as KnowledgeChunk rows (see
    app/services/knowledge_chunk_service.py, unchanged by this
    milestone)."""

    content: str
    character_count: int
    page_number: int | None
    section_title: str | None
    metadata: dict


class ChunkingStrategy(Protocol):
    def chunk(self, contents: list[NormalizedContent]) -> list[ChunkDraft]: ...


class SimpleChunkingStrategy:
    """Deterministic paragraph-based chunking: each `NormalizedContent`
    is split on blank-line paragraph boundaries, then greedily packed
    into chunks up to `max_chars`. A `NormalizedContent` with no natural
    paragraph breaks (a spreadsheet row, a slide, a short page) becomes
    exactly one chunk. Not semantic chunking — a future
    `SemanticChunkingStrategy` implementing the same interface can
    replace this without touching the ingestion service that calls it.
    """

    def __init__(self, max_chars: int = _DEFAULT_MAX_CHUNK_CHARS) -> None:
        self.max_chars = max_chars

    def chunk(self, contents: list[NormalizedContent]) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        for item in contents:
            drafts.extend(self._chunk_one(item))
        return drafts

    def _chunk_one(self, item: NormalizedContent) -> list[ChunkDraft]:
        paragraphs = [p.strip() for p in item.text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [item.text] if item.text.strip() else []
        if not paragraphs:
            # No text at all (e.g. an image, or an empty page) — still
            # worth a chunk if there's location metadata to preserve,
            # otherwise skip it rather than persist an empty, useless row.
            if not (item.metadata or item.source_reference):
                return []
            paragraphs = [""]

        location_metadata = self._location_metadata(item)

        drafts: list[ChunkDraft] = []
        buffer = ""
        for paragraph in paragraphs:
            candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            if buffer and len(candidate) > self.max_chars:
                drafts.append(self._draft(buffer, item, location_metadata))
                buffer = paragraph
            else:
                buffer = candidate
        if buffer or not drafts:
            drafts.append(self._draft(buffer, item, location_metadata))
        return drafts

    def _location_metadata(self, item: NormalizedContent) -> dict:
        location = {
            "content_type": item.content_type.value,
            "sheet_name": item.sheet_name,
            "row_number": item.row_number,
            "slide_number": item.slide_number,
            "source_reference": item.source_reference,
        }
        location = {k: v for k, v in location.items() if v is not None}
        location.update(item.metadata)
        return location

    def _draft(self, text: str, item: NormalizedContent, location_metadata: dict) -> ChunkDraft:
        return ChunkDraft(
            content=text,
            character_count=len(text),
            page_number=item.page_number,
            section_title=item.section_title,
            metadata=location_metadata,
        )
