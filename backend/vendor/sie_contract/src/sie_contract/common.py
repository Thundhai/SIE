"""Common types shared across every schema module in this package."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class EvidenceType(str, Enum):
    """Open-ish but currently-closed set of *kinds* of thing an
    EvidenceReference can point at. Deliberately an enum (not `str`)
    because this vocabulary is small, stable, and getting it wrong
    (e.g. confusing SAFETY_EVENT with RISK_ASSESSMENT_FINDING) is a
    real integration bug worth catching at validation time -- unlike
    AttentionItemDTO.category or DecisionReferenceDTO.decision_type,
    which are genuinely open and evolve on the Commercial Core side
    alone.
    """

    SAFETY_EVENT = "safety_event"
    RISK_ASSESSMENT_FINDING = "risk_assessment_finding"
    RISK_ASSESSMENT_CONTROL = "risk_assessment_control"
    SAFETY_ACTION = "safety_action"
    KNOWLEDGE_DOCUMENT = "knowledge_document"
    ORGANIZATIONAL_MEMORY = "organizational_memory"


class EvidenceReference(BaseModel):
    """A pointer to something that justifies an intelligence output --
    never the thing itself, never the internal query/scoring that found
    it. A consumer resolves this reference through Public SIE's own
    existing read APIs for that entity type (e.g. GET /events/{id}),
    not through this package.
    """

    model_config = ConfigDict(frozen=True)

    evidence_type: EvidenceType
    reference_id: uuid.UUID
    label: str | None = Field(default=None, description="A short, human-readable label for display, e.g. an event's title. Never the full entity payload.")


class AsOfWindow(BaseModel):
    """Temporal scope common to every observable intelligence output.

    `as_of` is the point in time the output is valid *as of* (point-in-time
    correctness -- see Thundhai/SIE's own extensive as_of handling
    throughout FieldIntelligenceContext/Attention); `generated_at` is when
    the computation actually ran, which may be later than `as_of` for a
    historical/backfilled query. The two are never assumed equal.
    """

    model_config = ConfigDict(frozen=True)

    as_of: datetime = Field(..., description="UTC. The point-in-time this output is valid as of.")
    generated_at: datetime = Field(..., description="UTC. When this output was actually computed -- may differ from as_of for a historical query.")
    window_days: int | None = Field(default=None, description="The lookback window, in days, this output considered -- when the output has a temporal window at all.")


class Page(BaseModel, Generic[T]):
    """A generic paginated envelope, matching the shape Public SIE's own
    list endpoints already use (`items`/`total`/`page`/`page_size`) --
    not a new pagination convention.
    """

    model_config = ConfigDict(frozen=True)

    items: list[T]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
