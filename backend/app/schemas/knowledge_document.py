import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    document_type: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    language: str | None = Field(default=None, max_length=20)
    external_document_id: str | None = Field(default=None, max_length=255)


class KnowledgeDocumentCreate(KnowledgeDocumentBase):
    """Body for creating a KnowledgeDocument.

    `source_id` identifies the parent source; the document's
    `organization_id` is never taken from this field directly — it is
    always derived server-side from that source's own `organization_id`
    (see KnowledgeDocumentService.create). `organization_id` here is
    optional and, when supplied, must exactly match what the source
    resolves to: it is an explicit assertion of the tenant context the
    caller expects, not a way to set it. A mismatch (or a missing value
    where one is required) is rejected rather than silently corrected, so
    a caller can never attach a document to a different organization than
    its source, and can never accidentally create it un-scoped.
    """

    source_id: uuid.UUID
    organization_id: uuid.UUID | None = None


class KnowledgeDocumentRead(KnowledgeDocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    organization_id: uuid.UUID | None
    current_version_id: uuid.UUID | None
    status: str
    created_at: datetime
    updated_at: datetime
