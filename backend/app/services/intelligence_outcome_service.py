"""IntelligenceOutcome service — SIE Milestone 37: Field Outcome
Foundation. The one write path for
`app/api/v1/intelligence_outcomes.py`, mirroring
`app/services/intelligence_decision_service.py`'s own shape exactly: one
small transaction-boundary context manager, plus the handful of
reference-resolution/validation functions the route calls inside it.

    POST /intelligence/outcomes
        -> resolve_decision_reference()   -- decision_id belongs to this organization
        -> resolve_action_reference()     -- (only if linked_action_id supplied) reused,
                                              unchanged, from risk_assessment_service
        -> validate_site_reference()      -- (only if site_id supplied) reused, unchanged,
                                              from safety_action_service
        -> validate_source_event_reference() -- once per evidence_event_ids entry, reused,
                                                 unchanged, from safety_action_service
        -> reject_future_outcome_at()     -- an outcome describes something that already
                                              happened
        -> outcome_mutation_transaction():
               IntelligenceOutcome row + AuditLog entry, one commit

No function in this module ever infers a classification or creates a row
automatically — every `IntelligenceOutcome` is the direct, explicit
result of one `POST /intelligence/outcomes` call. See
`app/models/intelligence_outcome.py`'s own docstring for the full
architectural rationale.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.intelligence_outcome import IntelligenceOutcome
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification
from app.services.intelligence_decision_service import resolve_decision_reference

__all__ = [
    "outcome_mutation_transaction",
    "reject_future_outcome_at",
    "resolve_decision_reference",
    "record_outcome",
]


@contextmanager
def outcome_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one `IntelligenceOutcome`
    write -- identical shape to
    `intelligence_decision_service.decision_mutation_transaction()`.
    Commits once on success; rolls back once and re-raises, unchanged,
    on any exception."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def reject_future_outcome_at(outcome_at: datetime) -> None:
    """An outcome describes something that has already happened (§7 —
    `outcome_at` is the real-world instant the outcome became
    observable). A future `outcome_at` is a 422, not a silently accepted
    prediction -- this milestone is a ground-truth capture layer, never
    a forecast."""
    now = datetime.now(timezone.utc)
    reference = outcome_at if outcome_at.tzinfo is not None else outcome_at.replace(tzinfo=timezone.utc)
    if reference > now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="outcome_at must not be in the future.",
        )


def record_outcome(
    db: Session,
    *,
    organization_id: uuid.UUID,
    decision_id: uuid.UUID,
    site_id: uuid.UUID | None,
    linked_action_id: uuid.UUID | None,
    classification: IntelligenceOutcomeClassification,
    summary: str,
    evidence_event_ids: list[uuid.UUID] | None,
    outcome_at: datetime,
    recorded_by_user_id: uuid.UUID | None,
    recorded_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> IntelligenceOutcome:
    """Builds and `db.add()`s (never commits -- the caller's own
    `outcome_mutation_transaction()` block does that) one
    `IntelligenceOutcome` row. Every reference field passed in here has
    already been validated by the route (see module docstring) -- this
    function performs no further lookups, mirroring
    `intelligence_decision_service.record_decision()`'s own "callers
    resolve, this function only persists" split."""
    record = IntelligenceOutcome(
        organization_id=organization_id,
        decision_id=decision_id,
        site_id=site_id,
        linked_action_id=linked_action_id,
        classification=classification,
        summary=summary,
        evidence_event_ids=[str(i) for i in evidence_event_ids] if evidence_event_ids else None,
        outcome_at=outcome_at,
        recorded_by_user_id=recorded_by_user_id,
        recorded_by_api_client_id=recorded_by_api_client_id,
        request_id=request_id,
    )
    db.add(record)
    db.flush()  # populates record.id/created_at/updated_at for the response, without committing
    return record
