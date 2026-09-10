"""HTTP request/response shapes for `POST /api/v1/intelligence/outcomes`,
`GET /api/v1/intelligence/outcomes`, and
`GET /api/v1/intelligence/outcomes/{outcome_id}` — SIE Milestone 37:
Field Outcome Foundation. Mirrors
`app/schemas/intelligence_decision.py`'s own internal-domain-object/
API-schema split, and `app/models/intelligence_outcome.py`'s own field
set.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification


class IntelligenceOutcomeCreate(BaseModel):
    """**Deliberately does not accept `organization_id`,
    `recorded_by_user_id`/`recorded_by_api_client_id`, or `request_id`.**
    `organization_id` is the same authorize-then-trust query parameter
    every other write route in this codebase already uses; the recorder
    is derived from `RequestContext` (identical to
    `IntelligenceDecisionCreate`'s own exclusion of `decided_by_*`) --
    never accepted as client input."""

    decision_id: uuid.UUID = Field(
        ..., description="The IntelligenceDecision this outcome reports the result of. Must belong to organization_id."
    )
    site_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Optional, independently supplied -- need not match decision_id's own site_id. "
            "Must belong to organization_id when supplied."
        ),
    )
    linked_action_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "An existing SafetyAction id, explicitly chosen by the human -- a Decision -> Outcome with no "
            "SafetyAction in between is a legitimate, first-class case. Must belong to organization_id."
        ),
    )
    classification: IntelligenceOutcomeClassification
    summary: str = Field(..., min_length=1, max_length=4000, description="Why the human believes this outcome occurred.")
    evidence_event_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Optional reference list of existing SafetyEvent ids (e.g. a follow-up observation). Each must belong to organization_id.",
    )
    outcome_at: datetime = Field(
        ...,
        description=(
            "The real-world instant this outcome became observable/was established -- never 'now'. "
            "Must not be in the future."
        ),
    )


class IntelligenceOutcomeDecisionRead(BaseModel):
    """A small, stable summary of the referenced `IntelligenceDecision`
    -- never the full `IntelligenceDecisionRead` shape (that stays
    `GET /intelligence/decisions/{id}`'s own job); mirrors
    `IntelligenceDecisionActionRead`'s own "just enough, no second
    request" shape."""

    id: uuid.UUID
    attention_reference: str
    decision: str


class IntelligenceOutcomeActionRead(BaseModel):
    """Identical shape to `IntelligenceDecisionActionRead` -- a small,
    stable summary of the linked `SafetyAction`, never the full
    `SafetyActionRead`."""

    id: uuid.UUID
    title: str
    status: str


class IntelligenceOutcomeRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    decision_id: uuid.UUID
    decision: IntelligenceOutcomeDecisionRead | None
    site_id: uuid.UUID | None
    site_label: str | None
    linked_action_id: uuid.UUID | None
    linked_action: IntelligenceOutcomeActionRead | None
    classification: IntelligenceOutcomeClassification
    summary: str
    evidence_event_ids: list[str]
    outcome_at: datetime
    recorded_by_user_id: uuid.UUID | None
    recorded_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class IntelligenceOutcomeListRead(BaseModel):
    items: list[IntelligenceOutcomeRead]
    total: int
    page: int
    page_size: int


__all__ = [
    "IntelligenceOutcomeCreate",
    "IntelligenceOutcomeDecisionRead",
    "IntelligenceOutcomeActionRead",
    "IntelligenceOutcomeRead",
    "IntelligenceOutcomeListRead",
]
