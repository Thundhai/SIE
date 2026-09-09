"""Learning Candidate Foundation API — SIE Milestone 39.

    POST /intelligence/outcomes/{id}/verifications (M38, unchanged) -> IntelligenceOutcomeVerification
    POST /intelligence/learning-candidates      -> a durable IntelligenceLearningCandidate row (this router)
    GET  /intelligence/learning-candidates
    GET  /intelligence/learning-candidates/{candidate_id}
    POST /intelligence/learning-candidates/{candidate_id}/governance-decisions
    GET  /intelligence/learning-candidates/{candidate_id}/governance-decisions
    GET  /intelligence/learning-candidates/{candidate_id}/state

**The governed entry boundary into `LEARN` — still not the SIE learning
engine.** See `app/models/intelligence_learning_candidate.py`'s own
docstring and `docs/LEARNING_CANDIDATE_V0_1.md` for the full design
rationale, including the explicit statement that organizational memory
(M40) and learning integration (M41) are out of scope. No
`PUT`/`PATCH`/`DELETE` route exists or is planned for either
`IntelligenceLearningCandidate` or its governance decisions — a
correction is a new governance-decision row referencing the same
`candidate_id` (M39 spec §10).

**Eligibility vs. acceptance — kept as two different HTTP actions (M39
spec §8).** `POST /learning-candidates` is the deterministic eligibility
gate: it succeeds only when the outcome's resolved current verification
is `VERIFIED` with independently valid evidence (reuses M38's own
`evaluate_learning_eligibility()` verbatim — see
`app/services/intelligence_learning_candidate_service.py::
create_learning_candidate()`). `POST .../governance-decisions` is the
separate, later, human governance judgment (`ACCEPTED`/`REJECTED`)
about a candidate that already exists — never conflated with
eligibility, and never automatic.

**Authorization — reuses M34's decision-governance permission, not a
new role (M39 spec §14).** Creating a candidate or recording a
governance decision about one is the same trusted-authority tier as
recording the decision/outcome/verification that started the chain —
so `Permission.INTELLIGENCE_DECISION_WRITE` gates every write in this
router (granted to the same `HSE_MANAGER`/`HSE_ANALYST` roles), rather
than inventing a new permission. Every read reuses `Permission.
INTELLIGENCE_READ`.

**Tenant resolution — reuses the M38 architecture verbatim, never
redesigned (M39 spec §14).** Every handler resolves its operative
`organization_id` through `app.api.deps_context.
resolve_authorized_organization_id()` — the identical function
`app/api/v1/intelligence_outcomes.py`'s own three verification
endpoints already use (moved to a shared location in this same
milestone specifically so there is exactly one implementation, not two
— see that function's own docstring).

**Idempotency (M39 spec §15) — two independent guarantees, not one.**
`POST /learning-candidates` is idempotent *by construction*: `Intelligence
LearningCandidate` carries a DB-level `UNIQUE(organization_id,
outcome_id)` constraint, so a repeat call for the same outcome always
returns the existing row (`created=False`), never a duplicate or an
error — this holds even without any `Idempotency-Key` header. Both
write routes additionally support the `Idempotency-Key` header exactly
like every other write route in this codebase, guaranteeing exact
response replay on a retried request.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission, resolve_authorized_organization_id
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.models.intelligence_learning_candidate import (
    IntelligenceLearningCandidate,
    IntelligenceLearningCandidateGovernanceDecision,
)
from app.models.intelligence_outcome import IntelligenceOutcome
from app.models.intelligence_outcome_verification import IntelligenceOutcomeVerification
from app.schemas.intelligence_learning_candidate import (
    IntelligenceLearningCandidateCreate,
    IntelligenceLearningCandidateGovernanceDecisionCreate,
    IntelligenceLearningCandidateGovernanceDecisionListRead,
    IntelligenceLearningCandidateGovernanceDecisionRead,
    IntelligenceLearningCandidateListRead,
    IntelligenceLearningCandidateOutcomeRead,
    IntelligenceLearningCandidateRead,
    IntelligenceLearningCandidateStateRead,
    IntelligenceLearningCandidateVerificationRead,
)
from app.schemas.intelligence_outcome_verification import EvidenceEvaluationRead
from app.services.audit_service import AuditAction, audit_service
from app.services.intelligence_learning_candidate_service import (
    candidate_mutation_transaction,
    create_learning_candidate,
    governance_mutation_transaction,
    record_governance_decision,
    resolve_candidate_reference,
    resolve_current_governance,
)
from app.services.intelligence_outcome_verification_service import evaluate_outcome_evidence
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["intelligence-learning-candidates"])

_ENDPOINT_CREATE_CANDIDATE = "POST /intelligence/learning-candidates"
_ENDPOINT_CREATE_GOVERNANCE_DECISION = "POST /intelligence/learning-candidates/{candidate_id}/governance-decisions"


def _candidate_to_read(db: Session, record: IntelligenceLearningCandidate) -> IntelligenceLearningCandidateRead:
    outcome_read = None
    outcome = db.get(IntelligenceOutcome, record.outcome_id)
    if outcome is not None:
        outcome_read = IntelligenceLearningCandidateOutcomeRead(
            id=outcome.id,
            decision_id=outcome.decision_id,
            classification=outcome.classification,
            outcome_at=outcome.outcome_at,
            site_id=outcome.site_id,
            linked_action_id=outcome.linked_action_id,
        )

    verification_read = None
    verification = db.get(IntelligenceOutcomeVerification, record.verification_id)
    if verification is not None:
        verification_read = IntelligenceLearningCandidateVerificationRead(
            id=verification.id, status=verification.status, verified_at=verification.verified_at
        )

    return IntelligenceLearningCandidateRead(
        id=record.id,
        organization_id=record.organization_id,
        outcome_id=record.outcome_id,
        verification_id=record.verification_id,
        outcome=outcome_read,
        verification=verification_read,
        created_by_user_id=record.created_by_user_id,
        created_by_api_client_id=record.created_by_api_client_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _governance_to_read(
    record: IntelligenceLearningCandidateGovernanceDecision,
) -> IntelligenceLearningCandidateGovernanceDecisionRead:
    return IntelligenceLearningCandidateGovernanceDecisionRead(
        id=record.id,
        organization_id=record.organization_id,
        candidate_id=record.candidate_id,
        status=record.status,
        rationale=record.rationale,
        decided_at=record.decided_at,
        decided_by_user_id=record.decided_by_user_id,
        decided_by_api_client_id=record.decided_by_api_client_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post(
    "/learning-candidates",
    response_model=IntelligenceLearningCandidateRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_intelligence_learning_candidate(
    body: IntelligenceLearningCandidateCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> IntelligenceLearningCandidateRead:
    """Creates (or returns the existing) learning candidate for
    `body.outcome_id`. Never mutates the outcome or its verification —
    the one write this route performs is the new
    `IntelligenceLearningCandidate` row itself, and only when one does
    not already exist for this outcome."""
    organization_id = resolve_authorized_organization_id(context, organization_id)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE_CANDIDATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return IntelligenceLearningCandidateRead.model_validate(lookup.response_body)

    with candidate_mutation_transaction(db):
        candidate, created = create_learning_candidate(
            db,
            organization_id=organization_id,
            outcome_id=body.outcome_id,
            created_by_user_id=context.user_id,
            created_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        if created:
            audit_service.log(
                db,
                action=AuditAction.INTELLIGENCE_LEARNING_CANDIDATE_CREATED,
                resource_type="IntelligenceLearningCandidate",
                resource_id=candidate.id,
                organization_id=organization_id,
                user_id=context.user_id,
                metadata={
                    "outcome_id": str(candidate.outcome_id),
                    "verification_id": str(candidate.verification_id),
                    "caller_kind": context.kind,
                },
                request_id=request_id,
                commit=False,
            )
        result = _candidate_to_read(db, candidate)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE_CANDIDATE,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_status_code=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
            organization_id=organization_id,
            api_client_id=context.api_client_id,
            user_id=context.user_id,
            commit=False,
        )
    return result


@router.get(
    "/learning-candidates",
    response_model=IntelligenceLearningCandidateListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_intelligence_learning_candidates(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    outcome_id: uuid.UUID | None = Query(default=None),
    as_of: datetime | None = Query(
        default=None, description="Point-in-time cutoff: only candidates with created_at <= as_of are returned."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceLearningCandidateListRead:
    """No candidate is ever mutated after creation -- at most one exists
    per `outcome_id` (the `UNIQUE(organization_id, outcome_id)`
    constraint), so this list is simply every candidate this
    organization currently has, newest first."""
    organization_id = resolve_authorized_organization_id(context, organization_id)

    conditions = [IntelligenceLearningCandidate.organization_id == organization_id]
    if outcome_id:
        conditions.append(IntelligenceLearningCandidate.outcome_id == outcome_id)
    if as_of is not None:
        conditions.append(IntelligenceLearningCandidate.created_at <= as_of)

    total = db.execute(select(func.count()).select_from(IntelligenceLearningCandidate).where(*conditions)).scalar_one()
    rows = (
        db.execute(
            select(IntelligenceLearningCandidate)
            .where(*conditions)
            .order_by(IntelligenceLearningCandidate.created_at.desc(), IntelligenceLearningCandidate.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return IntelligenceLearningCandidateListRead(
        items=[_candidate_to_read(db, r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/learning-candidates/{candidate_id}",
    response_model=IntelligenceLearningCandidateRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_intelligence_learning_candidate(
    candidate_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceLearningCandidateRead:
    """A candidate from a different organization (or a nonexistent id)
    is a 404, never a 403 -- mirrors every other single-resource GET in
    this codebase."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    candidate = resolve_candidate_reference(db, organization_id=organization_id, candidate_id=candidate_id)
    return _candidate_to_read(db, candidate)


@router.post(
    "/learning-candidates/{candidate_id}/governance-decisions",
    response_model=IntelligenceLearningCandidateGovernanceDecisionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_learning_candidate_governance_decision(
    candidate_id: uuid.UUID,
    body: IntelligenceLearningCandidateGovernanceDecisionCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> IntelligenceLearningCandidateGovernanceDecisionRead:
    """Records one human governance judgment (`ACCEPTED`/`REJECTED`)
    about one existing learning candidate. Never mutates the candidate,
    its outcome, or its verification -- the one write this route
    performs is the new `IntelligenceLearningCandidateGovernanceDecision`
    row. Unlike candidate creation, this is **not** idempotent by a
    natural key: a second call is a legitimate new governance event
    (e.g. a later reviewer changing an earlier decision) and creates a
    second row, preserving history -- only the `Idempotency-Key` header
    protects against an accidental duplicate submission of the *same*
    request."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    resolve_candidate_reference(db, organization_id=organization_id, candidate_id=candidate_id)

    request_hash = compute_request_hash(f"{candidate_id}:{body.model_dump_json()}".encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE_GOVERNANCE_DECISION,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return IntelligenceLearningCandidateGovernanceDecisionRead.model_validate(lookup.response_body)

    with governance_mutation_transaction(db):
        record = record_governance_decision(
            db,
            organization_id=organization_id,
            candidate_id=candidate_id,
            status=body.status,
            rationale=body.rationale,
            decided_by_user_id=context.user_id,
            decided_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_service.log(
            db,
            action=AuditAction.INTELLIGENCE_LEARNING_CANDIDATE_GOVERNANCE_DECISION_RECORDED,
            resource_type="IntelligenceLearningCandidateGovernanceDecision",
            resource_id=record.id,
            organization_id=organization_id,
            user_id=context.user_id,
            metadata={
                "candidate_id": str(candidate_id),
                "status": record.status.value,
                "caller_kind": context.kind,
            },
            request_id=request_id,
            commit=False,
        )
        result = _governance_to_read(record)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE_GOVERNANCE_DECISION,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_status_code=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
            organization_id=organization_id,
            api_client_id=context.api_client_id,
            user_id=context.user_id,
            commit=False,
        )
    return result


@router.get(
    "/learning-candidates/{candidate_id}/governance-decisions",
    response_model=IntelligenceLearningCandidateGovernanceDecisionListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_learning_candidate_governance_decisions(
    candidate_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    as_of: datetime | None = Query(
        default=None, description="Point-in-time cutoff: only decisions with created_at <= as_of are returned."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceLearningCandidateGovernanceDecisionListRead:
    """No governance decision is ever mutated after creation -- this
    list, ordered newest-first, *is* the correction/audit history for
    this candidate's governance. 404s (rather than an empty list) if
    `candidate_id` itself does not belong to this organization."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    resolve_candidate_reference(db, organization_id=organization_id, candidate_id=candidate_id)

    conditions = [
        IntelligenceLearningCandidateGovernanceDecision.organization_id == organization_id,
        IntelligenceLearningCandidateGovernanceDecision.candidate_id == candidate_id,
    ]
    if as_of is not None:
        conditions.append(IntelligenceLearningCandidateGovernanceDecision.created_at <= as_of)

    total = db.execute(
        select(func.count()).select_from(IntelligenceLearningCandidateGovernanceDecision).where(*conditions)
    ).scalar_one()
    rows = (
        db.execute(
            select(IntelligenceLearningCandidateGovernanceDecision)
            .where(*conditions)
            .order_by(
                IntelligenceLearningCandidateGovernanceDecision.created_at.desc(),
                IntelligenceLearningCandidateGovernanceDecision.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return IntelligenceLearningCandidateGovernanceDecisionListRead(
        items=[_governance_to_read(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/learning-candidates/{candidate_id}/state",
    response_model=IntelligenceLearningCandidateStateRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_learning_candidate_state(
    candidate_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(
        default=None,
        description=(
            "Point-in-time cutoff applied to the resolved governance decision. Omit for the current, "
            "unfiltered view. The live evidence re-evaluation always reflects the current database state, "
            "regardless of as_of -- see module docstring's own 'currently revalidated' distinction."
        ),
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceLearningCandidateStateRead:
    """Combines the candidate, its resolved current governance decision
    (or `None` if never governed -- "pending"), and a *live*
    re-evaluation of the originating outcome's evidence into one
    response -- mirrors `IntelligenceOutcomeVerificationStateRead`'s own
    identical shape. Nothing here is persisted; every field is
    recomputed live on each call."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    candidate = resolve_candidate_reference(db, organization_id=organization_id, candidate_id=candidate_id)

    current_governance = resolve_current_governance(
        db, organization_id=organization_id, candidate_id=candidate_id, as_of=as_of
    )

    outcome = db.get(IntelligenceOutcome, candidate.outcome_id)
    if outcome is None:  # pragma: no cover -- CASCADE FK makes this structurally unreachable
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Originating outcome no longer exists.")
    evidence_evaluation = evaluate_outcome_evidence(db, outcome)

    return IntelligenceLearningCandidateStateRead(
        candidate=_candidate_to_read(db, candidate),
        current_governance=_governance_to_read(current_governance) if current_governance is not None else None,
        current_evidence_evaluation=EvidenceEvaluationRead(
            evidence_count=evidence_evaluation.evidence_count,
            valid_evidence_count=evidence_evaluation.valid_evidence_count,
            invalid_evidence_count=evidence_evaluation.invalid_evidence_count,
            future_evidence_count=evidence_evaluation.future_evidence_count,
            evidence_status=evidence_evaluation.evidence_status,
            evidence_eligible_for_verification=evidence_evaluation.evidence_eligible_for_verification,
            reasons=evidence_evaluation.reasons,
        ),
    )


__all__ = ["router"]
