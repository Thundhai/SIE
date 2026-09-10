"""RAG result shapes — domain dataclasses returned by `RAGService.query()`.
Distinct from `app/schemas/rag.py` (the Pydantic API request/response
shapes), the same internal-domain-object/API-schema split
`app/retrieval/results.py`/`app/schemas/retrieval.py` already establish.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

from app.models.enums import ContentType, QualityStatus, VerificationStatus
from app.retrieval.results import RetrievalResult


class EvidenceState(str, Enum):
    """Deterministic evidence-sufficiency state — see
    `app/rag/sufficiency.py` for the exact rules that produce this. Never
    called "AI confidence" anywhere in this codebase (milestone item 6):
    it is computed from relevance buckets and counts alone, before any
    LLM is involved."""

    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class RAGOutcome(str, Enum):
    """What actually happened for this request — distinct from
    `EvidenceState`, which is a property of the *evidence alone*.
    `EvidenceState` and `RAGOutcome` can disagree in meaningful ways: e.g.
    `evidence_state=PARTIAL` with `outcome=SOURCE_CONFLICT` (there was
    enough evidence to find a conflict, so generation was never
    attempted), or `evidence_state=SUFFICIENT` with
    `outcome=PROVIDER_FAILURE` (the evidence was fine; the LLM call
    itself failed)."""

    ANSWERED = "ANSWERED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    UNSUPPORTED_CLAIM_REJECTED = "UNSUPPORTED_CLAIM_REJECTED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PRIVACY_BLOCKED = "PRIVACY_BLOCKED"


@dataclass
class SelectedEvidenceItem:
    """One piece of evidence that survived `EvidenceSelectionService` and
    was assigned a stable citation identifier. Wraps the existing
    `RetrievalResult` rather than copying its fields, so every provenance
    field `RetrievalService` already computed (rank, similarity,
    verification_status, extraction_quality, location, scope,
    organization_id, ...) automatically stays available end to end,
    exactly as retrieved — see `app/retrieval/results.py`."""

    citation_id: str  # "E1", "E2", ... — stable within one RAGResponse
    result: RetrievalResult


@dataclass
class Citation:
    """One citation actually present (and validated) in the generated
    answer — see `app/rag/citations.py`. Every field here is traceable
    back to the original `KnowledgeChunk` via `chunk_id` — the
    Response -> Citation -> Chunk -> Version -> Document -> Source chain
    the README's "Provenance" section demonstrates. Never exposes an
    internal database id where a stable citation identifier suffices in
    user-facing text; `chunk_id`/`document_id`/etc. remain available on
    this structured object for API consumers that need them (e.g. to link
    back to the source record), but the generated answer text itself only
    ever contains `[E1]`-style identifiers."""

    citation_id: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    document_title: str
    version_label: str
    location: str | None
    content_type: ContentType
    verification_status: VerificationStatus
    extraction_quality: QualityStatus
    source_authority_level: str | None
    similarity: float
    scope: str
    organization_id: uuid.UUID | None


@dataclass
class SourceConflict:
    """A detected disagreement between two evidence items — see
    `app/rag/conflict.py`. Deliberately never resolved automatically
    (milestone item 15/36): both sources are named, both statements are
    quoted verbatim, and the response states plainly that SIE cannot
    resolve the conflict without additional authority/context."""

    citation_id_a: str
    citation_id_b: str
    statement_a: str
    statement_b: str
    source_name_a: str
    source_name_b: str
    version_label_a: str
    version_label_b: str
    effective_date_a: str | None
    effective_date_b: str | None


@dataclass
class RAGResponse:
    """The full result of one `RAGService.query()` call. Never contains a
    raw embedding vector, a system prompt, an API key, or any other
    secret — see `app/schemas/rag.py::RAGQueryResponse` (the HTTP-facing
    projection of this) for the response-shape guarantee the API actually
    enforces."""

    query: str
    outcome: RAGOutcome
    evidence_state: EvidenceState
    answer: str | None
    citations: list[Citation] = field(default_factory=list)
    conflicts: list[SourceConflict] = field(default_factory=list)
    evidence_count: int = 0
    warnings: list[str] = field(default_factory=list)
    abstention_reason: str | None = None

    # Retrieval/model metadata — milestone items 24-26 (observability,
    # prompt versioning, reproducibility). Deliberately dict-shaped, not
    # a fixed dataclass: this is meant to be a stable *envelope*
    # (retrieval config, evidence-selection config, model identity) that
    # can grow without a schema break, exactly like
    # `RetrievalResponse.search_metadata`/`filters_applied`.
    retrieval_metadata: dict = field(default_factory=dict)
    model_metadata: dict | None = None
    prompt_version: str = ""
    reproducibility: dict = field(default_factory=dict)
