"""Provenance / lineage lookup.

SIE's provenance guarantee — every knowledge record is traceable back to
its source, document, version, and (for a chunk) ingestion event — is
established structurally, through the foreign key chain:

    KnowledgeChunk.document_version_id
        -> KnowledgeDocumentVersion.document_id
            -> KnowledgeDocument.source_id
                -> KnowledgeSource

`KnowledgeDocumentVersion` doubles as the "ingestion event" for now: its
`ingestion_status` and `created_at` record when and how that version's
content was received and processed, rather than there being a separate
ingestion-event table. Per the milestone's own instruction not to
overengineer a separate event system before one is needed, no such table
exists yet — this module is deliberately just a read-side helper that
walks the relationships above, not a new data model.

No new table is introduced here. This module exists so that lineage
lookups are exercised, tested, and available as a stable call site, ahead
of any feature (evidence citation, freshness monitoring) that will need
them.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion


def get_chunk_provenance(db: Session, *, chunk_id: uuid.UUID) -> dict[str, Any] | None:
    """Return the full lineage for one chunk: source, document, version,
    and the chunk itself. Returns None if the chunk doesn't exist.

    This performs no tenant filtering of its own — callers must resolve
    and authorize the chunk (or its document/version) through the normal
    tenant-scoped service methods first, exactly as with any other
    internal resolution helper in this codebase.
    """
    stmt = (
        select(KnowledgeChunk)
        .options(
            joinedload(KnowledgeChunk.document_version)
            .joinedload(KnowledgeDocumentVersion.document)
            .joinedload(KnowledgeDocument.source)
        )
        .where(KnowledgeChunk.id == chunk_id)
    )
    chunk = db.execute(stmt).unique().scalar_one_or_none()
    if chunk is None:
        return None

    version = chunk.document_version
    document = version.document
    source = document.source

    return {
        "chunk_id": chunk.id,
        "document_version_id": version.id,
        "document_id": document.id,
        "source_id": source.id,
        "organization_id": document.organization_id,
        "ingestion_status": version.ingestion_status,
    }
