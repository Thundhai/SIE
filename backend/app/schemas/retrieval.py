"""HTTP request/response shapes for POST /api/v1/knowledge/retrieval/search.

Distinct from `app/retrieval/results.py` (the internal `RetrievalService`
return type this is built from) — the same
internal-domain-object/API-schema split used throughout this codebase.
`organization_id` lives inside `RetrievalFiltersRequest` because it is
part of what the *client asks for*, but it is never trusted at face
value: `app/api/v1/retrieval.py` authorizes it before it ever reaches
`RetrievalService` — see that route's own docstring.
"""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ContentType,
    ExtractionMethod,
    QualityStatus,
    VerificationStatus,
)


class RetrievalFiltersRequest(BaseModel):
    """All fields optional. `organization_id` requests ORGANIZATION-scoped
    knowledge *in addition to* GLOBAL knowledge — omit it for a
    GLOBAL-only search. See the README's tenant isolation section."""

    organization_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    document_version_id: uuid.UUID | None = None
    content_type: ContentType | None = None
    industry_sector: str | None = None
    jurisdiction: str | None = None
    verification_status: VerificationStatus | None = None
    effective_date_from: date | None = None
    effective_date_to: date | None = None


class RetrievalSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    min_similarity: float | None = Field(default=None, ge=-1.0, le=1.0)
    filters: RetrievalFiltersRequest = Field(default_factory=RetrievalFiltersRequest)


class RetrievalResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    chunk_id: uuid.UUID
    similarity: float = Field(
        description="Cosine similarity to the query, in [-1, 1]. A vector-closeness "
        "score, not a confidence or truth judgment — see the README."
    )
    relevance: str = Field(description="HIGH | MODERATE | LOW — a bucketed label over "
        "`similarity`, never called 'confidence'.")
    content: str
    content_type: ContentType

    source_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    source: str = Field(description="Source name, e.g. '29 CFR 1910'.")
    document: str = Field(description="Document title.")
    version: str = Field(description="Document version label, e.g. 'v1'.")

    location: str | None = Field(
        description="Human-readable locator, e.g. 'Page 47, Section 6.2' or 'Slide 17'."
    )
    page_number: int | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    slide_number: int | None = None
    section_title: str | None = None
    section_path: list[str] | None = None

    extraction_quality: QualityStatus
    extraction_method: ExtractionMethod | None
    source_authority_level: str | None
    verification_status: VerificationStatus

    scope: str = Field(description="GLOBAL | ORGANIZATION")
    organization_id: uuid.UUID | None

    jurisdiction: str | None = None
    industry_sector: str | None = None
    publication_date: str | None = None
    effective_date: str | None = None


class EmbeddingModelRead(BaseModel):
    provider: str
    model_name: str
    model_version: str


class RetrievalSearchResponse(BaseModel):
    query: str
    outcome: str = Field(description="RESULTS | NO_RELEVANT_EVIDENCE")
    embedding_model: EmbeddingModelRead
    results: list[RetrievalResultRead]
    result_count: int
    filters_applied: dict
    search_metadata: dict
