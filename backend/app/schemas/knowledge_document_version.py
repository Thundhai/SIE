import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IngestionStatus


class KnowledgeDocumentVersionCreate(BaseModel):
    """Body for creating a KnowledgeDocumentVersion.

    Not one of the schemas explicitly named in the milestone spec, but
    required for the `POST .../versions` endpoint it does name to have a
    request body at all. `document_id` is intentionally not a field here:
    it comes from the URL path, matching how Site/DataSource creation
    already derives their parent from the path rather than the body.
    """

    version_label: str = Field(..., min_length=1, max_length=100)
    content_hash: str = Field(..., min_length=1, max_length=128)
    storage_reference: str = Field(..., min_length=1, max_length=1000)
    extracted_text: str | None = None
    publication_date: date | None = None
    effective_date: date | None = None
    ingestion_status: IngestionStatus = IngestionStatus.RECEIVED


class KnowledgeDocumentVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_label: str
    content_hash: str
    storage_reference: str
    extracted_text: str | None
    publication_date: date | None
    effective_date: date | None
    superseded_at: datetime | None
    ingestion_status: IngestionStatus
    created_at: datetime
