"""IngestionJob service — one immutable-ish record per ingestion attempt.
See app/models/ingestion_job.py for the current-state/history split this
mirrors from KnowledgeDocument/KnowledgeDocumentVersion.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.enums import IngestionJobStatus
from app.models.ingestion_job import IngestionJob


class IngestionJobService:
    def create(
        self,
        db: Session,
        *,
        file_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        source_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
    ) -> IngestionJob:
        job = IngestionJob(
            file_id=file_id,
            organization_id=organization_id,
            source_id=source_id,
            document_id=document_id,
            status=IngestionJobStatus.RECEIVED,
            started_at=utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def get(self, db: Session, *, id: uuid.UUID) -> IngestionJob | None:
        return db.get(IngestionJob, id)

    def mark_status(
        self,
        db: Session,
        *,
        job: IngestionJob,
        status: IngestionJobStatus,
        document_id: uuid.UUID | None = None,
        error_message: str | None = None,
    ) -> IngestionJob:
        job.status = status
        if document_id is not None:
            job.document_id = document_id
        if error_message is not None:
            job.error_message = error_message
        if status in (
            IngestionJobStatus.COMPLETED,
            IngestionJobStatus.FAILED,
            IngestionJobStatus.CANCELLED,
        ):
            job.completed_at = utcnow()
        db.add(job)
        db.commit()
        db.refresh(job)
        return job


ingestion_job_service = IngestionJobService()
