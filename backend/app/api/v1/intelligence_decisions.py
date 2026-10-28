"""Intelligence Decisions API — SIE Milestone 34.

**Updated by Roadmap Phase 1 (Decisions wiring).** The service this
router delegates to now lives behind `app.integrations.commercial_core`
(Thundhai/SIE-Commercial-Core's `cc_service` → `domain_service`
boundary) — the same seam Attention/Analytics/Enterprise Intelligence
already use, following M43-IP-03's own "no fake extraction" rule. Create/
list/get are wired; `memory-context` remains a 501 stub (Organizational
Memory's own contract DTO is still `REVIEW_REQUIRED` — Roadmap Phase 2).

**Response shape is narrower than the pre-extraction route's.**
`IntelligenceDecisionRead` (`app/schemas/intelligence_decision.py`)
mirrors `sie_contract.DecisionReferenceDTO` field-for-field: no
`calculation_version`, `evidence_*`, `linked_action`/`site_label` join,
or `created_at`/`updated_at`. A caller that needs the linked
`SafetyAction`'s own title/status already holds `linked_action_id`
(it supplied it) and resolves it via the existing `GET /actions/{id}`
route.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session
from sie_contract import ActorType

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission, resolve_authorized_organization_id
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.errors import ApiError, ErrorCode
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.integrations.commercial_core import (
    CommercialCoreIntegrationError,
    CommercialCoreNotFoundError,
    CommercialCoreTenantNotEntitledError,
    CommercialCoreUnavailable,
    CommercialCoreValidationError,
    commercial_core_client,
    get_commercial_core_client,
    tenant_not_entitled_error,
)
from app.integrations.tenant_assertion import tenant_actor_from_context
from app.models.intelligence_decision_enums import IntelligenceDecisionType
from app.schemas.intelligence_decision import (
    IntelligenceDecisionCreate,
    IntelligenceDecisionListRead,
    IntelligenceDecisionRead,
)
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["intelligence-decisions"])

_ENDPOINT_CREATE = "POST /intelligence/decisions"


def _actor_from_context(context: RequestContext) -> tuple[ActorType, uuid.UUID]:
    """The decider's own identity, explicitly asserted across the
    Commercial Core boundary -- never derived from anything the
    boundary's own service credential proves (see
    `cc_service/domain_client/decisions.py`'s module docstring on the
    Commercial Core side for why). Mirrors `RequestContext.kind`'s own
    "human or machine, never both" invariant."""
    if context.is_machine:
        return ActorType.MACHINE, context.api_client_id
    return ActorType.HUMAN, context.user_id


def _map_commercial_core_decision_error(exc: CommercialCoreIntegrationError) -> ApiError:
    """Mirrors `app/api/v1/intelligence.py::_map_commercial_core_attention_error()`
    exactly, with one addition: `CommercialCoreNotFoundError` maps to a
    plain 404 `RESOURCE_NOT_FOUND` -- the caller's own request naming an
    unknown `decision_id`/`site_id`/`linked_action_id`/
    `attention_reference`, never a dependency failure, so it must not
    collapse into the generic 503 bucket every other
    `CommercialCoreIntegrationError` subclass maps to. Not being entitled
    (SIE-2) is a 403, as there."""
    if isinstance(exc, CommercialCoreTenantNotEntitledError):
        return tenant_not_entitled_error()
    if isinstance(exc, CommercialCoreNotFoundError):
        return ApiError(status_code=404, code=ErrorCode.RESOURCE_NOT_FOUND, message=str(exc))
    if isinstance(exc, CommercialCoreValidationError):
        return ApiError(status_code=422, code=ErrorCode.VALIDATION_ERROR, message=str(exc))
    return ApiError(status_code=503, code=ErrorCode.MODEL_NOT_AVAILABLE, message=str(exc))


def _to_read(dto) -> IntelligenceDecisionRead:
    return IntelligenceDecisionRead.model_validate(dto, from_attributes=True)


@router.post(
    "/decisions",
    response_model=IntelligenceDecisionRead,
    status_code=201,
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
    org_id = resolve_authorized_organization_id(context, organization_id)
    actor_type, actor_id = _actor_from_context(context)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=org_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return IntelligenceDecisionRead.model_validate(lookup.response_body)

    try:
        client = get_commercial_core_client()
        dto = client.create_decision(
            organization_id=org_id,
            scope=body.scope,
            site_id=body.site_id,
            as_of=body.as_of,
            window_days=body.window_days,
            attention_reference=body.attention_reference,
            decision_type=body.decision.value,
            rationale=body.rationale,
            linked_action_id=body.linked_action_id,
            actor_type=actor_type,
            actor_id=actor_id,
            request_id=request_id,
            tenant_actor=tenant_actor_from_context(context, Permission.INTELLIGENCE_DECISION_WRITE),
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_decision_error(exc) from exc

    result = _to_read(dto)
    store_response(
        db,
        endpoint=_ENDPOINT_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status_code=201,
        response_body=result.model_dump(mode="json"),
        organization_id=org_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
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
    attention_reference: str | None = Query(
        default=None,
        description="Filter to every decision recorded about one specific signal -- the append-only decision history for it, newest first.",
    ),
    decision: IntelligenceDecisionType | None = Query(default=None),
    linked_action_id: uuid.UUID | None = Query(
        default=None, description="Reverse lookup: which intelligence decision(s) named this SafetyAction."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> IntelligenceDecisionListRead:
    org_id = resolve_authorized_organization_id(context, organization_id)
    try:
        client = get_commercial_core_client()
        dto = client.list_decisions(
            organization_id=org_id,
            site_id=site_id,
            attention_reference=attention_reference,
            decision_type=decision.value if decision is not None else None,
            linked_action_id=linked_action_id,
            page=page,
            page_size=page_size,
            request_id=None,
            tenant_actor=tenant_actor_from_context(context, Permission.INTELLIGENCE_READ),
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_decision_error(exc) from exc

    return IntelligenceDecisionListRead(
        items=[_to_read(item) for item in dto.items], total=dto.total, page=dto.page, page_size=dto.page_size
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
    org_id = resolve_authorized_organization_id(context, organization_id)
    try:
        client = get_commercial_core_client()
        dto = client.get_decision(
            organization_id=org_id,
            decision_id=decision_id,
            request_id=None,
            tenant_actor=tenant_actor_from_context(context, Permission.INTELLIGENCE_READ),
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_decision_error(exc) from exc
    return _to_read(dto)


@router.get("/decisions/{decision_id}/memory-context")
def get_intelligence_decision_memory_context(
    decision_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    """Organizational Memory's own contract DTO is still `REVIEW_REQUIRED`
    (Roadmap Phase 2) -- this route stays a 501 stub until that design
    pass lands, same reasoning M43-IP-03 originally gave."""
    raise commercial_core_client.unavailable("Intelligence decision memory context")


__all__ = ["router"]
