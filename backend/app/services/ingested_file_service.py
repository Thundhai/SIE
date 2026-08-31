"""IngestedFile service — thin CRUD/status-transition layer over the
file-metadata table. See app/models/ingested_file.py for why this isn't
built on TenantScopedRepository (nullable organization_id, and it's
written almost exclusively by app/services/ingestion_service.py rather
than read generically)."""

import uuid

from sqlalchemy.orm import Session

from app.models.enums import ExtractionMethod, ExtractionStatus, IngestionJobStatus
from app.models.ingested_file import IngestedFile


class IngestedFileService:
    def create(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID | None,
        original_filename: str,
        detected_media_type: str,
        file_extension: str,
        file_size: int,
        content_hash: str,
        storage_reference: str,
    ) -> IngestedFile:
        file = IngestedFile(
            organization_id=organization_id,
            original_filename=original_filename,
            detected_media_type=detected_media_type,
            file_extension=file_extension,
            file_size=file_size,
            content_hash=content_hash,
            storage_reference=storage_reference,
        )
        db.add(file)
        db.commit()
        db.refresh(file)
        return file

    def get(self, db: Session, *, id: uuid.UUID) -> IngestedFile | None:
        return db.get(IngestedFile, id)

    def update_status(
        self,
        db: Session,
        *,
        file: IngestedFile,
        ingestion_status: IngestionJobStatus | None = None,
        extraction_status: ExtractionStatus | None = None,
        extraction_method: ExtractionMethod | None = None,
    ) -> IngestedFile:
        if ingestion_status is not None:
            file.ingestion_status = ingestion_status
        if extraction_status is not None:
            file.extraction_status = extraction_status
        if extraction_method is not None:
            file.extraction_method = extraction_method
        db.add(file)
        db.commit()
        db.refresh(file)
        return file


ingested_file_service = IngestedFileService()
