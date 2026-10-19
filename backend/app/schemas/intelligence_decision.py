"""HTTP request/response shapes for `POST /api/v1/intelligence/decisions`,
`GET /api/v1/intelligence/decisions`, and
`GET /api/v1/intelligence/decisions/{decision_id}` — SIE Milestone 34:
Human Decision & Intervention Trace.

**Updated by Roadmap Phase 1 (Decisions wiring).** `IntelligenceDecisionRead`
used to mirror `app/models/intelligence_decision.py`'s own full field
set one-to-one (this route's pre-extraction shape, when the backing
table was local). Recording a decision is now routed through the
private Commercial Core service, whose own `sie_contract.
DecisionReferenceDTO` is the actual wire shape this route receives --
deliberately narrower (see that DTO's own docstring and
`docs/M43_IP_03_PUBLIC_EXTRACTION.md`): no `calculation_version`,
`evidence_*`, `linked_action`/`site_label` join, or
`decided_by_user_id`/`decided_by_api_client_id` split (collapsed into
`actor_type`/`actor_id`). `IntelligenceDecisionRead` below mirrors that
DTO field-for-field instead -- it is honest about what this deployment
can actually return, not what the pre-extraction monolith once could.
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


class IntelligenceDecisionRead(BaseModel):
    """Field-for-field `sie_contract.DecisionReferenceDTO` -- see module
    docstring for why this is narrower than the pre-extraction shape.
    A caller that needs the linked `SafetyAction`'s own title/status
    already holds `linked_action_id` itself (it supplied it when
    creating the decision) and can resolve it via the existing
    `GET /actions/{id}` route -- no Commercial Core round trip."""

    id: uuid.UUID
    organization_id: uuid.UUID
    attention_reference: str
    scope: str
    site_id: uuid.UUID | None
    attention_category: str
    attention_priority: str
    attention_title: str
    decision: IntelligenceDecisionType = Field(validation_alias="decision_type")
    rationale: str
    decided_at: datetime
    actor_type: str
    actor_id: uuid.UUID

    model_config = {"populate_by_name": True}


class IntelligenceDecisionListRead(BaseModel):
    items: list[IntelligenceDecisionRead]
    total: int
    page: int
    page_size: int


__all__ = [
    "IntelligenceDecisionCreate",
    "IntelligenceDecisionRead",
    "IntelligenceDecisionListRead",
]
