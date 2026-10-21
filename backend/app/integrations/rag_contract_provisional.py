"""PROVISIONAL -- a local mirror of `sie-contract` 0.8.0's `RAGOutcome` and
`RAGAnswerDTO`, for local development only.

**Why this file exists.** Public SIE vendors `sie-contract` 0.5.0
(`vendor/sie_contract/`), whose `RAGAnswerDTO` has no `outcome` and
requires answer text -- it cannot represent an abstention honestly. The
0.8.0 shape is proposed in Thundhai/SIE-Commercial-Core PR #19 and is not
merged, so it cannot be vendored yet: the vendoring rule is "only from a
merged Commercial Core commit, with `PROVENANCE.json`". This module copies
the proposed 0.8.0 definitions so the RAG client, route and UI can be
built and tested against them in the meantime.

**Never hand-edit `vendor/sie_contract/` instead of this.** Once #18 and
#19 merge and 0.8.0 is vendored with provenance, delete this module and
import `RAGOutcome`/`RAGAnswerDTO` from `sie_contract` directly. The field
names, enum values and validator below match the proposed
`sie_contract/rag.py` at Commercial Core `20918fd` exactly, so that swap
changes no call site. `CitationReferenceDTO` and `AsOfWindow` are
unchanged between 0.5.0 and 0.8.0 and are imported from the vendored
package, not copied.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sie_contract import AsOfWindow, CitationReferenceDTO

PROVISIONAL_CONTRACT_VERSION = "0.8.0"


class RAGOutcome(str, Enum):
    """What happened to one RAG query (proposed `sie-contract` 0.8.0)."""

    ANSWERED = "ANSWERED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    UNSUPPORTED_CLAIM_REJECTED = "UNSUPPORTED_CLAIM_REJECTED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PRIVACY_BLOCKED = "PRIVACY_BLOCKED"


class RAGAnswerDTO(BaseModel):
    """The result of one RAG query (proposed `sie-contract` 0.8.0).
    `ANSWERED` carries answer text; `SOURCE_CONFLICT` may carry a
    description of the conflicting sources (never a resolution); every
    other outcome carries no answer text and an explanation instead."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID | None = Field(default=None, description="None for a GLOBAL-scope query.")
    query: str
    outcome: RAGOutcome
    answer: str | None = None
    explanation: str | None = None
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


__all__ = ["PROVISIONAL_CONTRACT_VERSION", "RAGAnswerDTO", "RAGOutcome"]
