"""Retrieval result shapes — domain dataclasses returned by
`RetrievalService.search()`. Distinct from `app/schemas/retrieval.py`
(the Pydantic API request/response shapes), the same separation already
used throughout this codebase between an internal service's own return
type and the HTTP-facing schema built from it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

from app.models.enums import (
    ContentType,
    ExtractionMethod,
    QualityStatus,
    VerificationStatus,
)


class RelevanceLevel(str, Enum):
    """A human-readable bucket over the raw similarity score — never
    called "confidence" anywhere in this codebase (see the README):
    similarity is a measure of vector closeness, not of whether a result
    is true. Boundaries are `app.core.config.settings.RETRIEVAL_*_SIMILARITY`,
    documented *initial* defaults calibrated to the embedding provider
    actually in use — see that module's docstring."""

    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class RetrievalOutcome(str, Enum):
    """Whether `RetrievalResponse.results` actually contains usable
    evidence. `NO_RELEVANT_EVIDENCE` is a real, first-class outcome — see
    `RetrievalService`'s own docstring for why weak matches are never
    dressed up as relevant just because `top_k` was requested."""

    RESULTS = "RESULTS"
    NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"


@dataclass
class RetrievalResult:
    """One ranked piece of evidence. Every field the milestone's own
    example response lists is here, under names that make clear none of
    it is a truth judgment — see the module docstring."""

    rank: int
    chunk_id: uuid.UUID
    similarity: float
    relevance: RelevanceLevel
    content: str
    content_type: ContentType

    # Provenance — see app/services/knowledge_provenance_service.py for
    # the equivalent chain used elsewhere in this codebase.
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    source_id: uuid.UUID
    document_title: str
    source_name: str
    source_publisher: str
    version_label: str

    # Location within the source — page/sheet/row/slide/section, exactly
    # as chunking recorded it (app/ingestion/chunking.py).
    location: str | None
    page_number: int | None
    sheet_name: str | None
    row_number: int | None
    slide_number: int | None
    section_title: str | None
    section_path: list[str] | None

    # Quality/authority/governance — kept as three distinctly-named
    # fields, never combined into one score (see
    # app/ingestion/quality.py's module docstring, still true here).
    extraction_quality: QualityStatus
    extraction_method: ExtractionMethod | None
    source_authority_level: str | None
    verification_status: VerificationStatus

    # Tenant scope this result was returned under.
    scope: str  # "GLOBAL" | "ORGANIZATION"
    organization_id: uuid.UUID | None

    jurisdiction: str | None = None
    industry_sector: str | None = None
    publication_date: str | None = None
    effective_date: str | None = None


@dataclass
class RetrievalResponse:
    query: str
    outcome: RetrievalOutcome
    embedding_provider: str
    embedding_model: str
    embedding_model_version: str
    results: list[RetrievalResult] = field(default_factory=list)
    result_count: int = 0
    filters_applied: dict = field(default_factory=dict)
    search_metadata: dict = field(default_factory=dict)
