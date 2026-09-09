"""HTTP request/response shapes for
`POST /api/v1/intelligence/organizational-memory`,
`GET /api/v1/intelligence/organizational-memory`,
`GET /api/v1/intelligence/organizational-memory/{memory_id}`,
`POST /api/v1/intelligence/organizational-memory/{memory_id}/governance-decisions`,
`GET /api/v1/intelligence/organizational-memory/{memory_id}/governance-decisions`,
and `GET /api/v1/intelligence/organizational-memory/{memory_id}/state` —
SIE Milestone 40: Organizational Memory Architecture. Mirrors
`app/schemas/intelligence_learning_candidate.py`'s own internal-
domain-object/API-schema split, and
`app/models/organizational_memory.py`'s own field set. Directly reuses
`IntelligenceLearningCandidateOutcomeRead`/
`IntelligenceLearningCandidateVerificationRead` for the nested
provenance chain rather than redefining an equivalent shape (M40 spec
§16's "do not fork" instruction, extended to schemas).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.organizational_memory_enums import OrganizationalMemoryGovernanceStatus, OrganizationalMemoryType
from app.schemas.intelligence_learning_candidate import (
    IntelligenceLearningCandidateOutcomeRead,
    IntelligenceLearningCandidateVerificationRead,
)


class OrganizationalMemoryCreate(BaseModel):
    """**Deliberately does not accept `organization_id`,
    `created_by_user_id`/`created_by_api_client_id`, or `request_id`.**
    Those are all server-derived from `RequestContext` (M40 spec §20)."""

    learning_candidate_id: uuid.UUID = Field(
        ...,
        description=(
            "The IntelligenceLearningCandidate this memory is derived from. Must belong to organization_id, and "
            "its resolved current governance decision must be ACCEPTED."
        ),
    )
    memory_type: OrganizationalMemoryType
    title: str = Field(..., min_length=1, max_length=200, description="A short, human-scannable label.")
    memory_content: str = Field(
        ..., min_length=1, max_length=8000, description="The explicit knowledge statement this memory preserves."
    )
    rationale: str = Field(
        ..., min_length=1, max_length=4000, description="Why this statement was judged worth remembering."
    )


class OrganizationalMemoryCandidateRead(BaseModel):
    """A small, stable summary of the originating `IntelligenceLearning
    Candidate` and, one hop further, its own outcome/verification --
    never the full `IntelligenceLearningCandidateRead` shape (that stays
    `GET /intelligence/learning-candidates/{id}`'s own job). This is the
    one-hop provenance chain M40 spec §10 requires: Memory -> Candidate
    -> Outcome + Verification. The decision/intervention/evidence chain
    beyond that remains reachable via the outcome's own `decision_id`
    against the existing M34/M37/M38 endpoints -- never duplicated
    here."""

    id: uuid.UUID
    outcome_id: uuid.UUID
    verification_id: uuid.UUID
    outcome: IntelligenceLearningCandidateOutcomeRead | None
    verification: IntelligenceLearningCandidateVerificationRead | None


class OrganizationalMemoryRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    learning_candidate_id: uuid.UUID
    memory_type: OrganizationalMemoryType
    title: str
    memory_content: str
    rationale: str
    learning_candidate: OrganizationalMemoryCandidateRead | None
    created_by_user_id: uuid.UUID | None
    created_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class OrganizationalMemoryListRead(BaseModel):
    items: list[OrganizationalMemoryRead]
    total: int
    page: int
    page_size: int


class OrganizationalMemoryGovernanceDecisionCreate(BaseModel):
    """**Deliberately does not accept `organization_id`, `memory_id`
    (path parameter instead), `decided_by_user_id`/
    `decided_by_api_client_id`, `decided_at`, or `request_id`.** The
    actor and decision instant are both derived from `RequestContext`/
    the server clock — never accepted as client input (M40 spec §20)."""

    status: OrganizationalMemoryGovernanceStatus
    rationale: str = Field(..., min_length=1, max_length=4000, description="Why this governance decision was made.")


class OrganizationalMemoryGovernanceDecisionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    memory_id: uuid.UUID
    status: OrganizationalMemoryGovernanceStatus
    rationale: str
    decided_at: datetime
    decided_by_user_id: uuid.UUID | None
    decided_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class OrganizationalMemoryGovernanceDecisionListRead(BaseModel):
    items: list[OrganizationalMemoryGovernanceDecisionRead]
    total: int
    page: int
    page_size: int


class OrganizationalMemoryStateRead(BaseModel):
    """The resolved, current governance state for one memory — combines
    the memory itself and the resolved current governance decision (or
    `None` if no governance decision has ever been recorded — the
    implicit `ACTIVE` state, see `OrganizationalMemoryGovernanceStatus`'s
    own docstring). This is a *read-time composition*, never a persisted
    row of its own — mirrors `IntelligenceLearningCandidateStateRead`'s
    own identical shape, minus a live evidence re-evaluation (M40 has no
    equivalent of M38's evidence-revalidation concept — a memory's
    authority rests on its already-accepted candidate, not on evidence
    that could itself go stale)."""

    memory: OrganizationalMemoryRead
    current_governance: OrganizationalMemoryGovernanceDecisionRead | None


__all__ = [
    "OrganizationalMemoryCreate",
    "OrganizationalMemoryCandidateRead",
    "OrganizationalMemoryRead",
    "OrganizationalMemoryListRead",
    "OrganizationalMemoryGovernanceDecisionCreate",
    "OrganizationalMemoryGovernanceDecisionRead",
    "OrganizationalMemoryGovernanceDecisionListRead",
    "OrganizationalMemoryStateRead",
]
