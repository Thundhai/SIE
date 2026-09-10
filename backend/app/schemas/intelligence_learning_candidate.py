"""HTTP request/response shapes for
`POST /api/v1/intelligence/learning-candidates`,
`GET /api/v1/intelligence/learning-candidates`,
`GET /api/v1/intelligence/learning-candidates/{candidate_id}`,
`POST /api/v1/intelligence/learning-candidates/{candidate_id}/governance-decisions`,
`GET /api/v1/intelligence/learning-candidates/{candidate_id}/governance-decisions`,
and `GET /api/v1/intelligence/learning-candidates/{candidate_id}/state` —
SIE Milestone 39: Learning Candidate Foundation. Mirrors
`app/schemas/intelligence_outcome_verification.py`'s own internal-
domain-object/API-schema split, and
`app/models/intelligence_learning_candidate.py`'s own field set.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.intelligence_learning_candidate_enums import IntelligenceLearningCandidateGovernanceStatus
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification
from app.models.intelligence_outcome_verification_enums import IntelligenceOutcomeVerificationStatus
from app.schemas.intelligence_outcome_verification import EvidenceEvaluationRead


class IntelligenceLearningCandidateCreate(BaseModel):
    """**Deliberately does not accept `organization_id`,
    `verification_id`, `created_by_user_id`/`created_by_api_client_id`,
    or `request_id`.** `verification_id` in particular is never
    client-chosen: the server resolves the outcome's own *current*
    verification itself
    (`app/services/intelligence_learning_candidate_service.py::
    create_learning_candidate()`) — a client cannot pin a candidate to
    an outdated or superseded verification row."""

    outcome_id: uuid.UUID = Field(
        ...,
        description=(
            "The IntelligenceOutcome this candidate is derived from. Must belong to organization_id, and its "
            "resolved current verification must be VERIFIED with independently valid evidence."
        ),
    )


class IntelligenceLearningCandidateOutcomeRead(BaseModel):
    """A small, stable summary of the originating `IntelligenceOutcome`
    — never the full `IntelligenceOutcomeRead` shape (that stays
    `GET /intelligence/outcomes/{id}`'s own job); mirrors
    `IntelligenceOutcomeDecisionRead`'s own "just enough, no second
    request" shape."""

    id: uuid.UUID
    decision_id: uuid.UUID
    classification: IntelligenceOutcomeClassification
    outcome_at: datetime
    site_id: uuid.UUID | None
    linked_action_id: uuid.UUID | None


class IntelligenceLearningCandidateVerificationRead(BaseModel):
    """A small, stable summary of the pinned
    `IntelligenceOutcomeVerification` — the exact row that made this
    candidate eligible at creation time."""

    id: uuid.UUID
    status: IntelligenceOutcomeVerificationStatus
    verified_at: datetime


class IntelligenceLearningCandidateRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    outcome_id: uuid.UUID
    verification_id: uuid.UUID
    outcome: IntelligenceLearningCandidateOutcomeRead | None
    verification: IntelligenceLearningCandidateVerificationRead | None
    created_by_user_id: uuid.UUID | None
    created_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class IntelligenceLearningCandidateListRead(BaseModel):
    items: list[IntelligenceLearningCandidateRead]
    total: int
    page: int
    page_size: int


class IntelligenceLearningCandidateGovernanceDecisionCreate(BaseModel):
    """**Deliberately does not accept `organization_id`, `candidate_id`
    (path parameter instead), `decided_by_user_id`/
    `decided_by_api_client_id`, `decided_at`, or `request_id`.** The
    actor and decision instant are both derived from `RequestContext`/
    the server clock — never accepted as client input (M39 spec §9)."""

    status: IntelligenceLearningCandidateGovernanceStatus
    rationale: str = Field(..., min_length=1, max_length=4000, description="Why this governance decision was made.")


class IntelligenceLearningCandidateGovernanceDecisionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    candidate_id: uuid.UUID
    status: IntelligenceLearningCandidateGovernanceStatus
    rationale: str
    decided_at: datetime
    decided_by_user_id: uuid.UUID | None
    decided_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class IntelligenceLearningCandidateGovernanceDecisionListRead(BaseModel):
    items: list[IntelligenceLearningCandidateGovernanceDecisionRead]
    total: int
    page: int
    page_size: int


class IntelligenceLearningCandidateStateRead(BaseModel):
    """The resolved, current governance state for one candidate —
    combines the candidate itself, the resolved current governance
    decision (or `None` if no governance decision has ever been
    recorded — "pending", a distinct and the initial state), and a
    *live* re-evaluation of the originating outcome's evidence (M39
    spec §20's own "verified at time T" vs. "currently revalidated"
    distinction — reuses `EvidenceEvaluationRead` verbatim from M38,
    never a new evidence schema). This is a *read-time composition*,
    never a persisted row of its own — mirrors `IntelligenceOutcome
    VerificationStateRead`'s own identical shape exactly."""

    candidate: IntelligenceLearningCandidateRead
    current_governance: IntelligenceLearningCandidateGovernanceDecisionRead | None
    current_evidence_evaluation: EvidenceEvaluationRead


__all__ = [
    "IntelligenceLearningCandidateCreate",
    "IntelligenceLearningCandidateOutcomeRead",
    "IntelligenceLearningCandidateVerificationRead",
    "IntelligenceLearningCandidateRead",
    "IntelligenceLearningCandidateListRead",
    "IntelligenceLearningCandidateGovernanceDecisionCreate",
    "IntelligenceLearningCandidateGovernanceDecisionRead",
    "IntelligenceLearningCandidateGovernanceDecisionListRead",
    "IntelligenceLearningCandidateStateRead",
]
