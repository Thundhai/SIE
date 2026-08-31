import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeChunkCreate(BaseModel):
    """Body for creating a single KnowledgeChunk.

    Not one of the schemas explicitly named in the milestone spec (which
    lists only KnowledgeChunkRead), added because
    KnowledgeChunkService.create_many needs a typed input. There is no
    HTTP endpoint for chunk creation in this milestone — chunks are
    created through the service layer only, for a future ingestion worker
    to call — so this schema is consumed internally, not from a request
    body, but is still the appropriate typed boundary for that call.
    `document_version_id` is not a field here: it is supplied once by the
    caller of `create_many` for the whole batch, not per chunk.
    """

    chunk_index: int = Field(..., ge=0)
    content: str = Field(..., min_length=1)
    character_count: int = Field(..., ge=0)
    page_number: int | None = Field(default=None, ge=0)
    section_title: str | None = Field(default=None, max_length=500)
    chunk_metadata: dict[str, Any] | None = None


class KnowledgeChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_version_id: uuid.UUID
    chunk_index: int
    content: str
    character_count: int
    page_number: int | None
    section_title: str | None
    chunk_metadata: dict[str, Any] | None
    created_at: datetime
