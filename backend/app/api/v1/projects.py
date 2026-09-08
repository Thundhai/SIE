"""Project & Project/Site Relationship API — SIE Milestone 35:
Organizational & Operational Scope Foundation v0.1; extended by SIE
Milestone 35A: Canonical Project Attribution Correction.

    POST   /projects                          create a project
    GET    /projects                          list projects (paginated)
    GET    /projects/{project_id}             retrieve one project
    POST   /projects/{project_id}/sites       link a site to a project
    GET    /projects/{project_id}/sites       list a project's sites
    DELETE /projects/{project_id}/sites/{site_id}   unlink a site
    GET    /projects/by-site/{site_id}        reverse lookup: a site's projects
    PUT    /projects/{project_id}/events/{event_id}     attribute an event (M35A)
    DELETE /projects/{project_id}/events/{event_id}     clear attribution (M35A)
    GET    /projects/{project_id}/events                list attributed events (M35A)

**Identity and relationships only (item 9's own "provide only the APIs
genuinely required" instruction) — no project-management UI, no task/
schedule/budget endpoints.** This is the complete API surface this
milestone introduces.

**Same authorization shape every other modern route in this codebase
already uses.** `RequestContext`/`require_context_permission()` is the
one auth dependency; `organization_id` is the authorize-then-trust query
parameter. `Permission.PROJECT_READ`/`PROJECT_MANAGE` gate reads/writes
— checked against the existing vocabulary first (see
`app/services/permissions.py`'s own docstring) and granted to the same
roles as their `SITE_READ`/`SITE_MANAGE` counterparts, since `Project`
is an operational-scope entity of the same shape as `Site`.

**Tenant isolation.** Every query filters on `organization_id` first; a
project (or site) id belonging to a different organization is
indistinguishable from a nonexistent one — always `404`, never `403`,
mirroring every other tenant-scoped resource in this codebase (see
`app/services/project_service.py::resolve_project_reference()` and
`app/services/project_site_service.py`).

**Event attribution (SIE Milestone 35A) is the fix for M35's own
"site membership ≠ project attribution" gap** — see
`app/services/safety_event_project_service.py`'s own docstring for the
full rationale. `PUT .../events/{event_id}` is idempotent by
construction (it sets the exact target state, `project_id`, not "link
if absent"); `DELETE .../events/{event_id}` clears it back to `NULL`
(unattributed), also idempotently. Both are gated by
`Permission.PROJECT_MANAGE` -- attributing an event to a project is a
project-domain write, mirroring `POST .../sites`'s own gating exactly.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.request_id import get_request_id
from app.models.project import Project
from app.models.safety_event import SafetyEvent
from app.schemas.events import EventListRead, SafetyEventSummaryRead
from app.schemas.project import (
    ProjectCreate,
    ProjectListRead,
    ProjectRead,
    ProjectSiteCreate,
    ProjectSiteSummaryRead,
    ProjectSummaryRead,
)
from app.schemas.site import SiteRead
from app.services.audit_service import AuditAction, audit_service
from app.services.project_service import project_service, resolve_project_reference
from app.services.project_site_service import (
    link_project_site,
    list_projects_for_site,
    list_sites_for_project,
    unlink_project_site,
)
from app.services.permissions import Permission
from app.services.safety_event_project_service import attribute_event_to_project, clear_event_project_attribution

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_event_summary_read(event: SafetyEvent) -> SafetyEventSummaryRead:
    """Duplicated locally rather than imported from
    `app/api/v1/events.py`'s own (private) `_to_summary_read()` --
    mirrors this codebase's own established "small, route-layer
    converters stay self-contained per file" convention (see
    `app/api/v1/intelligence_decisions.py`'s own `_validate_window_days()`
    docstring for the identical precedent this follows)."""
    return SafetyEventSummaryRead(
        id=event.id,
        event_time=event.event_time,
        event_type=event.event_type,
        event_subtype=event.event_subtype,
        site_id=event.site_id,
        site_name=event.site.name if event.site is not None else None,
        status=event.status,
        severity=event.severity,
        source_system=event.source_system,
        source_record_id=event.source_record_id,
        data_quality_status=event.data_quality_status,
        attributed_project_id=event.attributed_project_id,
    )


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_project(
    body: ProjectCreate,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> Project:
    project = project_service.create(db, organization_id=organization_id, obj_in=body)
    audit_service.log(
        db,
        action=AuditAction.PROJECT_CREATED,
        resource_type="Project",
        resource_id=project.id,
        organization_id=organization_id,
        user_id=context.user_id,
        metadata={"name": project.name, "status": project.status.value},
        request_id=request_id,
    )
    return project


@router.get("", response_model=ProjectListRead, dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def list_projects(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_READ)),
    db: Session = Depends(get_db),
) -> ProjectListRead:
    total = db.execute(
        select(func.count()).select_from(Project).where(Project.organization_id == organization_id)
    ).scalar_one()
    rows = project_service.list(db, organization_id=organization_id, skip=(page - 1) * page_size, limit=page_size)
    return ProjectListRead(items=list(rows), total=total, page=page, page_size=page_size)


@router.get(
    "/by-site/{site_id}",
    response_model=list[ProjectSummaryRead],
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_projects_by_site(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_READ)),
    db: Session = Depends(get_db),
) -> list[Project]:
    """Reverse lookup: every project (in this organization) currently
    associated with `site_id`. A site from a different organization is
    404, never a 403."""
    return list_projects_for_site(db, organization_id=organization_id, site_id=site_id)


@router.get(
    "/{project_id}", response_model=ProjectRead, dependencies=[Depends(require_rate_limit(RateLimitClass.READ))]
)
def get_project(
    project_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_READ)),
    db: Session = Depends(get_db),
) -> Project:
    return resolve_project_reference(db, organization_id=organization_id, project_id=project_id)


@router.post(
    "/{project_id}/sites",
    response_model=ProjectSiteSummaryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def link_site_to_project(
    project_id: uuid.UUID,
    body: ProjectSiteCreate,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> SiteRead:
    """Links `body.site_id` to `project_id`. Both must already belong to
    `organization_id` (404 otherwise) — a project belonging to
    Organization A can never be attached to a site belonging to
    Organization B (item 4's own explicit requirement). Idempotent:
    linking an already-linked pair returns the existing relationship,
    never a duplicate row or an error."""
    link, created = link_project_site(
        db,
        organization_id=organization_id,
        project_id=project_id,
        site_id=body.site_id,
        created_by_user_id=context.user_id,
        created_by_api_client_id=context.api_client_id,
    )
    if created:
        db.commit()
        audit_service.log(
            db,
            action=AuditAction.PROJECT_SITE_LINKED,
            resource_type="ProjectSite",
            resource_id=link.id,
            organization_id=organization_id,
            user_id=context.user_id,
            metadata={"project_id": str(project_id), "site_id": str(body.site_id)},
            request_id=request_id,
        )
    return link.site


@router.get(
    "/{project_id}/sites",
    response_model=list[ProjectSiteSummaryRead],
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_project_sites(
    project_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_READ)),
    db: Session = Depends(get_db),
):
    return list_sites_for_project(db, organization_id=organization_id, project_id=project_id)


@router.delete(
    "/{project_id}/sites/{site_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def unlink_site_from_project(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> Response:
    removed = unlink_project_site(db, organization_id=organization_id, project_id=project_id, site_id=site_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This project is not currently linked to that site."
        )
    db.commit()
    audit_service.log(
        db,
        action=AuditAction.PROJECT_SITE_UNLINKED,
        resource_type="ProjectSite",
        resource_id=project_id,
        organization_id=organization_id,
        user_id=context.user_id,
        metadata={"project_id": str(project_id), "site_id": str(site_id)},
        request_id=request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{project_id}/events/{event_id}",
    response_model=SafetyEventSummaryRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def attribute_event_to_project_route(
    project_id: uuid.UUID,
    event_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> SafetyEventSummaryRead:
    """SIE Milestone 35A: explicitly attributes `event_id` to
    `project_id` -- never inferred from `ProjectSite`/`site_id`. When
    the event has a `site_id`, `project_id` must currently be
    associated with that site (`422` otherwise) -- see
    `app/services/safety_event_project_service.py`'s own docstring for
    the full validation rule. Re-attributing an already-attributed
    event to a different project is a correction, not an error."""
    event = attribute_event_to_project(db, organization_id=organization_id, event_id=event_id, project_id=project_id)
    db.commit()
    audit_service.log(
        db,
        action=AuditAction.SAFETY_EVENT_PROJECT_ATTRIBUTED,
        resource_type="SafetyEvent",
        resource_id=event.id,
        organization_id=organization_id,
        user_id=context.user_id,
        metadata={"event_id": str(event.id), "project_id": str(project_id)},
        request_id=request_id,
    )
    return _to_event_summary_read(event)


@router.delete(
    "/{project_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def clear_event_project_attribution_route(
    project_id: uuid.UUID,
    event_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> Response:
    """Clears `event_id`'s project attribution back to `NULL`
    (unattributed) -- idempotent, never an error even if it was already
    unattributed or attributed to a different project than
    `project_id`. `project_id` itself is not otherwise used here beyond
    being a required, tenant-validated path segment, mirroring
    `DELETE .../sites/{site_id}`'s own shape."""
    resolve_project_reference(db, organization_id=organization_id, project_id=project_id)
    event = clear_event_project_attribution(db, organization_id=organization_id, event_id=event_id)
    db.commit()
    audit_service.log(
        db,
        action=AuditAction.SAFETY_EVENT_PROJECT_ATTRIBUTION_CLEARED,
        resource_type="SafetyEvent",
        resource_id=event.id,
        organization_id=organization_id,
        user_id=context.user_id,
        metadata={"event_id": str(event.id), "project_id": str(project_id)},
        request_id=request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project_id}/events",
    response_model=EventListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_project_events(
    project_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    context: RequestContext = Depends(require_context_permission(Permission.PROJECT_READ)),
    db: Session = Depends(get_db),
) -> EventListRead:
    """Every `SafetyEvent` explicitly attributed to `project_id`
    (`SafetyEvent.attributed_project_id` -- never a `site_id`/
    `ProjectSite` guess). Ordered newest-first, mirroring
    `GET /events`'s own determinism guarantee."""
    resolve_project_reference(db, organization_id=organization_id, project_id=project_id)
    conditions = [SafetyEvent.organization_id == organization_id, SafetyEvent.attributed_project_id == project_id]
    total = db.execute(select(func.count()).select_from(SafetyEvent).where(*conditions)).scalar_one()
    rows = (
        db.execute(
            select(SafetyEvent)
            .where(*conditions)
            .options(joinedload(SafetyEvent.site))
            .order_by(SafetyEvent.event_time.desc(), SafetyEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return EventListRead(
        items=[_to_event_summary_read(e) for e in rows], total=total, page=page, page_size=page_size
    )


__all__ = ["router"]
