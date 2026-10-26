"""RAG boundary -- citation identity only, never retrieval/ranking policy.

See `../../docs/BOUNDARY_DECISIONS.md` Section 5 for the full RAG
classification. Summary: the *generic* retrieval interface and result
shape (Thundhai/SIE's existing `app/retrieval/*`, `app/embeddings/*`)
are already Public SIE infrastructure and need no new contract type --
they are not Commercial-Core-specific. What Commercial Core's private
RAG orchestration (`app/rag/*`: evidence selection, sufficiency policy,
conflict handling, citation validation) *produces* -- an answer with
citations -- is the one RAG-domain output worth a contract type, and
even that is redacted here: Thundhai/SIE's existing `CitationRead`
carries `similarity` (a retrieval-ranking signal) and
`source_authority_level`/`extraction_quality` (internal quality-scoring
detail) -- none of those are in `CitationReferenceDTO` below. A citation
is exposed as *what was cited*, never *how confidently or why it was
selected over alternatives*.

**Outcomes (since 0.8.0).** Not every query ends in an answer. Commercial
Core abstains when the evidence is insufficient, reports a source
conflict instead of picking a side, rejects a generated answer that cites
none of the supplied evidence, and refuses when the model provider fails
or a privacy rule blocks it. `RAGAnswerDTO.outcome` says which of these
happened, and `explanation` gives a plain-language reason for every
outcome other than `ANSWERED`. `explanation` is contract-owned wording:
it never carries provider names, configuration settings, relevance
thresholds or candidate counts.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sie_contract.common import AsOfWindow


class CitationReferenceDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    citation_id: str = Field(..., description="Stable identifier used inline in the answer text, e.g. 'E1'.")
    document_id: uuid.UUID
    source: str = Field(..., description="Source name, e.g. '29 CFR 1910'.")
    document: str = Field(..., description="Document title.")
    version: str = Field(..., description="Document version label.")
    location: str | None = Field(default=None, description="A locator within the document, e.g. a section number, when available.")


class RAGOutcome(str, Enum):
    """What happened to one RAG query. Closed set: adding a member is a
    breaking change (README "Versioning strategy")."""

    ANSWERED = "ANSWERED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    UNSUPPORTED_CLAIM_REJECTED = "UNSUPPORTED_CLAIM_REJECTED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PRIVACY_BLOCKED = "PRIVACY_BLOCKED"


class RAGAnswerDTO(BaseModel):
    """The result of one RAG query. `outcome` says whether an answer was
    produced. When it was (`ANSWERED`), `answer` is the generated text and
    `citations` is what supports it. For `SOURCE_CONFLICT`, `answer`
    describes the conflicting sources (never a resolution of them) and
    `citations` names them. For every other outcome `answer` is None and
    `explanation` says why. Nothing here describes how evidence was
    selected, how sufficiency was judged, or how a conflict between
    sources was resolved -- see BOUNDARY_DECISIONS.md."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID | None = Field(default=None, description="None for a GLOBAL-scope query.")
    query: str
    outcome: RAGOutcome
    answer: str | None = Field(default=None, description="Generated text for ANSWERED; the conflict description for SOURCE_CONFLICT; otherwise None.")
    explanation: str | None = Field(default=None, description="Plain-language reason, required for every outcome except ANSWERED. Contract-owned wording only.")
    citations: list[CitationReferenceDTO] = Field(default_factory=list)
    as_of: AsOfWindow

    @model_validator(mode="after")
    def _answer_and_explanation_match_outcome(self) -> "RAGAnswerDTO":
        if self.outcome is RAGOutcome.ANSWERED:
            if not self.answer:
                raise ValueError("An ANSWERED RAGAnswerDTO must carry non-empty answer text.")
            return self
        if not self.explanation:
            raise ValueError(f"A {self.outcome.value} RAGAnswerDTO must carry an explanation.")
        if self.outcome is not RAGOutcome.SOURCE_CONFLICT and self.answer is not None:
            raise ValueError(f"A {self.outcome.value} RAGAnswerDTO must not carry answer text.")
        return self
