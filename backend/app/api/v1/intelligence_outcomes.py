"""Field Outcome Foundation API — SIE Milestone 37, extended by SIE
Milestone 38 (Outcome Verification & Evidence).

    POST /intelligence/decisions (M34, unchanged) -> human decision/intervention
    POST /intelligence/outcomes  -> a durable IntelligenceOutcome row (M37)
    GET  /intelligence/outcomes
    GET  /intelligence/outcomes/{outcome_id}
    POST /intelligence/outcomes/{outcome_id}/verifications      -> IntelligenceOutcomeVerification (M38)
    GET  /intelligence/outcomes/{outcome_id}/verifications
    GET  /intelligence/outcomes/{outcome_id}/verification-state -> resolved governance state (M38)

**A ground-truth capture layer, not the SIE learning engine.** See
`app/models/intelligence_outcome.py`'s own docstring and
`docs/FIELD_OUTCOME_FOUNDATION_V0_1.md` for the full M37 design
rationale. No `PUT`/`PATCH`/`DELETE` route exists or is planned for
either `IntelligenceOutcome` or `IntelligenceOutcomeVerification` — a
correction is a new row referencing the same `decision_id`/`outcome_id`
respectively (M37 §6; M38 spec §4).

**Authorization — reuses M34's decision-governance permission, not a
new role (§10, M38 spec §12).** Recording an outcome or a verification
of one is the same trusted-authority tier as recording the decision that
started the chain, within one continuous DECIDE -> INTERVENE -> OUTCOME
-> VERIFY human-governance capability — so `Permission.
INTELLIGENCE_DECISION_WRITE` gates every write in this router (granted
to the same `HSE_MANAGER`/`HSE_ANALYST` roles), rather than inventing a
new permission for what is not a genuinely new capability tier. Every
read reuses `Permission.INTELLIGENCE_READ`, identical to every other
intelligence read route in this codebase.

**Point-in-time reads (§14, M38 spec §15).** `GET /intelligence/outcomes`
accepts an optional `as_of`; when supplied, only rows with both
`outcome_at <= as_of` and `created_at <= as_of` are returned — see
`app/models/intelligence_outcome.py`'s own "outcome_at vs. created_at"
section for why both timestamps are checked. The M38 verification
endpoints accept the identical `as_of` parameter, applied consistently:
a verification recorded after `as_of` never appears
(`created_at <= as_of` — see
`app/services/intelligence_outcome_verification_service.py::
resolve_current_verification()`), and an outcome not yet visible as of
`as_of` is excluded from eligibility the same way the M37 list read
already excludes it (`evaluate_learning_eligibility()`'s own
`as_of`-aware check) — one interpretation of `as_of`, never two. No new
`app/intelligence/temporal.py` helper is needed for any of this: unlike
M35B/M36's history-reconstruction problem, both `IntelligenceOutcome`
and `IntelligenceOutcomeVerification` rows are already
immutable/append-only, so the correct point-in-time semantics reduce to
direct column filters applied straight in these queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.models.intelligence_decision import IntelligenceDecision
from app.models.intelligence_outcome import IntelligenceOutcome
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification
from app.models.intelligence_outcome_verification import IntelligenceOutcomeVerification
from app.models.intelligence_outcome_verification_enums import IntelligenceOutcomeVerificationStatus
from app.models.safety_action import SafetyAction
from app.models.site import Site
from app.schemas.intelligence_outcome import (
    IntelligenceOutcomeActionRead,
    IntelligenceOutcomeCreate,
    IntelligenceOutcomeDecisionRead,
    IntelligenceOutcomeListRead,
    IntelligenceOutcomeRead,
)
from app.schemas.intelligence_outcome_verification import (
    EvidenceEvaluationRead,
    IntelligenceOutcomeVerificationCreate,
    IntelligenceOutcomeVerificationListRead,
    IntelligenceOutcomeVerificationRead,
    IntelligenceOutcomeVerificationStateRead,
    LearningEligibilityRead,
)
from app.services.audit_service import AuditAction, audit_service
from app.services.intelligence_outcome_service import (
    outcome_mutation_transaction,
    record_outcome,
    reject_future_outcome_at,
    resolve_decision_reference,
)
from app.services.intelligence_outcome_verification_service import (
    EvidenceEvaluation,
    evaluate_learning_eligibility,
    evaluate_outcome_evidence,
    record_verification,
    reject_future_verified_at,
    resolve_current_verification,
    resolve_outcome_reference,
    verification_mutation_transaction,
)
from app.services.permissions import Permission
from app.services.risk_assessment_service import resolve_action_reference
from app.services.safety_action_service import validate_site_reference, validate_source_event_reference

router = APIRouter(prefix="/intelligence", tags=["intelligence-outcomes"])

_ENDPOINT_CREATE = "POST /intelligence/outcomes"
_ENDPOINT_CREATE_VERIFICATION = "POST /intelligence/outcomes/{outcome_id}/verifications"


def _to_read(db: Session, record: IntelligenceOutcome) -> IntelligenceOutcomeRead:
    decision_read = None
    decision = db.get(IntelligenceDecision, record.decision_id)
    if decision is not None:
        decision_read = IntelligenceOutcomeDecisionRead(
            id=decision.id, attention_reference=decision.attention_reference, decision=decision.decision.value
        )

    site_label = None
    if record.site_id is not None:
        site = db.get(Site, record.site_id)
        site_label = site.name if site is not None else None

    linked_action_read = None
    if record.linked_action_id is not None:
        action = db.get(SafetyAction, record.linked_action_id)
        if action is not None:
            linked_action_read = IntelligenceOutcomeActionRead(
                id=action.id, title=action.title, status=action.status.value
            )

    return IntelligenceOutcomeRead(
        id=record.id,
        organization_id=record.organization_id,
        decision_id=record.decision_id,
        decision=decision_read,
        site_id=record.site_id,
        site_label=site_label,
        linked_action_id=record.linked_action_id,
        linked_action=linked_action_read,
        classification=record.classification,
        summary=record.summary,
        evidence_event_ids=record.evidence_event_ids or [],
        outcome_at=record.outcome_at,
        recorded_by_user_id=record.recorded_by_user_id,
        recorded_by_api_client_id=record.recorded_by_api_client_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post(
    "/outcomes",
    response_model=IntelligenceOutcomeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_intelligence_outcome(
    body: IntelligenceOutcomeCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> IntelligenceOutcomeRead:
    """Records one ground-truth outcome for one existing
    `IntelligenceDecision`. Never mutates the decision, the optionally
    referenced `SafetyAction`, or any other domain row — the one write
    this route performs is the new `IntelligenceOutcome` row itself."""
    resolve_decision_reference(db, organization_id=organization_id, decision_id=body.decision_id)

    if body.site_id is not None:
        validate_site_reference(db, organization_id=organization_id, site_id=body.site_id)

    linked_action_id: uuid.UUID | None = None
    if body.linked_action_id is not None:
        linked_action = resolve_action_reference(db, organization_id=organization_id, action_id=body.linked_action_id)
        linked_action_id = linked_action.id

    for event_id in body.evidence_event_ids or []:
        validate_source_event_reference(db, organization_id=organization_id, source_event_id=event_id)

    reject_future_outcome_at(body.outcome_at)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return IntelligenceOutcomeRead.model_validate(lookup.response_body)

    # Everything from here on -- the IntelligenceOutcome row, its
    # AuditLog entry, and the IdempotencyKey response -- is one
    # transaction: all of it commits together, once, or none of it
    # persists. Mirrors app.services.intelligence_decision_service's own
    # decision_mutation_transaction() shape exactly.
    with outcome_mutation_transaction(db):
        record = record_outcome(
            db,
            organization_id=organization_id,
            decision_id=body.decision_id,
            site_id=body.site_id,
            linked_action_id=linked_action_id,
            classification=body.classification,
            summary=body.summary,
            evidence_event_ids=body.evidence_event_ids,
            outcome_at=body.outcome_at,
            recorded_by_user_id=context.user_id,
            recorded_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_service.log(
            db,
            action=AuditAction.INTELLIGENCE_OUTCOME_RECORDED,
            resource_type="IntelligenceOutcome",
            resource_id=record.id,
            organization_id=organization_id,
            user_id=context.user_id,
            metadata={
                "decision_id": str(record.decision_id),
                "classification": record.classification.value,
                "linked_action_id": str(linked_action_id) if linked_action_id else None,
                "caller_kind": context.kind,
            },
            request_id=request_id,
            commit=False,
        )
        result = _to_read(db, record)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE,
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
    "/outcomes",
    response_model=IntelligenceOutcomeListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_intelligence_outcomes(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    site_id: uuid.UUID | None = Query(default=None),
    decision_id: uuid.UUID | None = Query(
        default=None,
        description="Filter to every outcome recorded about one specific decision -- the append-only outcome/correction history for it, newest first.",
    ),
    linked_action_id: uuid.UUID | None = Query(default=None),
    classification: IntelligenceOutcomeClassification | None = Query(default=None),
    as_of: datetime | None = Query(
        default=None,
        description=(
            "Point-in-time cutoff: only outcomes with both outcome_at <= as_of and created_at <= as_of are "
            "returned. Omit for the current, unfiltered view."
        ),
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceOutcomeListRead:
    """No outcome is ever mutated after creation (see
    `IntelligenceOutcome`'s own "immutable" docstring section) -- when
    multiple outcomes share one `decision_id`, this list, ordered
    newest-first, *is* that decision's outcome/correction history."""
    conditions = [IntelligenceOutcome.organization_id == organization_id]
    if site_id:
        conditions.append(IntelligenceOutcome.site_id == site_id)
    if decision_id:
        conditions.append(IntelligenceOutcome.decision_id == decision_id)
    if linked_action_id:
        conditions.append(IntelligenceOutcome.linked_action_id == linked_action_id)
    if classification:
        conditions.append(IntelligenceOutcome.classification == classification)
    if as_of is not None:
        conditions.append(IntelligenceOutcome.outcome_at <= as_of)
        conditions.append(IntelligenceOutcome.created_at <= as_of)

    total = db.execute(select(func.count()).select_from(IntelligenceOutcome).where(*conditions)).scalar_one()
    rows = (
        db.execute(
            select(IntelligenceOutcome)
            .where(*conditions)
            .order_by(
                IntelligenceOutcome.outcome_at.desc(),
                IntelligenceOutcome.created_at.desc(),
                IntelligenceOutcome.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return IntelligenceOutcomeListRead(
        items=[_to_read(db, r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/outcomes/{outcome_id}",
    response_model=IntelligenceOutcomeRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_intelligence_outcome(
    outcome_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceOutcomeRead:
    """An outcome from a different organization (or a nonexistent id) is
    a 404, never a 403 -- mirrors every other single-resource GET in
    this codebase's own "never reveal whether a given id exists in
    someone else's tenant" rule."""
    record = db.execute(
        select(IntelligenceOutcome).where(
            IntelligenceOutcome.id == outcome_id, IntelligenceOutcome.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outcome not found in this organization.")
    return _to_read(db, record)


# ==================================================================================================
# SIE Milestone 38: Outcome Verification & Evidence
# ==================================================================================================


def _authorized_organization_id(context: RequestContext, organization_id: uuid.UUID) -> uuid.UUID:
    """Corrective hardening for the M38 verification endpoints only
    (the three routes below) — every organization-scoped lookup/write
    they perform uses the value this function returns, never the raw
    `organization_id` query parameter directly, even though
    `require_context_permission`'s own `authorize_context()` has already
    authorized that query value against `context` before any of these
    handlers runs.

    For a **machine** caller, the authoritative tenant is `context.
    machine_organization_id` — resolved once, at credential
    authentication time, from `ApiClient.organization_id`, and never
    overridable by request content (see `app/api/deps_context.py`'s own
    "item 36" docstring section). Returning it here directly, instead of
    the query string, removes these three handlers' own reliance on
    `authorize_context()`'s equality check continuing to hold correct
    forever — pure defense in depth: the two are already guaranteed
    equal by the time this function runs, so no currently-observable
    behavior changes, but a future bug in that check could no longer
    let a machine credential's own request string name a *different*
    organization than the one its credential actually belongs to.

    For a **human** caller, `RequestContext` deliberately carries no
    organization id of its own — a human may hold membership in more
    than one organization, and the query parameter is how every human
    request in this codebase (M34's decisions, M37's own outcomes
    endpoints included) already indicates which one it is acting in,
    already authorized against that caller's own membership+permission
    by `authorize_context()` before this function is ever reached. There
    is no other, more-authoritative source to prefer for a human caller
    without inventing a new tenant-selection mechanism across the whole
    API — out of scope for this narrow M38 correction (M37's own
    identical `organization_id=Query(...)` endpoints are deliberately
    left unchanged, per instruction)."""
    if context.is_machine:
        assert context.machine_organization_id is not None, "machine RequestContext always carries its own org id"
        return context.machine_organization_id
    return organization_id


def _verification_to_read(record: IntelligenceOutcomeVerification) -> IntelligenceOutcomeVerificationRead:
    return IntelligenceOutcomeVerificationRead(
        id=record.id,
        organization_id=record.organization_id,
        outcome_id=record.outcome_id,
        status=record.status,
        rationale=record.rationale,
        verified_at=record.verified_at,
        verified_by_user_id=record.verified_by_user_id,
        verified_by_api_client_id=record.verified_by_api_client_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _evidence_evaluation_to_read(evaluation: EvidenceEvaluation) -> EvidenceEvaluationRead:
    return EvidenceEvaluationRead(
        evidence_count=evaluation.evidence_count,
        valid_evidence_count=evaluation.valid_evidence_count,
        invalid_evidence_count=evaluation.invalid_evidence_count,
        future_evidence_count=evaluation.future_evidence_count,
        evidence_status=evaluation.evidence_status,
        evidence_eligible_for_verification=evaluation.evidence_eligible_for_verification,
        reasons=evaluation.reasons,
    )


@router.post(
    "/outcomes/{outcome_id}/verifications",
    response_model=IntelligenceOutcomeVerificationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_outcome_verification(
    outcome_id: uuid.UUID,
    body: IntelligenceOutcomeVerificationCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> IntelligenceOutcomeVerificationRead:
    """Records one governance judgment about one existing
    `IntelligenceOutcome`'s trustworthiness. Never mutates the outcome
    itself, or any other domain row — the one write this route performs
    is the new `IntelligenceOutcomeVerification` row.

    **"VALID EVIDENCE ≠ VERIFIED OUTCOME" enforced here (M38 spec §8-9).**
    `status=VERIFIED` is rejected (422) unless the outcome's own evidence
    deterministically evaluates as fully valid
    (`evaluate_outcome_evidence()`) — a *necessary* condition this route
    enforces, never a *sufficient* one: valid evidence alone never
    creates a `VERIFIED` row automatically, only an explicit human
    request with that status does. `INSUFFICIENT_EVIDENCE`/`DISPUTED`
    carry no such requirement — a human may record either regardless of
    what the evidence evaluation says, since both are legitimate human
    judgments the evidence check does not gate."""
    organization_id = _authorized_organization_id(context, organization_id)
    outcome = resolve_outcome_reference(db, organization_id=organization_id, outcome_id=outcome_id)
    reject_future_verified_at(body.verified_at)

    if body.status == IntelligenceOutcomeVerificationStatus.VERIFIED:
        evaluation = evaluate_outcome_evidence(db, outcome)
        if not evaluation.evidence_eligible_for_verification:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Cannot record VERIFIED: outcome evidence_status is {evaluation.evidence_status.value}, "
                    "not VALID_EVIDENCE. " + " ".join(evaluation.reasons)
                ).strip(),
            )

    request_hash = compute_request_hash(f"{outcome_id}:{body.model_dump_json()}".encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE_VERIFICATION,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return IntelligenceOutcomeVerificationRead.model_validate(lookup.response_body)

    # Everything from here on -- the IntelligenceOutcomeVerification row,
    # its AuditLog entry, and the IdempotencyKey response -- is one
    # transaction: all of it commits together, once, or none of it
    # persists. Mirrors outcome_mutation_transaction()/
    # decision_mutation_transaction()'s own shape exactly.
    with verification_mutation_transaction(db):
        record = record_verification(
            db,
            organization_id=organization_id,
            outcome_id=outcome_id,
            status=body.status,
            rationale=body.rationale,
            verified_at=body.verified_at,
            verified_by_user_id=context.user_id,
            verified_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_service.log(
            db,
            action=AuditAction.INTELLIGENCE_OUTCOME_VERIFICATION_RECORDED,
            resource_type="IntelligenceOutcomeVerification",
            resource_id=record.id,
            organization_id=organization_id,
            user_id=context.user_id,
            metadata={
                "outcome_id": str(outcome_id),
                "status": record.status.value,
                "caller_kind": context.kind,
            },
            request_id=request_id,
            commit=False,
        )
        result = _verification_to_read(record)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE_VERIFICATION,
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
    "/outcomes/{outcome_id}/verifications",
    response_model=IntelligenceOutcomeVerificationListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_outcome_verifications(
    outcome_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    as_of: datetime | None = Query(
        default=None, description="Point-in-time cutoff: only verifications with created_at <= as_of are returned."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceOutcomeVerificationListRead:
    """No verification is ever mutated after creation (M38 spec §4) --
    this list, ordered newest-first, *is* the correction/audit history
    for this outcome's verification. 404s (rather than an empty list) if
    `outcome_id` itself does not belong to this organization, mirroring
    every other nested-resource read in this codebase."""
    organization_id = _authorized_organization_id(context, organization_id)
    resolve_outcome_reference(db, organization_id=organization_id, outcome_id=outcome_id)

    conditions = [
        IntelligenceOutcomeVerification.organization_id == organization_id,
        IntelligenceOutcomeVerification.outcome_id == outcome_id,
    ]
    if as_of is not None:
        conditions.append(IntelligenceOutcomeVerification.created_at <= as_of)

    total = db.execute(select(func.count()).select_from(IntelligenceOutcomeVerification).where(*conditions)).scalar_one()
    rows = (
        db.execute(
            select(IntelligenceOutcomeVerification)
            .where(*conditions)
            .order_by(IntelligenceOutcomeVerification.created_at.desc(), IntelligenceOutcomeVerification.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return IntelligenceOutcomeVerificationListRead(
        items=[_verification_to_read(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/outcomes/{outcome_id}/verification-state",
    response_model=IntelligenceOutcomeVerificationStateRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_outcome_verification_state(
    outcome_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(
        default=None,
        description=(
            "Point-in-time cutoff applied consistently to the resolved verification, the evidence "
            "evaluation, and the learning-eligibility gate. Omit for the current, unfiltered view."
        ),
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceOutcomeVerificationStateRead:
    """The one read this milestone's spec asks for "if useful, but do
    not create redundant APIs" (§11) — combines the resolved current
    verification (newest row by `created_at`, or `None` if none has ever
    been recorded), the live deterministic evidence evaluation, and the
    learning-eligibility gate into a single response, rather than
    requiring three separate round trips to reconstruct one governance
    picture. Nothing here is persisted; every field is recomputed live
    on each call (M38 spec §17's own "a reviewer should be able to
    reconstruct OUTCOME -> EVIDENCE -> EVIDENCE VALIDATION ->
    VERIFICATION -> LEARNING ELIGIBILITY without guessing")."""
    organization_id = _authorized_organization_id(context, organization_id)
    outcome = resolve_outcome_reference(db, organization_id=organization_id, outcome_id=outcome_id)

    current = resolve_current_verification(db, organization_id=organization_id, outcome_id=outcome_id, as_of=as_of)
    evaluation = evaluate_outcome_evidence(db, outcome)
    eligibility = evaluate_learning_eligibility(db, outcome=outcome, as_of=as_of)

    return IntelligenceOutcomeVerificationStateRead(
        outcome_id=outcome_id,
        current_verification=_verification_to_read(current) if current is not None else None,
        evidence_evaluation=_evidence_evaluation_to_read(evaluation),
        learning_eligibility=LearningEligibilityRead(eligible=eligibility.eligible, reasons=eligibility.reasons),
    )


__all__ = ["router"]
