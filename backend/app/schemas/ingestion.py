import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ExtractionMethod, ExtractionStatus, IngestionJobStatus


class IngestionResponse(BaseModel):
    """Response body for `POST /api/v1/knowledge/ingestion`.

    Deliberately does not include the extracted document content itself
    (per spec) — a client fetches that separately via the existing
    knowledge document/version/chunk read endpoints, using the ids
    returned here.
    """

    ingestion_job_id: uuid.UUID
    file_id: uuid.UUID
    detected_media_type: str
    file_size: int
    content_hash: str
    ingestion_status: IngestionJobStatus
    extraction_status: ExtractionStatus
    extraction_method: ExtractionMethod | None
    document_id: uuid.UUID | None
    version_id: uuid.UUID | None
    chunk_count: int
    warnings: list[str]


class IngestedFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    original_filename: str
    detected_media_type: str
    file_extension: str
    file_size: int
    content_hash: str
    ingestion_status: IngestionJobStatus
    extraction_status: ExtractionStatus
    extraction_method: ExtractionMethod | None
    created_at: datetime
    updated_at: datetime


class IngestionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    source_id: uuid.UUID | None
    document_id: uuid.UUID | None
    file_id: uuid.UUID
    status: IngestionJobStatus
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
