"""SafetyEvent <-> Project attribution service — SIE Milestone 35A:
Canonical Project Attribution Correction; corrected by SIE Milestone
35B: Project Attribution Temporal Integrity. The one write path for
`SafetyEvent.attributed_project_id` — mirrors
`app/services/project_site_service.py::link_project_site()`'s own
"resolve both ends scoped to the caller's authorized organization_id
before writing anything" shape, applied to a single nullable column
instead of a join table.

**Why this must be an explicit act, never inferred.** `ProjectSite`
only ever proves "this project operates at this site" — never "this
specific event belongs to this project," which becomes genuinely
ambiguous the moment a site hosts more than one project (SIE Milestone
35 explicitly allows exactly that). This service is where the
distinction is enforced in code: nothing here ever reads `ProjectSite`
to *guess* an event's project; the only way `attributed_project_id` is
ever set is a caller stating it explicitly, through
`attribute_event_to_project()`.

**Validation rule (M35A's own explicit requirement).** When the event
has a `site_id`, the project being attributed must currently be
associated with that site (via `ProjectSite`) — attributing "Project
Beta" to an event that occurred at a site only "Project Alpha" operates
at is rejected (422), not silently accepted. No historical/ingestion
exception exists in this correction: the check is unconditional. When
the event has no `site_id` at all, there is nothing to cross-check, and
any project belonging to the same organization may be attributed.

**Every genuine state transition writes a `SafetyEventProjectAttributionHistory`
row (SIE Milestone 35B).** `SafetyEvent.attributed_project_id` remains
the fast, current-state column every non-temporal read uses (event
detail, `GET /projects/{id}/events`, the `DELETE` target-match check
below), but it alone cannot answer "was this event Project Alpha's as
of an earlier instant" once the event has ever been re-attributed or
cleared — see `app/models/safety_event_project_attribution_history.py`'s
own docstring for the full rationale and
`app/intelligence/temporal.py::events_as_of()` for the point-in-time
reconstruction this history now makes possible. A history row is
written only on an actual transition: re-attributing an event to the
project it is already attributed to, or clearing an event that is
already unattributed, is a true no-op — no redundant row, no history
noise (mirrors `ProjectSite`'s own "linking an already-linked pair is a
no-op" idempotency precedent).

**No automatic reconciliation.** If a site is later unlinked from a
project (`DELETE /projects/{project_id}/sites/{site_id}`), any event
already attributed to that project keeps its attribution — the
attribution was a fact established at a specific time (this history
table's own `created_at` records exactly when), not a live view
recomputed from `ProjectSite`'s current state. This mirrors
`ProjectSite`'s own "no point-in-time reconstruction" limitation (see
that model's own docstring) rather than inventing a second,
inconsistent temporal model: this service does not attempt to
reconcile past attributions against later relationship changes, and
does not claim to.

**`clear_event_project_attribution()` now requires the target project
to match the event's current attribution (SIE Milestone 35B's own
correctness fix).** M35A's version accepted any tenant-owned
`project_id` in the URL and cleared whatever was currently attributed,
regardless of whether it matched — `DELETE
/projects/{beta_id}/events/{event_id}` would silently clear an
attribution to Alpha. That is no longer accepted: the caller's
`project_id` must equal `event.attributed_project_id` at the moment of
the call, or this raises `404` (mirrors `unlink_project_site()`'s own
"not currently associated" 404, not a new status-code convention).
Calling it on an already-unattributed event is likewise `404` (there is
no attribution for any `project_id` to match) — this is a deliberate,
documented narrowing from M35A's own "always idempotent, never an
error" framing; see `docs/OPERATIONAL_SCOPE_FOUNDATION_V0_1.md` §10.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.safety_event import SafetyEvent
from app.models.safety_event_project_attribution_history import (
    SafetyEventProjectAttributionAction,
    SafetyEventProjectAttributionHistory,
)
from app.services.project_service import resolve_project_reference
from app.services.project_site_service import project_site_ids


def _resolve_owned_event(db: Session, *, organization_id: uuid.UUID, event_id: uuid.UUID) -> SafetyEvent:
    event = db.execute(
        select(SafetyEvent).where(SafetyEvent.id == event_id, SafetyEvent.organization_id == organization_id)
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found in this organization.")
    return event


def _record_history(
    db: Session,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    project_id: uuid.UUID,
    action: str,
    changed_by_user_id: uuid.UUID | None,
    changed_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> None:
    db.add(
        SafetyEventProjectAttributionHistory(
            organization_id=organization_id,
            event_id=event_id,
            project_id=project_id,
            action=action,
            changed_by_user_id=changed_by_user_id,
            changed_by_api_client_id=changed_by_api_client_id,
            request_id=request_id,
        )
    )


def attribute_event_to_project(
    db: Session,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    project_id: uuid.UUID,
    changed_by_user_id: uuid.UUID | None = None,
    changed_by_api_client_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> tuple[SafetyEvent, bool]:
    """Sets `event.attributed_project_id = project_id`. Both the event
    and the project must belong to `organization_id` (404 otherwise).
    When the event has a `site_id`, `project_id` must currently be
    associated with that site via `ProjectSite`, or this raises `422`
    (see module docstring's "Validation rule"). Re-attributing an
    already-attributed event to a different project is allowed (a
    correction, not blocked) — the previous value is simply overwritten.
    Calling this with the project the event is already attributed to is
    a true no-op: no history row, `event.updated_at` untouched.
    `changed_by_user_id`/`changed_by_api_client_id`/`request_id` are
    recorded on the `SafetyEventProjectAttributionHistory` row this
    writes on an actual transition (SIE Milestone 35B) — the same
    actor/request-id convention `link_project_site()` already
    established, threaded here for exactly the same reason.

    Returns `(event, changed)` — `changed` mirrors `link_project_site()`'s
    own `(link, created)` return-tuple precedent, so the caller (the API
    route) knows whether to write an audit log entry: a true no-op wrote
    nothing worth auditing."""
    event = _resolve_owned_event(db, organization_id=organization_id, event_id=event_id)
    project = resolve_project_reference(db, organization_id=organization_id, project_id=project_id)

    if event.site_id is not None:
        current_site_ids = project_site_ids(db, organization_id=organization_id, project_id=project.id)
        if event.site_id not in current_site_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Project {project.id} is not currently associated with site {event.site_id}, "
                    "which this event occurred at. Link the project to the site first "
                    "(POST /api/v1/projects/{project_id}/sites), or attribute a different project."
                ),
            )

    if event.attributed_project_id == project.id:
        return event, False

    event.attributed_project_id = project.id
    _record_history(
        db,
        organization_id=organization_id,
        event_id=event.id,
        project_id=project.id,
        action=SafetyEventProjectAttributionAction.ATTRIBUTED,
        changed_by_user_id=changed_by_user_id,
        changed_by_api_client_id=changed_by_api_client_id,
        request_id=request_id,
    )
    db.flush()
    return event, True


def clear_event_project_attribution(
    db: Session,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    project_id: uuid.UUID,
    changed_by_user_id: uuid.UUID | None = None,
    changed_by_api_client_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> SafetyEvent:
    """Sets `event.attributed_project_id = NULL` -- returns the event to
    its default, fully-valid "unattributed" state. `project_id` (SIE
    Milestone 35B) must equal `event.attributed_project_id` at the
    moment of the call, or this raises `404` -- see module docstring's
    own "now requires the target project to match" section for why this
    is no longer unconditionally idempotent the way SIE Milestone 35A
    first built it."""
    event = _resolve_owned_event(db, organization_id=organization_id, event_id=event_id)
    if event.attributed_project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event.id} is not currently attributed to project {project_id}.",
        )

    _record_history(
        db,
        organization_id=organization_id,
        event_id=event.id,
        project_id=project_id,
        action=SafetyEventProjectAttributionAction.CLEARED,
        changed_by_user_id=changed_by_user_id,
        changed_by_api_client_id=changed_by_api_client_id,
        request_id=request_id,
    )
    event.attributed_project_id = None
    db.flush()
    return event


__all__ = ["attribute_event_to_project", "clear_event_project_attribution"]
