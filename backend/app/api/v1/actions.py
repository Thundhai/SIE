"""Actions / Intervention API — SIE Milestone 17: Actions & Intervention
Foundation v0.1.

    Safety Event (optional)
       |
    POST /api/v1/actions | GET .../actions | GET .../{id} | PATCH .../{id}
    | POST .../{id}/status
       |
    RequestContext (app.api.deps_context — human OR machine, unchanged)
       |
    Authorization (authorize_context() -- intervention:*, unchanged logic)
       |
    Tenant-scoped query/write (this module: organization_id is always an
       |                        explicit WHERE clause / column, never
       |                        trusted implicitly from the body)
    SafetyAction / SafetyActionHistory (app.models.safety_action*, new)

**This is the ACTION DOMAIN, not an AI remediation feature.** Nothing in
this module creates, assigns, escalates, closes, or claims completion of
an action on its own — every write here is a deliberate, separately
authorized call made by a human or an already-authorized machine
integration. See `app/models/safety_action.py`'s own "Closure semantics"
docstring section: `COMPLETED` means "an authorized actor marked this
done," never "SIE verified the hazard is gone." There is no
effectiveness-verification, notification, escalation, or workflow-engine
code anywhere in this module (milestone §17-18, §25) — a future
milestone may add human-facing suggestion features on top of this, but
this milestone does not.

**Permission mapping (see app/services/permissions.py's own docstring
for why `INTERVENTION_READ`/`INTERVENTION_MANAGE` are reused rather than
duplicated under a `SAFETY_ACTIONS_*` name):**

  * `SAFETY_ACTIONS_READ`   -> `Permission.INTERVENTION_READ`   (list/get)
  * `SAFETY_ACTIONS_WRITE`  -> `Permission.INTERVENTION_MANAGE` (create,
    PATCH, and any status transition that is *not* into a terminal state)
  * `SAFETY_ACTIONS_ASSIGN` -> `Permission.INTERVENTION_ASSIGN` (setting
    or changing `owner_user_id`, at create or via PATCH -- required in
    *addition* to WRITE, not instead of it)
  * `SAFETY_ACTIONS_CLOSE`  -> `Permission.INTERVENTION_CLOSE` (a status
    transition *into* `COMPLETED` or `CANCELLED` -- required *instead
    of* WRITE for that one call, since closing is its own capability,
    not a subset of general write access)

**Tenant isolation.** Every query below filters on
`SafetyAction.organization_id == organization_id` before anything else,
where `organization_id` is always the value `require_context_permission`/
`authorize_context` already authorized the caller for — never a
path/body-supplied value trusted on its own. `get_action`/PATCH/status
additionally fold `organization_id` into the *same* WHERE clause as
`action_id` — a valid id belonging to a different organization is
indistinguishable from a nonexistent one: always `404`, never a
distinguishing `403` that would leak existence (mirrors
`app/api/v1/events.py`'s own "Event ID isolation" — see
`app/services/safety_action_service.py` for the identical treatment of
`site_id`/`source_event_id`/`owner_user_id` cross-tenant references).

**No history read endpoint in this milestone.** `SafetyActionHistory` is
fully implemented, written on every material change, and tenant-scoped
(see that model's own docstring) — but the milestone's own §11 API list
names exactly five endpoints, none of them a history reader. Exposing
one is left to a future milestone rather than invented here (§25 "do not
over-engineer"); history correctness is verified directly at the
service/database layer in this milestone's own tests instead of over
HTTP.

**Deliberately narrow mutation surface, mirroring
`app/api/v1/data_sources.py`'s own precedent.** Status transitions never
go through `PATCH` — only the dedicated `POST .../status` endpoint can
change `status`/`completed_at`/`cancelled_at`, so the transition matrix
(`app/models/safety_action_enums.py`) has exactly one code path to
enforce, not two.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.api.deps_context import RequestContext, authorize_context, get_request_context, require_context_permission
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.models.safety_action import SafetyAction
from app.models.safety_action_enums import ACTION_TERMINAL_STATUSES, ActionPriority, ActionStatus, ActionType, is_allowed_action_transition
from app.schemas.actions import ActionListRead, SafetyActionCreate, SafetyActionRead, SafetyActionStatusUpdate, SafetyActionUpdate
from app.services.permissions import Permission
from app.services.safety_action_service import (
    ActionHistoryChangeType,
    AuditAction,
    apply_update,
    audit_action_event,
    record_history,
    utcnow,
    validate_owner_reference,
    validate_site_reference,
    validate_source_event_reference,
)

router = APIRouter(prefix="/actions", tags=["actions"])

_SEARCH_MAX_LENGTH = 200
_ENDPOINT_CREATE = "POST /actions"


def _require_permission(db: Session, context: RequestContext, *, organization_id: uuid.UUID, permission: Permission) -> None:
    """The same wrapper `require_context_permission`'s own factory
    applies for the *primary* permission on a route, used here for a
    *secondary* one that depends on the request body (§10's
    SAFETY_ACTIONS_ASSIGN/SAFETY_ACTIONS_CLOSE) -- see
    `app.api.deps_context`'s own docstring, which explicitly sanctions
    calling `get_request_context()`/`authorize_context()` directly for
    exactly this "non-standard permission selection" case."""
    if not authorize_context(db, context, permission=permission, organization_id=organization_id):
        detail = (
            f"API client is not authorized for organization {organization_id} or is missing "
            f"scope {permission.value}."
            if context.is_machine
            else f"Missing {permission.value} permission in the requested organization."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _get_owned_action_or_404(db: Session, *, organization_id: uuid.UUID, action_id: uuid.UUID) -> SafetyAction:
    action = db.execute(
        select(SafetyAction)
        .where(SafetyAction.id == action_id, SafetyAction.organization_id == organization_id)
        .options(joinedload(SafetyAction.site), joinedload(SafetyAction.owner))
    ).scalar_one_or_none()
    if action is None:
        # Deliberately identical whether action_id doesn't exist at all or
        # belongs to a different organization -- see module docstring's
        # own "Tenant isolation" note.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found.")
    return action


def _to_read(action: SafetyAction) -> SafetyActionRead:
    return SafetyActionRead(
        id=action.id,
        organization_id=action.organization_id,
        site_id=action.site_id,
        site_name=action.site.name if action.site is not None else None,
        source_event_id=action.source_event_id,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        priority=action.priority,
        status=action.status,
        owner_user_id=action.owner_user_id,
        owner_name=action.owner.name if action.owner is not None else None,
        due_date=action.due_date,
        created_by_user_id=action.created_by_user_id,
        created_by_api_client_id=action.created_by_api_client_id,
        created_at=action.created_at,
        updated_at=action.updated_at,
        completed_at=action.completed_at,
        cancelled_at=action.cancelled_at,
        external_reference=action.external_reference,
        attributes=action.attributes,
    )


@router.post(
    "",
    response_model=SafetyActionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_action(
    body: SafetyActionCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.INTERVENTION_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> SafetyActionRead:
    if body.owner_user_id is not None:
        _require_permission(db, context, organization_id=organization_id, permission=Permission.INTERVENTION_ASSIGN)

    if body.site_id is not None:
        validate_site_reference(db, organization_id=organization_id, site_id=body.site_id)
    if body.source_event_id is not None:
        validate_source_event_reference(db, organization_id=organization_id, source_event_id=body.source_event_id)
    if body.owner_user_id is not None:
        validate_owner_reference(db, organization_id=organization_id, owner_user_id=body.owner_user_id)

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
        return SafetyActionRead.model_validate(lookup.response_body)

    action = SafetyAction(
        organization_id=organization_id,
        site_id=body.site_id,
        source_event_id=body.source_event_id,
        title=body.title,
        description=body.description,
        action_type=body.action_type,
        priority=body.priority,
        status=ActionStatus.OPEN,
        owner_user_id=body.owner_user_id,
        due_date=body.due_date,
        created_by_user_id=context.user_id,
        created_by_api_client_id=context.api_client_id,
        external_reference=body.external_reference,
        attributes=body.attributes,
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    record_history(
        db,
        action=action,
        change_type=ActionHistoryChangeType.CREATED,
        to_status=action.status.value,
        changed_by_user_id=context.user_id,
        changed_by_api_client_id=context.api_client_id,
        request_id=request_id,
    )
    audit_action_event(
        db,
        action_name=AuditAction.SAFETY_ACTION_CREATED,
        action=action,
        user_id=context.user_id,
        caller_kind=context.kind,
        metadata={"title": action.title, "action_type": action.action_type.value, "priority": action.priority.value},
    )

    result = _to_read(action)
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
    )
    return result


@router.get("", response_model=ActionListRead, dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def list_actions(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    status_: ActionStatus | None = Query(default=None, alias="status"),
    priority: ActionPriority | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    site_id: uuid.UUID | None = Query(default=None),
    source_event_id: uuid.UUID | None = Query(default=None),
    action_type: ActionType | None = Query(default=None),
    due_date_from: datetime | None = Query(default=None, description="Inclusive lower bound on due_date."),
    due_date_to: datetime | None = Query(default=None, description="Inclusive upper bound on due_date."),
    search: str | None = Query(
        default=None, max_length=_SEARCH_MAX_LENGTH, description="Matches title, description, or external_reference."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTERVENTION_READ)),
    db: Session = Depends(get_db),
) -> ActionListRead:
    conditions = [SafetyAction.organization_id == organization_id]
    if status_:
        conditions.append(SafetyAction.status == status_)
    if priority:
        conditions.append(SafetyAction.priority == priority)
    if owner_user_id:
        conditions.append(SafetyAction.owner_user_id == owner_user_id)
    if site_id:
        conditions.append(SafetyAction.site_id == site_id)
    if source_event_id:
        conditions.append(SafetyAction.source_event_id == source_event_id)
    if action_type:
        conditions.append(SafetyAction.action_type == action_type)
    if due_date_from:
        conditions.append(SafetyAction.due_date >= due_date_from)
    if due_date_to:
        conditions.append(SafetyAction.due_date <= due_date_to)
    if search:
        # Parameterized ORM ILIKE -- never raw/interpolated SQL, mirrors
        # app/api/v1/events.py's own search implementation exactly.
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                SafetyAction.title.ilike(pattern),
                SafetyAction.description.ilike(pattern),
                SafetyAction.external_reference.ilike(pattern),
            )
        )

    # Count first, against the same filters, without ever materializing
    # the full matching population.
    total = db.execute(select(func.count()).select_from(SafetyAction).where(*conditions)).scalar_one()

    rows = (
        db.execute(
            select(SafetyAction)
            .where(*conditions)
            .options(joinedload(SafetyAction.site), joinedload(SafetyAction.owner))
            # created_at DESC, id DESC -- id is a stable, always-unique
            # secondary key, so two actions created in the same instant
            # never reorder between identical requests (mirrors
            # app/api/v1/events.py's own determinism note).
            .order_by(SafetyAction.created_at.desc(), SafetyAction.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .scalars()
        .all()
    )

    return ActionListRead(items=[_to_read(a) for a in rows], total=total, page=page, page_size=page_size)


@router.get(
    "/{action_id}", response_model=SafetyActionRead, dependencies=[Depends(require_rate_limit(RateLimitClass.READ))]
)
def get_action(
    action_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTERVENTION_READ)),
    db: Session = Depends(get_db),
) -> SafetyActionRead:
    action = _get_owned_action_or_404(db, organization_id=organization_id, action_id=action_id)
    return _to_read(action)


@router.patch(
    "/{action_id}", response_model=SafetyActionRead, dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))]
)
def update_action(
    action_id: uuid.UUID,
    body: SafetyActionUpdate,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTERVENTION_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> SafetyActionRead:
    action = _get_owned_action_or_404(db, organization_id=organization_id, action_id=action_id)

    if "owner_user_id" in body.model_fields_set:
        _require_permission(db, context, organization_id=organization_id, permission=Permission.INTERVENTION_ASSIGN)
        if body.owner_user_id is not None:
            validate_owner_reference(db, organization_id=organization_id, owner_user_id=body.owner_user_id)
    if "site_id" in body.model_fields_set and body.site_id is not None:
        validate_site_reference(db, organization_id=organization_id, site_id=body.site_id)

    changed_fields, owner_changed = apply_update(action, body)
    if not changed_fields:
        return _to_read(action)

    db.commit()
    db.refresh(action)

    change_type = ActionHistoryChangeType.ASSIGNED if owner_changed else ActionHistoryChangeType.UPDATED
    record_history(
        db,
        action=action,
        change_type=change_type,
        changed_by_user_id=context.user_id,
        changed_by_api_client_id=context.api_client_id,
        request_id=request_id,
        comment=f"Changed fields: {', '.join(sorted(changed_fields))}",
    )
    audit_action_event(
        db,
        action_name=AuditAction.SAFETY_ACTION_ASSIGNED if owner_changed else AuditAction.SAFETY_ACTION_UPDATED,
        action=action,
        user_id=context.user_id,
        caller_kind=context.kind,
        metadata={"changed_fields": sorted(changed_fields)},
    )
    return _to_read(action)


@router.post(
    "/{action_id}/status",
    response_model=SafetyActionRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def update_action_status(
    action_id: uuid.UUID,
    body: SafetyActionStatusUpdate,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(get_request_context),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> SafetyActionRead:
    # Which permission applies depends on the *target* status (see module
    # docstring's permission-mapping table) -- this is exactly the "call
    # get_request_context()/authorize_context() directly" case
    # app.api.deps_context's own docstring describes, so
    # require_context_permission (one fixed permission) doesn't fit here.
    required_permission = (
        Permission.INTERVENTION_CLOSE if body.status in ACTION_TERMINAL_STATUSES else Permission.INTERVENTION_MANAGE
    )
    _require_permission(db, context, organization_id=organization_id, permission=required_permission)

    action = _get_owned_action_or_404(db, organization_id=organization_id, action_id=action_id)

    if not is_allowed_action_transition(action.status.value, body.status.value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot transition action from {action.status.value} to {body.status.value}.",
        )

    previous_status = action.status
    action.status = body.status
    # completed_at/cancelled_at are set here, and only here -- never
    # accepted as client input (see app/schemas/actions.py's own
    # docstring and app/models/safety_action.py's "Closure semantics").
    if body.status == ActionStatus.COMPLETED:
        action.completed_at = utcnow()
    elif body.status == ActionStatus.CANCELLED:
        action.cancelled_at = utcnow()
    db.commit()
    db.refresh(action)

    record_history(
        db,
        action=action,
        change_type=ActionHistoryChangeType.STATUS_CHANGED,
        from_status=previous_status.value,
        to_status=action.status.value,
        changed_by_user_id=context.user_id,
        changed_by_api_client_id=context.api_client_id,
        request_id=request_id,
        comment=body.comment,
    )
    audit_action_event(
        db,
        action_name=AuditAction.SAFETY_ACTION_STATUS_CHANGED,
        action=action,
        user_id=context.user_id,
        caller_kind=context.kind,
        metadata={"from_status": previous_status.value, "to_status": action.status.value},
    )
    return _to_read(action)


__all__ = ["router"]
