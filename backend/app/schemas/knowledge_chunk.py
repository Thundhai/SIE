import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContentType, ExtractionMethod, QualityStatus


class KnowledgeChunkCreate(BaseModel):
    """Body for creating a single KnowledgeChunk.

    Not one of the schemas explicitly named in the milestone spec (which
    lists only KnowledgeChunkRead), added because
    KnowledgeChunkService.create_many needs a typed input. There is no
    HTTP endpoint for chunk creation — chunks are created through the
    service layer only, driven by app/services/chunking_service.py during
    ingestion — so this schema is consumed internally, not from a request
    body, but is still the appropriate typed boundary for that call.
    `document_version_id` is not a field here: it is supplied once by the
    caller of `create_many` for the whole batch, not per chunk.

    `content` deliberately allows an empty string (unlike the original
    Knowledge Foundation version of this schema, which required
    `min_length=1`): a blank scanned page or an image with no OCR result
    is still a real, citable chunk recording *that* extraction produced
    nothing — see app/ingestion/quality.py's "do not pretend content was
    understood" principle — and must not be rejected at the schema layer.
    `quality_status`/`character_count` are what actually communicate that
    such a chunk has near-zero informational value, not the schema
    forbidding it from existing.
    """

    chunk_index: int = Field(..., ge=0)
    content: str = Field(default="")
    character_count: int = Field(..., ge=0)

    document_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None

    content_type: ContentType = ContentType.TEXT
    page_number: int | None = Field(default=None, ge=0)
    sheet_name: str | None = Field(default=None, max_length=255)
    row_number: int | None = Field(default=None, ge=0)
    slide_number: int | None = Field(default=None, ge=0)
    section_title: str | None = Field(default=None, max_length=500)
    section_path: list[str] | None = None
    source_reference: str | None = Field(default=None, max_length=500)
    extraction_method: ExtractionMethod | None = None
    quality_status: QualityStatus

    chunk_metadata: dict[str, Any] | None = None


class KnowledgeChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_version_id: uuid.UUID
    document_id: uuid.UUID | None
    source_id: uuid.UUID | None
    organization_id: uuid.UUID | None

    chunk_index: int
    content: str
    character_count: int
    content_type: ContentType

    page_number: int | None
    sheet_name: str | None
    row_number: int | None
    slide_number: int | None
    section_title: str | None
    section_path: list[str] | None
    source_reference: str | None
    extraction_method: ExtractionMethod | None
    quality_status: QualityStatus

    chunk_metadata: dict[str, Any] | None
    created_at: datetime
