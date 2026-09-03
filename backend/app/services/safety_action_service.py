"""Actions / Intervention domain service — SIE Milestone 17: Actions &
Intervention Foundation v0.1. The one place `app/api/v1/actions.py`
delegates tenant-safe reference validation, history recording, and its
own mutation transaction boundary to, so that logic exists once, not
once per route.

**Why both `SafetyActionHistory` and `AuditLog`.** They answer different
questions. `SafetyActionHistory` (`app/models/safety_action_history.py`)
is the domain-scoped "what happened to *this action*" trail a client
would render on an action's own detail view — one row per material
change, immutable, tenant-scoped, queryable by `action_id`. `AuditLog`
(`app/services/audit_service.py`) is the platform-wide security/
administrative log every other milestone already writes to, organized
by actor/organization/request rather than by resource. Both are written
in the same call, from the same data, by `record_history()` and
`audit_action_event()` below — this is the same "one write path"
judgment call `app/api/v1/intelligence.py` already makes for its own
domain events, applied here to two sinks instead of one.

**Tenant-safe reference validation (§7-9 of the milestone spec).**
`validate_site_reference()`/`validate_source_event_reference()`/
`validate_owner_reference()` each raise the *same* `404` whether the
referenced id does not exist at all or belongs to a different
organization — never a `403` or any other signal that would disclose a
foreign record's existence (the exact "Event ID isolation" pattern
`app/api/v1/events.py` already established, applied to three more
reference kinds here).

**Transaction boundary (SIE Milestone 17 corrective patch).** The
original implementation committed the `SafetyAction` row, its
`SafetyActionHistory` entry, its `AuditLog` entry, and (for
`POST /actions`) the replayable `IdempotencyKey` response separately —
four independent `db.commit()` calls per mutation. That left real
failure windows: an exception between commits could leave a
`SafetyAction` persisted with no matching history/audit row, or a
successfully-created action whose `Idempotency-Key` was never stored,
so a client retry after a transient failure could create a second
action.

`action_mutation_transaction()` below is the fix: every
`SafetyAction` mutation (`POST /actions`, `PATCH /actions/{id}`,
`POST /actions/{id}/status` — see `app/api/v1/actions.py`) now wraps
its entire body in this one context manager. Every write inside it —
`db.add(action)`/attribute mutation, `record_history(..., commit=False)`,
`audit_action_event(..., commit=False)`, and (create only)
`store_response(..., commit=False)` — only `flush()`es, never commits
independently; `action_mutation_transaction()` issues exactly one
`db.commit()` when the block finishes without error, or one explicit
`db.rollback()` (before re-raising) if anything inside it raises. So
either the action mutation, its history, its audit entry, and its
idempotency record all persist together, or none of them do — there is
no longer a state where a client can observe (or a retry can be
confused by) a partially-written mutation.

This intentionally does **not** change `AuditService.log()`'s or
`store_response()`'s default behavior for any of their other,
non-Actions call sites (`commit` defaults to `True` in both) — see each
function's own docstring.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.safety_action import SafetyAction
from app.models.safety_action_history import ActionHistoryChangeType, SafetyActionHistory
from app.models.safety_event import SafetyEvent
from app.models.site import Site
from app.services.audit_service import AuditAction, audit_service
from app.services.membership_service import membership_service


@contextmanager
def action_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one `SafetyAction` mutation
    -- see this module's own "Transaction boundary" docstring section
    for the full rationale. Every write performed inside this block
    must pass `commit=False` (or, for the `SafetyAction` row itself,
    simply be `db.add()`ed/mutated and left to this block's own
    `db.flush()`/`db.commit()`) so nothing inside commits on its own.

    On success, commits once. On any exception, rolls back once (so no
    partial write from this block is left pending) and re-raises
    unchanged -- this function never swallows or replaces an error, it
    only controls when the underlying database transaction ends."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def validate_site_reference(db: Session, *, organization_id: uuid.UUID, site_id: uuid.UUID) -> None:
    site = db.execute(
        select(Site).where(Site.id == site_id, Site.organization_id == organization_id)
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site_id not found in this organization.")


def validate_source_event_reference(db: Session, *, organization_id: uuid.UUID, source_event_id: uuid.UUID) -> None:
    event = db.execute(
        select(SafetyEvent).where(SafetyEvent.id == source_event_id, SafetyEvent.organization_id == organization_id)
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="source_event_id not found in this organization."
        )


def validate_owner_reference(db: Session, *, organization_id: uuid.UUID, owner_user_id: uuid.UUID) -> None:
    """An owner must be an *active* member of the same organization —
    reuses `membership_service.get_active_membership()`, the exact check
    `authorization_service.py`/`tenant_context.py` already rely on, so
    "assignable" here means the same thing "authorized" means elsewhere
    in this codebase, not a second, looser definition."""
    membership = membership_service.get_active_membership(db, user_id=owner_user_id, organization_id=organization_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="owner_user_id not found in this organization."
        )


def record_history(
    db: Session,
    *,
    action: SafetyAction,
    change_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    changed_by_user_id: uuid.UUID | None,
    changed_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
    comment: str | None = None,
    commit: bool = True,
) -> SafetyActionHistory:
    """`commit=False` (used by every `app/api/v1/actions.py` call site
    as of the Milestone 17 corrective patch — see this module's own
    "Transaction boundary" docstring section) only `db.add()`s and
    `db.flush()`s the row, leaving the enclosing
    `action_mutation_transaction()` block to commit it together with
    the `SafetyAction` mutation and `AuditLog` entry it belongs with."""
    entry = SafetyActionHistory(
        organization_id=action.organization_id,
        action_id=action.id,
        change_type=change_type,
        from_status=from_status,
        to_status=to_status,
        changed_by_user_id=changed_by_user_id,
        changed_by_api_client_id=changed_by_api_client_id,
        request_id=request_id,
        comment=comment,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()
    return entry


def audit_action_event(
    db: Session,
    *,
    action_name: str,
    action: SafetyAction,
    user_id: uuid.UUID | None,
    caller_kind: str,
    metadata: dict,
    commit: bool = True,
) -> None:
    """Thin wrapper over `audit_service.log()` — see this module's own
    "Transaction boundary" docstring section for what `commit=False`
    means here (identical to `record_history()` above: only
    `db.add()`/`db.flush()`, no independent commit)."""
    audit_service.log(
        db,
        action=action_name,
        resource_type="SafetyAction",
        resource_id=action.id,
        organization_id=action.organization_id,
        user_id=user_id,
        metadata={**metadata, "caller_kind": caller_kind},
        commit=commit,
    )


# The exact set of SafetyActionUpdate fields PATCH may change -- kept
# here (not re-derived from the schema) so this module has one visible
# list to audit against the milestone's own "forbidden fields" rule.
_PATCHABLE_FIELDS = frozenset(
    {"title", "description", "action_type", "priority", "owner_user_id", "site_id", "due_date", "external_reference", "attributes"}
)


def apply_update(action: SafetyAction, payload) -> tuple[set[str], bool]:
    """Applies only the fields the caller actually supplied
    (`model_fields_set` — a field omitted from the request body is left
    untouched; a field explicitly sent as `null` clears it, valid for
    every nullable field here). Returns `(changed_fields, owner_changed)`
    so the caller can decide the right history `change_type` and
    whether `SAFETY_ACTIONS_ASSIGN` was required."""
    supplied = payload.model_fields_set & _PATCHABLE_FIELDS
    changed: set[str] = set()
    owner_changed = False
    for field in supplied:
        new_value = getattr(payload, field)
        if getattr(action, field) != new_value:
            setattr(action, field, new_value)
            changed.add(field)
            if field == "owner_user_id":
                owner_changed = True
    return changed, owner_changed


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "action_mutation_transaction",
    "validate_site_reference",
    "validate_source_event_reference",
    "validate_owner_reference",
    "record_history",
    "audit_action_event",
    "apply_update",
    "utcnow",
    "ActionHistoryChangeType",
    "AuditAction",
]
