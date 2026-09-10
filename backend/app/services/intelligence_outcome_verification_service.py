"""IntelligenceOutcomeVerification service — SIE Milestone 38: Outcome
Verification & Evidence. The one write path for
`app/api/v1/intelligence_outcomes.py`'s verification endpoints, mirroring
`app/services/intelligence_outcome_service.py`'s own shape exactly, plus
the deterministic evidence-evaluation and eligibility functions this
milestone introduces.

    POST /intelligence/outcomes/{id}/verifications
        -> resolve_outcome_reference()    -- outcome_id belongs to this organization
        -> evaluate_outcome_evidence()    -- deterministic evidence check (route calls
                                              this *before* record_verification() to
                                              enforce "VERIFIED requires valid evidence" --
                                              see that function's own docstring)
        -> reject_future_verified_at()    -- a verification describes a review that
                                              already happened
        -> verification_mutation_transaction():
               IntelligenceOutcomeVerification row + AuditLog entry, one commit

No function in this module ever infers a verification status or creates
a row automatically -- every `IntelligenceOutcomeVerification` is the
direct, explicit result of one `POST .../verifications` call. See
`app/models/intelligence_outcome_verification.py`'s own docstring for
the full architectural rationale.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.intelligence_outcome import IntelligenceOutcome
from app.models.intelligence_outcome_verification import IntelligenceOutcomeVerification
from app.models.intelligence_outcome_verification_enums import (
    EvidenceStatus,
    IntelligenceOutcomeVerificationStatus,
)
from app.models.safety_event import SafetyEvent

__all__ = [
    "EvidenceEvaluation",
    "LearningEligibility",
    "verification_mutation_transaction",
    "resolve_outcome_reference",
    "reject_future_verified_at",
    "evaluate_outcome_evidence",
    "record_verification",
    "resolve_current_verification",
    "evaluate_learning_eligibility",
]


def _as_utc(value: datetime) -> datetime:
    """SQLite (used by this project's default test/dev database) does
    not round-trip `tzinfo` through a commit/expire cycle -- identical,
    already-established pattern reused verbatim from
    `tests/test_intelligence_decision_service.py::_as_utc()` and
    `app/intelligence/enterprise_intelligence_service.py::_as_utc()`,
    needed here too since this module compares timestamps read back
    from committed rows."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass
class EvidenceEvaluation:
    """The deterministic, structural evaluation of one
    `IntelligenceOutcome`'s `evidence_event_ids` list -- M38 spec §7's
    own small, explainable schema (explicitly not an opaque numerical
    score). Always recomputed live from the outcome's own fixed
    `outcome_at`/`created_at` and the current `SafetyEvent` rows; never
    persisted anywhere."""

    evidence_count: int
    valid_evidence_count: int
    invalid_evidence_count: int
    future_evidence_count: int
    evidence_status: EvidenceStatus
    #: True iff every supplied evidence id passed validation --
    #: `evidence_status == EvidenceStatus.VALID_EVIDENCE`. This is a
    #: *necessary* condition for granting `VERIFIED` (see module
    #: docstring and `record_verification()`'s own caller-side check in
    #: the API route) -- never a *sufficient* one; a human still has to
    #: explicitly write the `VERIFIED` row.
    evidence_eligible_for_verification: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class LearningEligibility:
    """The deterministic learning-eligibility gate (M38 spec §10) --
    a **gate only**: nothing reads `eligible` to actually learn
    anything. That remains a distinct, out-of-scope future milestone."""

    eligible: bool
    reasons: list[str] = field(default_factory=list)


@contextmanager
def verification_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one
    `IntelligenceOutcomeVerification` write -- identical shape to
    `intelligence_outcome_service.outcome_mutation_transaction()`/
    `intelligence_decision_service.decision_mutation_transaction()`.
    Commits once on success; rolls back once and re-raises, unchanged,
    on any exception."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def resolve_outcome_reference(
    db: Session, *, organization_id: uuid.UUID, outcome_id: uuid.UUID
) -> IntelligenceOutcome:
    """The identical "does this id belong to this organization" shape as
    `intelligence_decision_service.resolve_decision_reference()`,
    applied to `IntelligenceOutcome`: the one place a caller-supplied
    `outcome_id` is validated before creating a verification row that
    references it, or before evaluating its evidence. A nonexistent id
    or one from a different organization is a 404, never a silent
    cross-tenant read."""
    outcome = db.execute(
        select(IntelligenceOutcome).where(
            IntelligenceOutcome.id == outcome_id, IntelligenceOutcome.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="outcome_id not found in this organization."
        )
    return outcome


def reject_future_verified_at(verified_at: datetime) -> None:
    """A verification describes a review that has already happened (M38
    spec §6/§9 -- mirrors `intelligence_outcome_service.
    reject_future_outcome_at()`'s own identical rule for
    `IntelligenceOutcome.outcome_at`). A future `verified_at` is a 422,
    not a silently accepted prediction."""
    now = datetime.now(timezone.utc)
    reference = verified_at if verified_at.tzinfo is not None else verified_at.replace(tzinfo=timezone.utc)
    if reference > now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="verified_at must not be in the future.",
        )


def evaluate_outcome_evidence(db: Session, outcome: IntelligenceOutcome) -> EvidenceEvaluation:
    """Deterministically evaluate `outcome.evidence_event_ids` -- the
    one place this milestone decides whether supplied evidence is
    structurally and temporally acceptable. No fuzzy matching, no LLM,
    no weighted score (M38 spec §5/§7): every evidence id is checked
    against exactly two fixed timestamps already on `outcome` itself.

    **Why evidence validity is anchored to the outcome alone, not to any
    one verification's own `verified_at` (M38 spec §6's "consider ...
    verified_at" instruction, addressed here explicitly).** Once an
    `IntelligenceOutcome` is created, its `evidence_event_ids`,
    `outcome_at`, and `created_at` never change (M37's own
    immutability guarantee) and `SafetyEvent` rows are never deleted or
    mutated in this codebase either -- so whether one particular
    evidence id is "valid evidence for this outcome" is a fixed
    historical fact the moment the outcome is created, never a moving
    target that depends on which verification, or how many, later
    reference it. Threading each verification's own (also
    caller-supplied, per-review) `verified_at` into this check would let
    the *same* evidence id evaluate as valid for one verification row
    and invalid for another on the identical outcome -- an inconsistent,
    unexplainable result the spec's own "small and explainable" schema
    instruction (§7) rules out. `verified_at` therefore governs only
    that verification row's own audit trail and `as_of` visibility
    (`resolve_current_verification()` below), never evidence validity.

    For each id in `outcome.evidence_event_ids`:

    * not found, or found in a different organization -> **invalid**
      (`invalid_evidence_count`; the two cases are folded into one
      count and one generic reason -- mirroring every other
      "404 whether missing or foreign-organization" reference check in
      this codebase, this function does not reveal to a caller which
      case applies).
    * found, but `SafetyEvent.event_time > outcome.outcome_at` ->
      **future** (`future_evidence_count`; the evidence must have
      genuinely happened by the time the outcome became observable --
      reuses `events_as_of()`'s own `event_time` filter, with
      `outcome.outcome_at` playing the role `as_of` normally plays).
    * found, `event_time <= outcome.outcome_at`, but
      `SafetyEvent.ingestion_time > outcome.created_at` -> **invalid**
      (the evidence was not yet in the system when the outcome was
      recorded, so it could not genuinely have supported that report --
      reuses `events_as_of()`'s own `ingestion_time` filter, with
      `outcome.created_at` playing the role `as_of`).
    * otherwise -> **valid**.

    `evidence_status` (M38 spec §7's own A/B/C/D categories, deliberately
    without a fifth "disputed" value here -- disputed is a property of a
    verification row, not of the evidence itself, see
    `IntelligenceOutcomeVerificationStatus.DISPUTED`'s own docstring):

    * `NO_EVIDENCE` -- `evidence_count == 0`.
    * `INVALID_EVIDENCE` -- at least one id supplied, none of them valid.
    * `INSUFFICIENT_EVIDENCE` -- a mix: some valid, some not.
    * `VALID_EVIDENCE` -- every supplied id is valid.
    """
    evidence_ids = outcome.evidence_event_ids or []
    outcome_at = _as_utc(outcome.outcome_at)
    outcome_created_at = _as_utc(outcome.created_at)

    valid_count = 0
    invalid_count = 0
    future_count = 0
    reasons: list[str] = []

    for raw_id in evidence_ids:
        try:
            event_id = uuid.UUID(str(raw_id))
        except (ValueError, TypeError):
            invalid_count += 1
            reasons.append(f"evidence_event_id {raw_id!r} is not a valid id.")
            continue

        event = db.execute(
            select(SafetyEvent).where(SafetyEvent.id == event_id, SafetyEvent.organization_id == outcome.organization_id)
        ).scalar_one_or_none()
        if event is None:
            invalid_count += 1
            reasons.append(f"evidence_event_id {event_id} not found in this organization.")
            continue

        event_time = _as_utc(event.event_time)
        ingestion_time = _as_utc(event.ingestion_time)

        if event_time > outcome_at:
            future_count += 1
            reasons.append(
                f"evidence_event_id {event_id} has event_time after the outcome's own outcome_at "
                "(cannot be evidence for something that had not yet happened)."
            )
            continue

        if ingestion_time > outcome_created_at:
            invalid_count += 1
            reasons.append(
                f"evidence_event_id {event_id} was ingested after this outcome was recorded "
                "(not available at outcome-recording time)."
            )
            continue

        valid_count += 1

    evidence_count = len(evidence_ids)
    if evidence_count == 0:
        evidence_status = EvidenceStatus.NO_EVIDENCE
    elif valid_count == 0:
        evidence_status = EvidenceStatus.INVALID_EVIDENCE
    elif valid_count < evidence_count:
        evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE
    else:
        evidence_status = EvidenceStatus.VALID_EVIDENCE

    return EvidenceEvaluation(
        evidence_count=evidence_count,
        valid_evidence_count=valid_count,
        invalid_evidence_count=invalid_count,
        future_evidence_count=future_count,
        evidence_status=evidence_status,
        evidence_eligible_for_verification=(evidence_status == EvidenceStatus.VALID_EVIDENCE),
        reasons=reasons,
    )


def record_verification(
    db: Session,
    *,
    organization_id: uuid.UUID,
    outcome_id: uuid.UUID,
    status: IntelligenceOutcomeVerificationStatus,
    rationale: str,
    verified_at: datetime,
    verified_by_user_id: uuid.UUID | None,
    verified_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> IntelligenceOutcomeVerification:
    """Builds and `db.add()`s (never commits -- the caller's own
    `verification_mutation_transaction()` block does that) one
    `IntelligenceOutcomeVerification` row. Performs no evidence
    evaluation or business-rule enforcement itself -- the caller (the
    API route) has already resolved `outcome_id` and, when `status` is
    `VERIFIED`, already checked `evaluate_outcome_evidence()` before
    calling this function, mirroring `intelligence_outcome_service.
    record_outcome()`'s own "callers resolve/validate, this function
    only persists" split."""
    record = IntelligenceOutcomeVerification(
        organization_id=organization_id,
        outcome_id=outcome_id,
        status=status,
        rationale=rationale,
        verified_at=verified_at,
        verified_by_user_id=verified_by_user_id,
        verified_by_api_client_id=verified_by_api_client_id,
        request_id=request_id,
    )
    db.add(record)
    db.flush()  # populates record.id/created_at/updated_at for the response, without committing
    return record


def resolve_current_verification(
    db: Session, *, organization_id: uuid.UUID, outcome_id: uuid.UUID, as_of: datetime | None = None
) -> IntelligenceOutcomeVerification | None:
    """The deterministic "resolved current state" for one outcome's
    verification history (M38 spec §4's own "prefer created_at ordering"
    instruction): the single most recent
    `IntelligenceOutcomeVerification` row, ordered `created_at DESC,
    id DESC` -- never an aggregate, a vote, or a weighted combination of
    multiple rows. `None` when no verification has ever been recorded
    for this outcome (a distinct, and far more common, state than a row
    that exists and says `INSUFFICIENT_EVIDENCE`/`DISPUTED`, mirroring
    `IntelligenceOutcomeClassification.NO_OUTCOME_RECORDED`'s own
    "absence is not the same as an explicit statement" precedent).

    `as_of`, when supplied, restricts to rows with `created_at <= as_of`
    -- a verification recorded after `as_of` must not appear in a
    historical reconstruction (M38 spec §15)."""
    conditions = [
        IntelligenceOutcomeVerification.organization_id == organization_id,
        IntelligenceOutcomeVerification.outcome_id == outcome_id,
    ]
    if as_of is not None:
        conditions.append(IntelligenceOutcomeVerification.created_at <= as_of)
    return db.execute(
        select(IntelligenceOutcomeVerification)
        .where(*conditions)
        .order_by(IntelligenceOutcomeVerification.created_at.desc(), IntelligenceOutcomeVerification.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def evaluate_learning_eligibility(
    db: Session, *, outcome: IntelligenceOutcome, as_of: datetime | None = None
) -> LearningEligibility:
    """The deterministic learning-eligibility gate (M38 spec §10) -- a
    **gate only**. Nothing in this codebase reads `.eligible` to
    actually retrain, recalibrate, or adjust any model, threshold, or
    priority; that remains a distinct, out-of-scope future milestone
    (M39+). Requires, at minimum, per the spec's own list:

    1. the outcome exists (trivially true -- the caller already has it).
    2. the outcome is temporally valid as of `as_of` (when supplied):
       `outcome.outcome_at <= as_of` and `outcome.created_at <= as_of`
       -- mirrors `app/api/v1/intelligence_outcomes.py`'s own list-read
       `as_of` filter exactly, so "eligible as of `as_of`" and "visible
       as of `as_of`" never disagree.
    3. the resolved current verification (as of the same `as_of`) has
       `status == VERIFIED`.
    4. the outcome's own evidence evaluates as `VALID_EVIDENCE`
       (`evaluate_outcome_evidence()`) -- checked again here, even
       though the write path already refuses to create a `VERIFIED` row
       without it (defense in depth against the two ever silently
       drifting apart, at negligible cost since both are simple,
       deterministic, live recomputations, never cached).
    """
    reasons: list[str] = []

    if as_of is not None:
        outcome_at = _as_utc(outcome.outcome_at)
        outcome_created_at = _as_utc(outcome.created_at)
        if outcome_at > as_of or outcome_created_at > as_of:
            reasons.append("outcome is not yet visible as of the given as_of.")
            return LearningEligibility(eligible=False, reasons=reasons)

    current = resolve_current_verification(
        db, organization_id=outcome.organization_id, outcome_id=outcome.id, as_of=as_of
    )
    if current is None:
        reasons.append("no verification has been recorded for this outcome.")
        return LearningEligibility(eligible=False, reasons=reasons)
    if current.status != IntelligenceOutcomeVerificationStatus.VERIFIED:
        reasons.append(f"latest verification status is {current.status.value}, not VERIFIED.")
        return LearningEligibility(eligible=False, reasons=reasons)

    evidence = evaluate_outcome_evidence(db, outcome)
    if not evidence.evidence_eligible_for_verification:
        reasons.append(f"outcome evidence_status is {evidence.evidence_status.value}, not VALID_EVIDENCE.")
        return LearningEligibility(eligible=False, reasons=reasons)

    return LearningEligibility(eligible=True, reasons=[])
