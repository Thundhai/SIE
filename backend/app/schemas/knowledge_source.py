import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ScopeType, VerificationStatus


class KnowledgeSourceBase(BaseModel):
    publisher: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., min_length=1, max_length=100)
    jurisdiction: str | None = Field(default=None, max_length=100)
    industry_sector: str | None = Field(default=None, max_length=100)
    authority_level: str | None = Field(default=None, max_length=100)
    external_reference: str | None = None
    publication_date: date | None = None
    review_date: date | None = None


class KnowledgeSourceCreate(KnowledgeSourceBase):
    """Body for creating a KnowledgeSource.

    Unlike Site/DataSource, a KnowledgeSource has no parent organization in
    its URL — `/api/v1/knowledge/sources` is not nested under an
    organization — so tenant context has to be explicit in the body itself:
    `scope_type` states the caller's intent, and `organization_id` is
    required if and only if `scope_type` is ORGANIZATION. The service layer
    re-validates this (and that the organization actually exists) rather
    than trusting the model_validator alone.
    """

    scope_type: ScopeType
    organization_id: uuid.UUID | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING

    @model_validator(mode="after")
    def _check_scope_organization_consistency(self) -> "KnowledgeSourceCreate":
        if self.scope_type == ScopeType.GLOBAL and self.organization_id is not None:
            raise ValueError("organization_id must be omitted for a GLOBAL knowledge source")
        if self.scope_type == ScopeType.ORGANIZATION and self.organization_id is None:
            raise ValueError(
                "organization_id is required for an ORGANIZATION-scoped knowledge source"
            )
        return self


class KnowledgeSourceRead(KnowledgeSourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope_type: ScopeType
    organization_id: uuid.UUID | None
    verification_status: VerificationStatus
    created_at: datetime
    updated_at: datetime
