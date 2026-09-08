"""Human Decision & Intervention Trace API — SIE Milestone 34.

    GET /intelligence/attention (M33, read-only, unchanged)
        -> human reviews an AttentionItem, decides
    POST /intelligence/decisions  -> a durable IntelligenceDecision row
    GET  /intelligence/decisions
    GET  /intelligence/decisions/{decision_id}

**The first intentional write in the SIE intelligence workflow** (M30-M33
were architecture/read-only). Narrowly scoped to recording a human
decision and, where the human explicitly supplies one, its relationship
to an existing `SafetyAction` — never a second action-creation path, and
never a write to any other domain (findings, assessments, predictions,
events). See `app/models/intelligence_decision.py`'s own docstring for
the full design rationale and `app/services/intelligence_decision_service.py`
for the "what SIE said is always server-derived, never client-trusted"
trust boundary.

**Same authorization shape every other route in this router already
uses.** `organization_id` is the authorize-then-trust query parameter;
`RequestContext`/`require_context_permission()` is the one auth
dependency (never a second framework); the decision-maker is
`context.user_id`/`context.api_client_id` — `POST`'s own request body
has no `decided_by_*` field at all, so there is nothing for a client to
spoof (§3). `Permission.INTELLIGENCE_DECISION_WRITE` gates the write
(granted to `HSE_MANAGER`/`HSE_ANALYST`, the same roles that already
hold `RISK_ASSESSMENT_WRITE` — see `app/services/permissions.py`'s own
docstring for the reasoning); the two reads reuse
`Permission.INTELLIGENCE_READ`, identical to every other read route in
`app/api/v1/intelligence.py`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.config import settings
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.models.intelligence_decision import IntelligenceDecision
from app.models.intelligence_decision_enums import IntelligenceDecisionType
from app.models.safety_action import SafetyAction
from app.models.site import Site
from app.schemas.intelligence_decision import (
    IntelligenceDecisionActionRead,
    IntelligenceDecisionCreate,
    IntelligenceDecisionListRead,
    IntelligenceDecisionRead,
)
from app.services.audit_service import AuditAction, audit_service
from app.services.intelligence_decision_service import (
    decision_mutation_transaction,
    record_decision,
    resolve_attention_item,
)
from app.services.permissions import Permission
from app.services.risk_assessment_service import resolve_action_reference
from app.services.safety_action_service import validate_site_reference

router = APIRouter(prefix="/intelligence", tags=["intelligence-decisions"])

_ENDPOINT_CREATE = "POST /intelligence/decisions"


def _validate_window_days(window_days: int) -> None:
    """Identical rule to `app/api/v1/intelligence.py::_validate_window_days()`
    — duplicated locally rather than imported, mirroring
    `app/api/v1/predictions.py`'s own established convention of keeping
    this kind of small, route-layer helper self-contained per file (see
    that file's own `_require_owned_site()`) rather than reaching into a
    sibling router module's private helpers."""
    if window_days not in settings.ENTERPRISE_INTELLIGENCE_ALLOWED_WINDOW_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"window_days must be one of {settings.ENTERPRISE_INTELLIGENCE_ALLOWED_WINDOW_DAYS}, "
                f"got {window_days}."
            ),
        )


def _validate_scope(scope: str, site_id: uuid.UUID | None) -> None:
    if scope not in ("organization", "site"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope must be 'organization' or 'site'.")
    if scope == "site" and site_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id is required when scope='site'.")
    if scope == "organization" and site_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id must be omitted when scope='organization'.")


def _to_read(db: Session, record: IntelligenceDecision) -> IntelligenceDecisionRead:
    site_label = None
    if record.site_id is not None:
        site = db.get(Site, record.site_id)
        site_label = site.name if site is not None else None

    linked_action_read = None
    if record.linked_action_id is not None:
        action = db.get(SafetyAction, record.linked_action_id)
        if action is not None:
            linked_action_read = IntelligenceDecisionActionRead(
                id=action.id, title=action.title, status=action.status.value
            )

    return IntelligenceDecisionRead(
        id=record.id,
        organization_id=record.organization_id,
        site_id=record.site_id,
        site_label=site_label,
        scope=record.scope,
        attention_reference=record.attention_reference,
        attention_category=record.attention_category,
        attention_priority=record.attention_priority,
        attention_title=record.attention_title,
        attention_explanation=record.attention_explanation,
        intelligence_as_of=record.intelligence_as_of,
        intelligence_window_days=record.intelligence_window_days,
        calculation_version=record.calculation_version,
        evidence_source=record.evidence_source,
        evidence_entity_ids=record.evidence_entity_ids or [],
        evidence_event_ids=record.evidence_event_ids or [],
        decision=record.decision,
        rationale=record.rationale,
        linked_action_id=record.linked_action_id,
        linked_action=linked_action_read,
        decided_by_user_id=record.decided_by_user_id,
        decided_by_api_client_id=record.decided_by_api_client_id,
        decided_at=record.decided_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post(
    "/decisions",
    response_model=IntelligenceDecisionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_intelligence_decision(
    body: IntelligenceDecisionCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> IntelligenceDecisionRead:
    """Records one human decision about one attention item. Read-only
    against every other domain: the one write this route performs is
    the new `IntelligenceDecision` row itself (plus, only when the
    human explicitly supplies `linked_action_id`, a *reference* to an
    already-existing `SafetyAction` — never a mutation of that row, and
    never a new one created here)."""
    _validate_scope(body.scope, body.site_id)
    _validate_window_days(body.window_days)
    if body.site_id is not None:
        validate_site_reference(db, organization_id=organization_id, site_id=body.site_id)

    linked_action_id: uuid.UUID | None = None
    if body.linked_action_id is not None:
        linked_action = resolve_action_reference(db, organization_id=organization_id, action_id=body.linked_action_id)
        linked_action_id = linked_action.id

    # Re-derive "what SIE said" server-side, from the exact historical
    # as_of the human was viewing -- never trust category/priority/
    # title/evidence supplied by the client. See
    # resolve_attention_item()'s own docstring for the full trust-
    # boundary rationale.
    item = resolve_attention_item(
        db,
        organization_id=organization_id,
        scope=body.scope,
        site_id=body.site_id,
        as_of=body.as_of,
        window_days=body.window_days,
        attention_reference=body.attention_reference,
    )

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
        return IntelligenceDecisionRead.model_validate(lookup.response_body)

    # Everything from here on -- the IntelligenceDecision row, its
    # AuditLog entry, and the IdempotencyKey response -- is one
    # transaction: all of it commits together, once, or none of it
    # persists. Mirrors app.services.safety_action_service's own
    # action_mutation_transaction() shape exactly.
    with decision_mutation_transaction(db):
        record = record_decision(
            db,
            organization_id=organization_id,
            item=item,
            decision=body.decision,
            rationale=body.rationale,
            linked_action_id=linked_action_id,
            decided_by_user_id=context.user_id,
            decided_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_service.log(
            db,
            action=AuditAction.INTELLIGENCE_DECISION_RECORDED,
            resource_type="IntelligenceDecision",
            resource_id=record.id,
            organization_id=organization_id,
            user_id=context.user_id,
            metadata={
                "decision": record.decision.value,
                "attention_category": record.attention_category,
                "attention_priority": record.attention_priority,
                "attention_reference": record.attention_reference,
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
    "/decisions",
    response_model=IntelligenceDecisionListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_intelligence_decisions(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    site_id: uuid.UUID | None = Query(default=None),
    attention_category: str | None = Query(default=None),
    attention_reference: str | None = Query(
        default=None, description="Filter to every decision recorded about one specific signal -- the append-only decision history for it, newest first."
    ),
    decision: IntelligenceDecisionType | None = Query(default=None),
    linked_action_id: uuid.UUID | None = Query(
        default=None, description="Reverse lookup: which intelligence decision(s) named this SafetyAction."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceDecisionListRead:
    """No decision is ever mutated after creation (see
    `IntelligenceDecision`'s own "immutable" docstring section) -- when
    multiple decisions share one `attention_reference`, this list,
    ordered newest-first, *is* that signal's decision history."""
    conditions = [IntelligenceDecision.organization_id == organization_id]
    if site_id:
        conditions.append(IntelligenceDecision.site_id == site_id)
    if attention_category:
        conditions.append(IntelligenceDecision.attention_category == attention_category)
    if attention_reference:
        conditions.append(IntelligenceDecision.attention_reference == attention_reference)
    if decision:
        conditions.append(IntelligenceDecision.decision == decision)
    if linked_action_id:
        conditions.append(IntelligenceDecision.linked_action_id == linked_action_id)

    total = db.execute(select(func.count()).select_from(IntelligenceDecision).where(*conditions)).scalar_one()
    rows = (
        db.execute(
            select(IntelligenceDecision)
            .where(*conditions)
            .order_by(IntelligenceDecision.decided_at.desc(), IntelligenceDecision.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return IntelligenceDecisionListRead(
        items=[_to_read(db, r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/decisions/{decision_id}",
    response_model=IntelligenceDecisionRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_intelligence_decision(
    decision_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceDecisionRead:
    """A decision from a different organization (or a nonexistent id) is
    a 404, never a 403 -- mirrors every other single-resource GET in
    this codebase's own "never reveal whether a given id exists in
    someone else's tenant" rule."""
    record = db.execute(
        select(IntelligenceDecision).where(
            IntelligenceDecision.id == decision_id, IntelligenceDecision.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found in this organization.")
    return _to_read(db, record)


__all__ = ["router"]
