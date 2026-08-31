"""Chunking service — the database-facing half of Knowledge Quality &
Semantic Chunking Foundation v0.1:

    DocumentVersion + NormalizedContent -> Knowledge Units
        -> ChunkingStrategy -> KnowledgeChunk rows

This is deliberately the *only* place `app/ingestion/chunking.py`'s
`StructureAwareChunkingStrategy` is invoked from. It knows nothing about
LLMs, embeddings, or vector databases — those concerns don't exist
anywhere in this call chain (see chunking.py's own docstring for the same
boundary one layer down). Its job is narrower: give a strategy's
`ChunkDraft`s a real document/source/organization identity and persist
them as `KnowledgeChunk` rows.

Called only from `app/services/ingestion_service.py`, and only *after* a
`KnowledgeDocumentVersion` row already exists. Chunking cannot happen
inside `app/ingestion/pipeline.py` (one layer down, DB-independent)
because it needs two things only the database can provide: identity
(which document/source/organization this content belongs to, for the
denormalized columns and metadata snapshot below) and idempotency
(whether this exact version was already chunked).

No public chunk-writing API endpoint exists or should exist — per the
milestone spec, chunk generation is controlled by ingestion processing
only, not by direct client requests.
"""

from sqlalchemy.orm import Session

from app.ingestion.chunking import (
    ChunkDraft,
    ChunkingSettings,
    StructureAwareChunkingStrategy,
)
from app.ingestion.knowledge_unit import build_knowledge_units
from app.ingestion.normalized_content import NormalizedContent
from app.models.enums import ExtractionMethod, ExtractionStatus
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.knowledge_source import KnowledgeSource
from app.schemas.knowledge_chunk import KnowledgeChunkCreate
from app.services.knowledge_chunk_service import knowledge_chunk_service


class ChunkingService:
    def __init__(self, strategy: StructureAwareChunkingStrategy | None = None) -> None:
        # One strategy instance, built from current app settings, reused
        # across calls — chunking is stateless per call (see
        # StructureAwareChunkingStrategy's own determinism guarantee), so
        # there is no per-request state to worry about sharing.
        self._strategy = strategy or StructureAwareChunkingStrategy(
            ChunkingSettings.from_app_settings()
        )

    def generate_chunks(
        self,
        db: Session,
        *,
        document: KnowledgeDocument,
        source: KnowledgeSource,
        version: KnowledgeDocumentVersion,
        normalized_content: list[NormalizedContent],
        extraction_status: ExtractionStatus,
        extraction_method: ExtractionMethod | None,
        warnings: list[str],
    ) -> list[KnowledgeChunk]:
        """Idempotent on `version`: a version that already has chunks is
        returned unchanged rather than re-chunked. Re-chunking would both
        violate the `(document_version_id, chunk_index)` uniqueness
        constraint and, more importantly, duplicate evidence that was
        already persisted for content that (per `content_hash`
        deduplication one layer up, in ingestion_service.py) isn't
        actually new. Reprocessing the same normalized content through the
        same strategy and settings is also fully deterministic (see
        chunking.py), so even a caller that bypassed this check would get
        the same chunk sequence back — this check exists to avoid wasted
        work and duplicate rows, not to paper over nondeterminism.
        """
        existing = knowledge_chunk_service.list_for_version(db, document_version=version)
        if existing:
            return existing

        units = build_knowledge_units(
            normalized_content,
            document_version_id=version.id,
            extraction_status=extraction_status,
            warnings=warnings,
        )
        drafts = self._strategy.chunk(units)
        if not drafts:
            return []

        metadata_snapshot = _source_metadata_snapshot(document=document, source=source, version=version)

        chunks_in = [
            _draft_to_create(
                draft,
                index=index,
                document=document,
                extraction_method=extraction_method,
                metadata_snapshot=metadata_snapshot,
            )
            for index, draft in enumerate(drafts)
        ]
        return knowledge_chunk_service.create_many(db, document_version=version, chunks_in=chunks_in)


def _source_metadata_snapshot(
    *,
    document: KnowledgeDocument,
    source: KnowledgeSource,
    version: KnowledgeDocumentVersion,
) -> dict:
    """A point-in-time copy of metadata that is *owned* elsewhere
    (KnowledgeDocument.language, KnowledgeSource.jurisdiction/
    industry_sector/authority_level/verification_status,
    KnowledgeDocumentVersion.publication_date/effective_date) — see
    app/models/knowledge_chunk.py's docstring for why these are recorded
    as a metadata snapshot rather than live columns/joins. A future
    retrieval filter can read this snapshot without a join; anything that
    needs the *current* value instead of the value-as-of-chunking still
    queries the owning table directly. Only non-None values are included
    to keep the metadata blob free of clutter.
    """
    snapshot = {
        "language": document.language,
        "jurisdiction": source.jurisdiction,
        "industry_sector": source.industry_sector,
        "authority_level": source.authority_level,
        "verification_status": (
            source.verification_status.value if source.verification_status else None
        ),
        "publication_date": (
            version.publication_date.isoformat() if version.publication_date else None
        ),
        "effective_date": version.effective_date.isoformat() if version.effective_date else None,
    }
    return {key: value for key, value in snapshot.items() if value is not None}


def _draft_to_create(
    draft: ChunkDraft,
    *,
    index: int,
    document: KnowledgeDocument,
    extraction_method: ExtractionMethod | None,
    metadata_snapshot: dict,
) -> KnowledgeChunkCreate:
    metadata = dict(draft.metadata)
    metadata.update(draft.quality.as_metadata())
    if metadata_snapshot:
        metadata["source_metadata_snapshot"] = metadata_snapshot

    return KnowledgeChunkCreate(
        chunk_index=index,
        content=draft.content,
        character_count=draft.character_count,
        document_id=document.id,
        source_id=document.source_id,
        # Denormalized straight from the document, not re-derived — this
        # is the same value KnowledgeDocument.organization_id itself was
        # derived from at document-creation time (see that model's
        # docstring), so a chunk's tenant identity can never drift from
        # its document's.
        organization_id=document.organization_id,
        content_type=draft.content_type,
        page_number=draft.page_number,
        sheet_name=draft.sheet_name,
        row_number=draft.row_number,
        slide_number=draft.slide_number,
        section_title=draft.section_title,
        section_path=draft.section_path,
        source_reference=draft.source_reference,
        extraction_method=extraction_method,
        quality_status=draft.quality.status,
        chunk_metadata=metadata,
    )


chunking_service = ChunkingService()
