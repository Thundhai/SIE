"""HTTP request/response shapes for
`POST /api/v1/intelligence/outcomes/{outcome_id}/verifications`,
`GET /api/v1/intelligence/outcomes/{outcome_id}/verifications`,
`GET /api/v1/intelligence/outcomes/{outcome_id}/verification-state`, and
`GET /api/v1/intelligence/outcomes/{outcome_id}/evidence-evaluation` —
SIE Milestone 38: Outcome Verification & Evidence. Mirrors
`app/schemas/intelligence_outcome.py`'s own internal-domain-object/
API-schema split, and `app/models/intelligence_outcome_verification.py`'s
own field set.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.intelligence_outcome_verification_enums import (
    EvidenceStatus,
    IntelligenceOutcomeVerificationStatus,
)


class IntelligenceOutcomeVerificationCreate(BaseModel):
    """**Deliberately does not accept `organization_id`, `outcome_id`
    (path parameter instead), `verified_by_user_id`/
    `verified_by_api_client_id`, or `request_id`.** The verifier is
    derived from `RequestContext` (identical to
    `IntelligenceOutcomeCreate`'s own exclusion of `recorded_by_*`) --
    never accepted as client input."""

    status: IntelligenceOutcomeVerificationStatus
    rationale: str = Field(..., min_length=1, max_length=4000, description="Why this verification judgment was made.")
    verified_at: datetime = Field(
        ...,
        description=(
            "The real-world instant a human actually reviewed the outcome/evidence -- never 'now'. "
            "Must not be in the future."
        ),
    )


class EvidenceEvaluationRead(BaseModel):
    """The deterministic, structural evaluation of the outcome's own
    `evidence_event_ids` -- mirrors
    `app/services/intelligence_outcome_verification_service.py::
    EvidenceEvaluation` field-for-field. Never an opaque score."""

    evidence_count: int
    valid_evidence_count: int
    invalid_evidence_count: int
    future_evidence_count: int
    evidence_status: EvidenceStatus
    evidence_eligible_for_verification: bool
    reasons: list[str]


class IntelligenceOutcomeVerificationRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    outcome_id: uuid.UUID
    status: IntelligenceOutcomeVerificationStatus
    rationale: str
    verified_at: datetime
    verified_by_user_id: uuid.UUID | None
    verified_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class IntelligenceOutcomeVerificationListRead(BaseModel):
    items: list[IntelligenceOutcomeVerificationRead]
    total: int
    page: int
    page_size: int


class LearningEligibilityRead(BaseModel):
    """The deterministic learning-eligibility gate (M38 spec §10) -- a
    **gate only**, never itself an act of learning. Mirrors
    `app/services/intelligence_outcome_verification_service.py::
    LearningEligibility` field-for-field."""

    eligible: bool
    reasons: list[str]


class IntelligenceOutcomeVerificationStateRead(BaseModel):
    """The resolved, current governance state for one outcome — the
    single response `GET .../verification-state` returns, combining the
    resolved current verification (or `None` if none has ever been
    recorded — a distinct, and far more common, state than a row that
    exists and disputes it), the live evidence evaluation, and the
    learning-eligibility gate. This is a *read-time composition*, never
    a persisted row of its own -- everything in it is recomputed live
    on every call."""

    outcome_id: uuid.UUID
    current_verification: IntelligenceOutcomeVerificationRead | None
    evidence_evaluation: EvidenceEvaluationRead
    learning_eligibility: LearningEligibilityRead


__all__ = [
    "IntelligenceOutcomeVerificationCreate",
    "EvidenceEvaluationRead",
    "IntelligenceOutcomeVerificationRead",
    "IntelligenceOutcomeVerificationListRead",
    "LearningEligibilityRead",
    "IntelligenceOutcomeVerificationStateRead",
]
