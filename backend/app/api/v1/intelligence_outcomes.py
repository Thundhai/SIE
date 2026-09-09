"""Field Outcome Foundation API — SIE Milestone 37.

    POST /intelligence/decisions (M34, unchanged) -> human decision/intervention
    POST /intelligence/outcomes  -> a durable IntelligenceOutcome row (this router)
    GET  /intelligence/outcomes
    GET  /intelligence/outcomes/{outcome_id}

**A ground-truth capture layer, not the SIE learning engine.** See
`app/models/intelligence_outcome.py`'s own docstring and
`docs/FIELD_OUTCOME_FOUNDATION_V0_1.md` for the full design rationale.
No `PUT`/`PATCH`/`DELETE` route exists or is planned — a correction is a
new row referencing the same `decision_id` (§6).

**Authorization — reuses M34's decision-governance permission, not a
new role (§10).** Recording an outcome is the same trusted-authority
tier as recording the decision it reports on, within one continuous
DECIDE -> INTERVENE -> OUTCOME human-governance capability — so
`Permission.INTELLIGENCE_DECISION_WRITE` gates the write here too
(granted to the same `HSE_MANAGER`/`HSE_ANALYST` roles), rather than
inventing a new `INTELLIGENCE_OUTCOME_WRITE` permission for what is not
a genuinely new capability tier. The two reads reuse
`Permission.INTELLIGENCE_READ`, identical to every other intelligence
read route in this codebase.

**Point-in-time reads (§14).** `GET /intelligence/outcomes` accepts an
optional `as_of`; when supplied, only rows with both `outcome_at <=
as_of` and `created_at <= as_of` are returned — see
`app/models/intelligence_outcome.py`'s own "outcome_at vs. created_at"
section for why both timestamps are checked. No new
`app/intelligence/temporal.py` helper is needed for this: unlike
M35B/M36's history-reconstruction problem, `IntelligenceOutcome` rows
are already immutable/append-only, so the correct point-in-time
semantics reduce to a direct two-column filter applied straight in this
list query.
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
from app.models.safety_action import SafetyAction
from app.models.site import Site
from app.schemas.intelligence_outcome import (
    IntelligenceOutcomeActionRead,
    IntelligenceOutcomeCreate,
    IntelligenceOutcomeDecisionRead,
    IntelligenceOutcomeListRead,
    IntelligenceOutcomeRead,
)
from app.services.audit_service import AuditAction, audit_service
from app.services.intelligence_outcome_service import (
    outcome_mutation_transaction,
    record_outcome,
    reject_future_outcome_at,
    resolve_decision_reference,
)
from app.services.permissions import Permission
from app.services.risk_assessment_service import resolve_action_reference
from app.services.safety_action_service import validate_site_reference, validate_source_event_reference

router = APIRouter(prefix="/intelligence", tags=["intelligence-outcomes"])

_ENDPOINT_CREATE = "POST /intelligence/outcomes"


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


__all__ = ["router"]
