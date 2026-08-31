"""Ingestion service — the database-facing half of the ingestion engine.

    Authenticated user -> TenantContext -> authorized organization
        -> ingestion  (this module, called only after the API layer has
                        already authorized the caller — see
                        app/api/v1/ingestion.py)

Everything upstream of the database (detection, validation, hashing,
extraction, normalization, chunking) is `app/ingestion/pipeline.py`,
called from here exactly once. This module's own job is the pipeline
diagram's remaining stages — source/document association, persistence,
and provenance — all of it built on the *existing* Knowledge Foundation
services (`knowledge_document_service`, `knowledge_document_version_service`,
`knowledge_chunk_service`) rather than any new tenant-isolation or
document-versioning mechanism: a document's organization_id is still
derived from its source exactly as before this milestone, and a
duplicate `content_hash` still reuses the existing version instead of
creating a new one.

Two distinct failure shapes on `ingest()`:

  * `IngestionRequestError` — the request itself is invalid (oversized
    file, missing required field, a document_id that doesn't belong to
    the given source). Raised before anything is written to the
    database; the API layer maps this to 400.
  * A resulting `IngestionOutcome` with `job.status == FAILED` — the
    request was well-formed and the file's type is supported, but this
    specific file could not be parsed (corrupt content, etc.). This is
    not an HTTP error: a file, a job, and (if resolved) a document all
    exist and are queryable, recording exactly what went wrong — see the
    "fail safely" quality principle. The API layer still returns 201.

`UnsupportedFileTypeError` (from pipeline.py) is deliberately not caught
here — it propagates to the API layer as-is and is mapped to 415, with
no database rows created at all, since there is nothing yet to
associate with a source/document.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.ingestion.hashing import sha256_hex
from app.ingestion.pipeline import (
    FileExtractionError,
    FileValidationError,
    PipelineOutcome,
    detect_supported_type,
    extract_and_normalize,
)
from app.ingestion.storage import StorageProvider, get_storage_provider
from app.models.enums import ExtractionStatus, IngestionJobStatus, IngestionStatus
from app.models.ingested_file import IngestedFile
from app.models.ingestion_job import IngestionJob
from app.models.knowledge_document import KnowledgeDocument
from app.schemas.knowledge_chunk import KnowledgeChunkCreate
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate
from app.services.audit_service import AuditAction, audit_service
from app.services.errors import KnowledgeNotFoundError
from app.services.ingested_file_service import ingested_file_service
from app.services.ingestion_job_service import ingestion_job_service
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import knowledge_document_version_service

_MAX_STORED_EXTRACTED_TEXT_CHARS = 50_000


class IngestionRequestError(ValueError):
    """The ingestion request itself is invalid — see module docstring.
    Mapped to HTTP 400 by app/api/v1/ingestion.py."""


@dataclass
class IngestionOutcome:
    job: IngestionJob
    file: IngestedFile
    document: KnowledgeDocument | None
    version_id: uuid.UUID | None
    chunk_count: int
    warnings: list[str]


class IngestionService:
    def __init__(self, storage: StorageProvider | None = None) -> None:
        self._storage = storage

    def _storage_provider(self) -> StorageProvider:
        return self._storage or get_storage_provider()

    def ingest(
        self,
        db: Session,
        *,
        file_bytes: bytes,
        filename: str,
        source_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        document_id: uuid.UUID | None = None,
        title: str | None = None,
        document_type: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> IngestionOutcome:
        if not file_bytes:
            raise IngestionRequestError("Uploaded file is empty.")
        if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise IngestionRequestError(
                f"File exceeds the maximum upload size of {settings.MAX_UPLOAD_SIZE_BYTES} bytes."
            )

        # Detection only — no parsing yet, no database writes yet. Lets an
        # unsupported type be rejected (see docstring) before we touch
        # source/document association at all.
        detected, adapter = detect_supported_type(file_bytes, filename=filename)

        document = self._resolve_document(
            db,
            source_id=source_id,
            organization_id=organization_id,
            document_id=document_id,
            title=title,
            document_type=document_type or adapter.content_category,
            actor_user_id=actor_user_id,
        )

        content_hash = sha256_hex(file_bytes)
        storage_reference = self._storage_provider().save(
            content_hash=content_hash, extension=detected.extension, data=file_bytes
        )

        file = ingested_file_service.create(
            db,
            organization_id=organization_id,
            original_filename=filename,
            detected_media_type=detected.media_type,
            file_extension=detected.extension,
            file_size=len(file_bytes),
            content_hash=content_hash,
            storage_reference=storage_reference,
        )
        job = ingestion_job_service.create(
            db,
            file_id=file.id,
            organization_id=organization_id,
            source_id=source_id,
            document_id=document.id,
        )
        audit_service.log(
            db,
            action=AuditAction.INGESTION_STARTED,
            resource_type="IngestionJob",
            resource_id=job.id,
            organization_id=organization_id,
            user_id=actor_user_id,
            metadata={"filename": filename, "detected_media_type": detected.media_type},
        )

        ingestion_job_service.mark_status(db, job=job, status=IngestionJobStatus.VALIDATING)
        ingestion_job_service.mark_status(db, job=job, status=IngestionJobStatus.PROCESSING)

        try:
            outcome = extract_and_normalize(file_bytes, filename=filename, adapter=adapter)
        except (FileValidationError, FileExtractionError) as exc:
            return self._fail(
                db,
                job=job,
                file=file,
                document=document,
                error_message=str(exc),
                actor_user_id=actor_user_id,
                organization_id=organization_id,
            )

        return self._complete(
            db,
            job=job,
            file=file,
            document=document,
            storage_reference=storage_reference,
            outcome=outcome,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
        )

    def _resolve_document(
        self,
        db: Session,
        *,
        source_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        document_id: uuid.UUID | None,
        title: str | None,
        document_type: str,
        actor_user_id: uuid.UUID | None,
    ) -> KnowledgeDocument:
        if document_id is not None:
            document = knowledge_document_service.get(
                db, id=document_id, organization_id=organization_id
            )
            if document is None:
                raise KnowledgeNotFoundError(f"knowledge document {document_id} not found")
            if document.source_id != source_id:
                raise IngestionRequestError(
                    "document_id does not belong to the given source_id."
                )
            return document

        if not title:
            raise IngestionRequestError(
                "title is required when document_id is not provided (a new document "
                "would otherwise be created with no name)."
            )
        # Reuses the Knowledge Foundation's own source/organization
        # consistency validation in full — see
        # app/services/knowledge_document_service.py::create. This
        # service does not re-implement any part of that check.
        return knowledge_document_service.create(
            db,
            obj_in=KnowledgeDocumentCreate(
                source_id=source_id,
                organization_id=organization_id,
                title=title,
                document_type=document_type,
            ),
            actor_user_id=actor_user_id,
        )

    def _fail(
        self,
        db: Session,
        *,
        job: IngestionJob,
        file: IngestedFile,
        document: KnowledgeDocument,
        error_message: str,
        actor_user_id: uuid.UUID | None,
        organization_id: uuid.UUID | None,
    ) -> IngestionOutcome:
        ingested_file_service.update_status(
            db, file=file, ingestion_status=IngestionJobStatus.FAILED
        )
        job = ingestion_job_service.mark_status(
            db, job=job, status=IngestionJobStatus.FAILED, error_message=error_message
        )
        audit_service.log(
            db,
            action=AuditAction.INGESTION_FAILED,
            resource_type="IngestionJob",
            resource_id=job.id,
            organization_id=organization_id,
            user_id=actor_user_id,
            metadata={"error_message": error_message},
        )
        return IngestionOutcome(
            job=job, file=file, document=document, version_id=None, chunk_count=0, warnings=[]
        )

    def _complete(
        self,
        db: Session,
        *,
        job: IngestionJob,
        file: IngestedFile,
        document: KnowledgeDocument,
        storage_reference: str,
        outcome: PipelineOutcome,
        actor_user_id: uuid.UUID | None,
        organization_id: uuid.UUID | None,
    ) -> IngestionOutcome:
        version_ingestion_status = (
            IngestionStatus.FAILED
            if outcome.extraction_status == ExtractionStatus.FAILED
            else IngestionStatus.PROCESSED
        )
        version = knowledge_document_version_service.create(
            db,
            document=document,
            obj_in=KnowledgeDocumentVersionCreate(
                version_label=self._next_version_label(db, document),
                content_hash=outcome.content_hash,
                storage_reference=storage_reference,
                extracted_text=_summarize_text(outcome),
                ingestion_status=version_ingestion_status,
            ),
            actor_user_id=actor_user_id,
        )

        # knowledge_document_version_service.create() is idempotent on
        # content_hash (see its own docstring) and returns the *existing*
        # version, unchanged, when this content was already ingested for
        # this document — including chunks it already has. Re-chunking in
        # that case would violate the (document_version_id, chunk_index)
        # uniqueness constraint and, worse, duplicate content that isn't
        # actually new. So: only chunk a version that doesn't have any yet.
        existing_chunks = knowledge_chunk_service.list_for_version(db, document_version=version)
        if existing_chunks:
            chunk_count = len(existing_chunks)
        elif outcome.chunk_drafts:
            chunks_in = [
                KnowledgeChunkCreate(
                    chunk_index=index,
                    content=draft.content,
                    character_count=draft.character_count,
                    page_number=draft.page_number,
                    section_title=draft.section_title,
                    chunk_metadata=draft.metadata,
                )
                for index, draft in enumerate(outcome.chunk_drafts)
            ]
            created = knowledge_chunk_service.create_many(
                db, document_version=version, chunks_in=chunks_in
            )
            chunk_count = len(created)
        else:
            chunk_count = 0

        ingested_file_service.update_status(
            db,
            file=file,
            ingestion_status=IngestionJobStatus.COMPLETED,
            extraction_status=outcome.extraction_status,
            extraction_method=outcome.extraction_method,
        )
        job = ingestion_job_service.mark_status(
            db, job=job, status=IngestionJobStatus.COMPLETED, document_id=document.id
        )
        audit_service.log(
            db,
            action=AuditAction.INGESTION_COMPLETED,
            resource_type="IngestionJob",
            resource_id=job.id,
            organization_id=organization_id,
            user_id=actor_user_id,
            metadata={
                "document_id": str(document.id),
                "version_id": str(version.id),
                "chunk_count": chunk_count,
                "extraction_status": outcome.extraction_status.value,
            },
        )

        return IngestionOutcome(
            job=job,
            file=file,
            document=document,
            version_id=version.id,
            chunk_count=chunk_count,
            warnings=outcome.warnings,
        )

    def _next_version_label(self, db: Session, document: KnowledgeDocument) -> str:
        existing = knowledge_document_version_service.list_for_document(db, document=document)
        return f"v{len(existing) + 1}"


def _summarize_text(outcome: PipelineOutcome) -> str | None:
    parts = [item.text for item in outcome.normalized_content if item.text.strip()]
    if not parts:
        return None
    text = "\n\n".join(parts)
    if len(text) > _MAX_STORED_EXTRACTED_TEXT_CHARS:
        text = text[:_MAX_STORED_EXTRACTED_TEXT_CHARS] + "\n\n[truncated]"
    return text


ingestion_service = IngestionService()
