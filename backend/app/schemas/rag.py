"""HTTP request/response shapes for POST /api/v1/knowledge/rag/query.

Distinct from `app/rag/results.py` (the internal `RAGService` return type
this is built from) — the same internal-domain-object/API-schema split
`app/retrieval/results.py`/`app/schemas/retrieval.py` already establish.

**Milestone item 21: the client cannot choose an embedding model or an
LLM provider/model.** No field on `RAGQueryRequest` selects either one —
both are resolved server-side from app settings, exactly like
`RetrievalSearchRequest` never lets a client pick an embedding model.

**Milestone item 22: what this response never contains.** No system
prompt, no raw prompt text, no raw embedding vector, no API key, no
internal database credential, no private storage path.
`RAGResponse.reproducibility` (the internal domain object) is
deliberately *not* projected onto `RAGQueryResponse` below for this same
reason — it exists for the audit trail (see `app/rag/rag_service.py`),
not for exposure over HTTP.
"""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContentType, QualityStatus, VerificationStatus


class RAGFiltersRequest(BaseModel):
    """All fields optional. `organization_id` requests ORGANIZATION-scoped
    knowledge *in addition to* GLOBAL knowledge — omit it for a
    GLOBAL-only query. See `app/api/v1/rag.py` for how this is authorized
    before it ever reaches `RAGService`/`RetrievalService` — identical
    contract to `app/schemas/retrieval.py::RetrievalFiltersRequest`."""

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


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    filters: RAGFiltersRequest = Field(default_factory=RAGFiltersRequest)


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    citation_id: str = Field(description="Stable identifier used in the answer text, e.g. 'E1'.")
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    source_id: uuid.UUID
    source: str
    document: str
    version: str
    location: str | None
    content_type: ContentType
    verification_status: VerificationStatus
    extraction_quality: QualityStatus
    source_authority_level: str | None
    similarity: float
    scope: str = Field(description="GLOBAL | ORGANIZATION")
    organization_id: uuid.UUID | None


class SourceRead(BaseModel):
    source_id: uuid.UUID
    source: str
    scope: str
    verification_status: VerificationStatus


class SourceConflictRead(BaseModel):
    citation_id_a: str
    citation_id_b: str
    statement_a: str
    statement_b: str
    source_a: str
    source_b: str
    version_a: str
    version_b: str
    effective_date_a: str | None
    effective_date_b: str | None


class RAGQueryResponse(BaseModel):
    query: str
    outcome: str = Field(
        description="ANSWERED | INSUFFICIENT_EVIDENCE | SOURCE_CONFLICT | "
        "UNSUPPORTED_CLAIM_REJECTED | PROVIDER_FAILURE | PRIVACY_BLOCKED"
    )
    evidence_state: str = Field(description="SUFFICIENT | PARTIAL | INSUFFICIENT")
    answer: str | None
    citations: list[CitationRead]
    sources: list[SourceRead]
    conflicts: list[SourceConflictRead]
    evidence_count: int
    warnings: list[str]
    abstention_reason: str | None
    retrieval_metadata: dict
    model_metadata: dict | None
    prompt_version: str
