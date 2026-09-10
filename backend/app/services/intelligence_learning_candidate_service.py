"""IntelligenceLearningCandidate service — SIE Milestone 39: Learning
Candidate Foundation. The one write path for
`app/api/v1/intelligence_learning_candidates.py`, mirroring
`app/services/intelligence_outcome_verification_service.py`'s own shape
exactly, plus the governance-decision functions this milestone
introduces.

    POST /intelligence/learning-candidates
        -> resolve_outcome_reference()      -- reused verbatim from
                                                intelligence_outcome_verification_service,
                                                never forked (M39 spec §6)
        -> evaluate_learning_eligibility()  -- reused verbatim -- the one write-time
                                                gate: 422 unless the outcome's resolved
                                                current verification is VERIFIED and its
                                                evidence independently evaluates valid
        -> candidate_mutation_transaction():
               IntelligenceLearningCandidate row (or the existing one, idempotent by
               construction -- see that model's own docstring) + AuditLog entry, one commit

    POST /intelligence/learning-candidates/{id}/governance-decisions
        -> resolve_candidate_reference()
        -> governance_mutation_transaction():
               IntelligenceLearningCandidateGovernanceDecision row + AuditLog entry

No function in this module ever infers a governance decision or creates
a candidate automatically -- every `IntelligenceLearningCandidate` is
the direct, explicit result of one `POST /intelligence/
learning-candidates` call against an already-`VERIFIED` outcome, and
every governance decision is the direct, explicit result of one
`POST .../governance-decisions` call. See
`app/models/intelligence_learning_candidate.py`'s own docstring for the
full architectural rationale, and
`docs/LEARNING_CANDIDATE_V0_1.md` for the explicit statement that this
milestone stops at the learning-candidate boundary -- it does not learn.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.intelligence_learning_candidate import (
    IntelligenceLearningCandidate,
    IntelligenceLearningCandidateGovernanceDecision,
)
from app.models.intelligence_learning_candidate_enums import IntelligenceLearningCandidateGovernanceStatus
from app.services.intelligence_outcome_verification_service import (
    evaluate_learning_eligibility,
    resolve_current_verification,
    resolve_outcome_reference,
)

__all__ = [
    "candidate_mutation_transaction",
    "governance_mutation_transaction",
    "resolve_candidate_reference",
    "create_learning_candidate",
    "resolve_current_governance",
    "record_governance_decision",
]


@contextmanager
def candidate_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one `IntelligenceLearning
    Candidate` write -- identical shape to `intelligence_outcome_
    verification_service.verification_mutation_transaction()`. Commits
    once on success; rolls back once and re-raises, unchanged, on any
    exception."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


@contextmanager
def governance_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one governance-decision
    write -- identical shape, kept as its own named function (rather
    than reusing `candidate_mutation_transaction()` under a generic
    name) so each transaction boundary reads as exactly what it
    protects, mirroring `intelligence_decision_service.
    decision_mutation_transaction()`/`intelligence_outcome_service.
    outcome_mutation_transaction()`'s own one-context-manager-per-write-
    kind convention."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def resolve_candidate_reference(
    db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID
) -> IntelligenceLearningCandidate:
    """The identical "does this id belong to this organization" shape
    as `intelligence_outcome_verification_service.
    resolve_outcome_reference()`, applied to
    `IntelligenceLearningCandidate`. A nonexistent id or one from a
    different organization is a 404, never a silent cross-tenant read."""
    candidate = db.execute(
        select(IntelligenceLearningCandidate).where(
            IntelligenceLearningCandidate.id == candidate_id,
            IntelligenceLearningCandidate.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="candidate_id not found in this organization."
        )
    return candidate


def create_learning_candidate(
    db: Session,
    *,
    organization_id: uuid.UUID,
    outcome_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    created_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> tuple[IntelligenceLearningCandidate, bool]:
    """Create (or return the existing) `IntelligenceLearningCandidate`
    for `outcome_id`. Returns `(row, created)` -- `created=False` when a
    candidate already existed for this outcome (idempotent by
    construction, mirrors `project_site_service.link_project_site()`'s
    own identical "existing row returned, no duplicate, no error"
    precedent -- see `IntelligenceLearningCandidate`'s own docstring for
    the full "Idempotent by construction" rationale).

    `outcome_id` is resolved against `organization_id` first (404 before
    any row is touched, tenant isolation structural not merely checked
    after the fact -- identical discipline to `link_project_site()`).
    Eligibility is the one write-time gate -- reuses `evaluate_learning_
    eligibility()` verbatim, never forked (M39 spec §6): 422 with the
    specific reasons when the outcome's resolved current verification is
    not `VERIFIED`, or its evidence does not independently evaluate as
    valid."""
    outcome = resolve_outcome_reference(db, organization_id=organization_id, outcome_id=outcome_id)

    existing = db.execute(
        select(IntelligenceLearningCandidate).where(
            IntelligenceLearningCandidate.organization_id == organization_id,
            IntelligenceLearningCandidate.outcome_id == outcome_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    eligibility = evaluate_learning_eligibility(db, outcome=outcome)
    if not eligibility.eligible:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=("Outcome is not eligible to become a learning candidate. " + " ".join(eligibility.reasons)).strip(),
        )

    # eligibility.eligible guarantees a VERIFIED current verification
    # exists (see evaluate_learning_eligibility()'s own docstring item
    # 3) -- resolved again here (not re-derived by hand) so the pinned
    # verification_id always comes from the identical, unforked M38
    # resolution function.
    current_verification = resolve_current_verification(
        db, organization_id=organization_id, outcome_id=outcome_id
    )
    assert current_verification is not None, "evaluate_learning_eligibility() already guarantees this"

    candidate = IntelligenceLearningCandidate(
        organization_id=organization_id,
        outcome_id=outcome_id,
        verification_id=current_verification.id,
        created_by_user_id=created_by_user_id,
        created_by_api_client_id=created_by_api_client_id,
        request_id=request_id,
    )
    db.add(candidate)
    db.flush()  # populates candidate.id/created_at/updated_at, without committing
    return candidate, True


def resolve_current_governance(
    db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, as_of: datetime | None = None
) -> IntelligenceLearningCandidateGovernanceDecision | None:
    """The deterministic "resolved current state" for one candidate's
    governance history -- identical rule to `intelligence_outcome_
    verification_service.resolve_current_verification()`: the single
    most recent row, ordered `created_at DESC, id DESC`. `None` when no
    governance decision has ever been recorded ("pending" -- a distinct,
    and the initial, state; see `IntelligenceLearningCandidateGovernance
    Status`'s own docstring for why it has no enum member).

    `as_of`, when supplied, restricts to rows with `created_at <= as_of`
    -- a governance decision recorded after `as_of` must not appear in a
    historical reconstruction, mirroring M38's identical `as_of` rule."""
    conditions = [
        IntelligenceLearningCandidateGovernanceDecision.organization_id == organization_id,
        IntelligenceLearningCandidateGovernanceDecision.candidate_id == candidate_id,
    ]
    if as_of is not None:
        conditions.append(IntelligenceLearningCandidateGovernanceDecision.created_at <= as_of)
    return db.execute(
        select(IntelligenceLearningCandidateGovernanceDecision)
        .where(*conditions)
        .order_by(
            IntelligenceLearningCandidateGovernanceDecision.created_at.desc(),
            IntelligenceLearningCandidateGovernanceDecision.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()


def record_governance_decision(
    db: Session,
    *,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID,
    status: IntelligenceLearningCandidateGovernanceStatus,
    rationale: str,
    decided_by_user_id: uuid.UUID | None,
    decided_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> IntelligenceLearningCandidateGovernanceDecision:
    """Builds and `db.add()`s (never commits -- the caller's own
    `governance_mutation_transaction()` block does that) one
    `IntelligenceLearningCandidateGovernanceDecision` row. Performs no
    validation itself beyond what the caller (the API route) has already
    resolved (`candidate_id` via `resolve_candidate_reference()`) --
    mirrors `intelligence_outcome_verification_service.
    record_verification()`'s own "callers resolve, this function only
    persists" split. `decided_at` is server-derived
    (`default=utcnow` on the model column) -- see that column's own
    docstring for why, unlike `outcome_at`/`verified_at`, no backdating
    discipline is needed for a governance action."""
    record = IntelligenceLearningCandidateGovernanceDecision(
        organization_id=organization_id,
        candidate_id=candidate_id,
        status=status,
        rationale=rationale,
        decided_by_user_id=decided_by_user_id,
        decided_by_api_client_id=decided_by_api_client_id,
        request_id=request_id,
    )
    db.add(record)
    db.flush()  # populates record.id/decided_at/created_at/updated_at, without committing
    return record
