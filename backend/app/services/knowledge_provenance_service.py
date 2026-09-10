"""Provenance / lineage lookup.

SIE's provenance guarantee — every knowledge record is traceable back to
its source, document, version, and (for a chunk) ingestion event — is
established structurally, through the foreign key chain:

    KnowledgeChunk.document_version_id
        -> KnowledgeDocumentVersion.document_id
            -> KnowledgeDocument.source_id
                -> KnowledgeSource

`KnowledgeDocumentVersion` doubles as the "ingestion event" for
non-file-based knowledge; where a version *did* come from an uploaded
file (see app/services/ingestion_service.py), the full chain extends one
step further:

    IngestionJob.file_id -> IngestedFile.content_hash
        == KnowledgeDocumentVersion.content_hash (same document)

`IngestionJob` deliberately has no `document_version_id` foreign key of
its own (see app/models/ingestion_job.py's docstring for why) — the join
above, by `content_hash` within the job's own `document_id`, is how
`get_ingestion_provenance` below recovers it without one, extending the
same "no new event table" principle the module docstring already
described to cover the ingestion engine's own provenance requirement too.

No new table is introduced here. This module exists so that lineage
lookups are exercised, tested, and available as a stable call site, ahead
of any feature (evidence citation, freshness monitoring) that will need
them.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.ingested_file import IngestedFile
from app.models.ingestion_job import IngestionJob
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


def get_ingestion_provenance(db: Session, *, ingestion_job_id: uuid.UUID) -> dict[str, Any] | None:
    """Return the full lineage for one ingestion job: file, job, document,
    version (if one was created or reused), and every chunk that version
    has. Returns None if the job doesn't exist.

    Same no-tenant-filtering contract as `get_chunk_provenance` — callers
    resolve/authorize first.
    """
    job = db.get(IngestionJob, ingestion_job_id)
    if job is None:
        return None

    file = db.get(IngestedFile, job.file_id)

    version = None
    if job.document_id is not None and file is not None:
        stmt = select(KnowledgeDocumentVersion).where(
            KnowledgeDocumentVersion.document_id == job.document_id,
            KnowledgeDocumentVersion.content_hash == file.content_hash,
        )
        version = db.execute(stmt).scalar_one_or_none()

    chunk_ids: list[uuid.UUID] = []
    if version is not None:
        chunk_stmt = select(KnowledgeChunk.id).where(
            KnowledgeChunk.document_version_id == version.id
        )
        chunk_ids = list(db.execute(chunk_stmt).scalars().all())

    return {
        "file_id": file.id if file else None,
        "ingestion_job_id": job.id,
        "document_id": job.document_id,
        "source_id": job.source_id,
        "document_version_id": version.id if version else None,
        "chunk_ids": chunk_ids,
    }
