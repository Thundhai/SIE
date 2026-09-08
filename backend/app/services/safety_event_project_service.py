"""SafetyEvent <-> Project attribution service — SIE Milestone 35A:
Canonical Project Attribution Correction. The one write path for
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

**No automatic reconciliation.** If a site is later unlinked from a
project (`DELETE /projects/{project_id}/sites/{site_id}`), any event
already attributed to that project keeps its attribution — the
attribution was a fact established at a specific time
(`SafetyEvent.updated_at` records when), not a live view recomputed
from `ProjectSite`'s current state. This mirrors `ProjectSite`'s own
"no point-in-time reconstruction" limitation (see that model's own
docstring) rather than inventing a second, inconsistent temporal model:
this service does not attempt to reconcile past attributions against
later relationship changes, and does not claim to.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.safety_event import SafetyEvent
from app.services.project_service import resolve_project_reference
from app.services.project_site_service import project_site_ids


def _resolve_owned_event(db: Session, *, organization_id: uuid.UUID, event_id: uuid.UUID) -> SafetyEvent:
    event = db.execute(
        select(SafetyEvent).where(SafetyEvent.id == event_id, SafetyEvent.organization_id == organization_id)
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found in this organization.")
    return event


def attribute_event_to_project(
    db: Session, *, organization_id: uuid.UUID, event_id: uuid.UUID, project_id: uuid.UUID
) -> SafetyEvent:
    """Sets `event.attributed_project_id = project_id`. Both the event
    and the project must belong to `organization_id` (404 otherwise).
    When the event has a `site_id`, `project_id` must currently be
    associated with that site via `ProjectSite`, or this raises `422`
    (see module docstring's "Validation rule"). Re-attributing an
    already-attributed event to a different project is allowed (a
    correction, not blocked) — the previous value is simply overwritten;
    callers that need to know a change occurred should compare the
    returned row's previous state themselves or rely on the audit log
    entry the API layer writes alongside this call."""
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

    event.attributed_project_id = project.id
    db.flush()
    return event


def clear_event_project_attribution(db: Session, *, organization_id: uuid.UUID, event_id: uuid.UUID) -> SafetyEvent:
    """Sets `event.attributed_project_id = NULL` -- returns the event to
    its default, fully-valid "unattributed" state. Never an error, even
    if it was already `NULL` (idempotent)."""
    event = _resolve_owned_event(db, organization_id=organization_id, event_id=event_id)
    event.attributed_project_id = None
    db.flush()
    return event


__all__ = ["attribute_event_to_project", "clear_event_project_attribution"]
