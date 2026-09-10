"""HTTP request/response shapes for `POST /api/v1/intelligence/decisions`,
`GET /api/v1/intelligence/decisions`, and
`GET /api/v1/intelligence/decisions/{decision_id}` — SIE Milestone 34:
Human Decision & Intervention Trace. Mirrors
`app/models/intelligence_decision.py`'s own field set, the same
internal-domain-object/API-schema split every other domain in this
codebase already establishes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.intelligence_decision_enums import IntelligenceDecisionType


class IntelligenceDecisionCreate(BaseModel):
    """**Deliberately does not accept `organization_id`,
    `decided_by_user_id`/`decided_by_api_client_id`, or any
    `attention_*`/`intelligence_*`/`calculation_version`/`evidence_*`
    field.** `organization_id` is the same authorize-then-trust query
    parameter every other write route in this codebase already uses
    (never a body field a client could mismatch against its own
    authorization); the decision-maker is derived from
    `RequestContext` (§3's own "must not accept an arbitrary
    decided_by_user_id from an untrusted client"); "what SIE said" is
    re-derived server-side by
    `app.services.intelligence_decision_service.resolve_attention_item()`
    from `scope`/`site_id`/`as_of`/`window_days`/`attention_reference`
    below -- see that function's own docstring."""

    scope: str = Field(..., description='"organization" | "site" -- must match the GET /intelligence/attention call this decision concerns.')
    site_id: uuid.UUID | None = Field(
        default=None, description="Required when scope='site' (and must belong to organization_id); omitted for scope='organization'."
    )
    as_of: datetime = Field(
        ..., description="The exact as_of from the GET /intelligence/attention response this decision concerns -- never 'now'."
    )
    window_days: int = Field(..., description="The exact window_days from that same GET response.")
    attention_reference: str = Field(
        ..., min_length=1, max_length=500, description="An item's own `reference` field from that GET response."
    )
    decision: IntelligenceDecisionType
    rationale: str = Field(..., min_length=1, max_length=4000)
    linked_action_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "An existing SafetyAction id, explicitly chosen by the human -- never created automatically "
            "merely because decision='ACT'. Must belong to organization_id."
        ),
    )


class IntelligenceDecisionActionRead(BaseModel):
    """A small, stable summary of the linked `SafetyAction` -- never the
    full `SafetyActionRead` shape (that stays `GET /actions/{id}`'s own
    job); just enough to answer "which intervention resulted" without a
    second request."""

    id: uuid.UUID
    title: str
    status: str


class IntelligenceDecisionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    site_label: str | None
    scope: str
    attention_reference: str
    attention_category: str
    attention_priority: str
    attention_title: str
    attention_explanation: str
    intelligence_as_of: datetime
    intelligence_window_days: int
    calculation_version: str | None
    evidence_source: str | None
    evidence_entity_ids: list[str]
    evidence_event_ids: list[str]
    decision: IntelligenceDecisionType
    rationale: str
    linked_action_id: uuid.UUID | None
    linked_action: IntelligenceDecisionActionRead | None
    decided_by_user_id: uuid.UUID | None
    decided_by_api_client_id: uuid.UUID | None
    decided_at: datetime
    created_at: datetime
    updated_at: datetime


class IntelligenceDecisionListRead(BaseModel):
    items: list[IntelligenceDecisionRead]
    total: int
    page: int
    page_size: int


__all__ = [
    "IntelligenceDecisionCreate",
    "IntelligenceDecisionActionRead",
    "IntelligenceDecisionRead",
    "IntelligenceDecisionListRead",
]
