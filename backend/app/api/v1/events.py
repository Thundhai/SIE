"""Human-facing Events read API — SIE Enterprise Read API & Browser
Integration Foundation v0.1.

    Browser
       |
    Frontend API client (src/services/api/client.ts)
       |
    GET /api/v1/events | GET /api/v1/events/{id}
       |
    RequestContext (app.api.deps_context — human OR machine, unchanged)
       |
    Authorization (authorize_context() -- SAFETY_DATA_READ, unchanged)
       |
    Tenant-scoped query (this module: organization_id is always an
       |                  explicit WHERE clause, never trusted implicitly)
    SafetyEvent (app.models.safety_event — unchanged, no second event model)

**Why `SAFETY_DATA_READ`, not a new permission.** This is the read half
of the exact same capability `app/api/v1/intelligence.py`'s
`POST /intelligence/events`/`POST /data/ingestion` already write under
`SAFETY_DATA_WRITE` — reading the canonical safety-event population an
organization already owns is `safety_data:read`, already granted to
every `OrganizationRole` including `VIEWER` (see
`app/services/permissions.py::ROLE_PERMISSIONS`). No new permission was
introduced for this milestone.

**Tenant isolation.** Every query below filters on
`SafetyEvent.organization_id == organization_id` *before* anything else
— never relies on the frontend, never trusts a path/body-supplied
organization_id without `require_context_permission()` first confirming
the caller (human or machine) is actually authorized for it (see
`app.api.deps_context`'s own docstring for the machine-organization-
pinning rule this reuses unchanged). `get_event` additionally folds
`organization_id` into the *same* WHERE clause as `event_id` — a valid
id belonging to a different organization is indistinguishable from a
nonexistent one: both 404, never a distinguishing 403 that would leak
existence (§17 "Event ID isolation").

**Determinism.** Every list response is ordered
`event_time DESC, id DESC` — `id` is a stable, always-unique secondary
key, so two events sharing the same `event_time` (not uncommon for
batch-ingested data) never reorder between identical requests.

**No second event model, no fabricated relationships.** Response
shapes are `app/schemas/events.py`, built directly from the real
`SafetyEvent`/`Site`/`DataSource` columns — see that module's own
docstring for why evidence/knowledge/related-record fields are
deliberately absent rather than invented.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.models.data_source import DataSource
from app.models.project import Project
from app.models.safety_event import SafetyEvent
from app.schemas.events import (
    EventListRead,
    EventProvenanceRead,
    SafetyEventDetailRead,
    SafetyEventSummaryRead,
)
from app.services.permissions import Permission

router = APIRouter(prefix="/events", tags=["events"])

_SEARCH_MAX_LENGTH = 200


def _to_summary_read(event: SafetyEvent) -> SafetyEventSummaryRead:
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


def _to_detail_read(
    event: SafetyEvent, *, data_source_name: str | None, attributed_project_name: str | None = None
) -> SafetyEventDetailRead:
    return SafetyEventDetailRead(
        id=event.id,
        organization_id=event.organization_id,
        site_id=event.site_id,
        site_name=event.site.name if event.site is not None else None,
        event_type=event.event_type,
        event_subtype=event.event_subtype,
        event_time=event.event_time,
        period_end=event.period_end,
        reported_time=event.reported_time,
        status=event.status,
        severity=event.severity,
        potential_severity=event.potential_severity,
        description=event.description,
        location=event.location,
        project=event.project,
        department=event.department,
        contractor=event.contractor,
        activity=event.activity,
        attributes=event.attributes,
        data_quality_status=event.data_quality_status,
        data_quality_issues=event.data_quality_issues,
        attributed_project_id=event.attributed_project_id,
        attributed_project_name=attributed_project_name,
        provenance=EventProvenanceRead(
            organization_id=event.organization_id,
            source_system=event.source_system,
            source_record_id=event.source_record_id,
            source_record_version=event.source_record_version,
            source_schema_version=event.source_schema_version,
            ingestion_batch_id=event.ingestion_batch_id,
            ingestion_source_id=event.ingestion_source_id,
            data_source_name=data_source_name,
            ingestion_time=event.ingestion_time,
            normalization_version=event.normalization_version,
            schema_version=event.schema_version,
            correlation_id=event.correlation_id,
        ),
    )


@router.get(
    "",
    response_model=EventListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_events(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    event_type: str | None = Query(default=None, description="Exact match, e.g. INCIDENT."),
    event_subtype: str | None = Query(default=None, description="Exact match."),
    site_id: uuid.UUID | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status", description="Exact match."),
    source_system: str | None = Query(default=None, description="Exact match."),
    event_time_from: datetime | None = Query(default=None, description="Inclusive lower bound on event_time."),
    event_time_to: datetime | None = Query(default=None, description="Inclusive upper bound on event_time."),
    search: str | None = Query(
        default=None,
        max_length=_SEARCH_MAX_LENGTH,
        description="Matches description, source_record_id, event_type, event_subtype, or correlation_id.",
    ),
    context: RequestContext = Depends(require_context_permission(Permission.SAFETY_DATA_READ)),
    db: Session = Depends(get_db),
) -> EventListRead:
    conditions = [SafetyEvent.organization_id == organization_id]
    if event_type:
        conditions.append(SafetyEvent.event_type == event_type)
    if event_subtype:
        conditions.append(SafetyEvent.event_subtype == event_subtype)
    if site_id:
        conditions.append(SafetyEvent.site_id == site_id)
    if status_:
        conditions.append(SafetyEvent.status == status_)
    if source_system:
        conditions.append(SafetyEvent.source_system == source_system)
    if event_time_from:
        conditions.append(SafetyEvent.event_time >= event_time_from)
    if event_time_to:
        conditions.append(SafetyEvent.event_time <= event_time_to)
    if search:
        # Parameterized ORM ILIKE -- never raw/interpolated SQL (§4's
        # "avoid unrestricted SQL-style search").
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                SafetyEvent.description.ilike(pattern),
                SafetyEvent.source_record_id.ilike(pattern),
                SafetyEvent.event_type.ilike(pattern),
                SafetyEvent.event_subtype.ilike(pattern),
                SafetyEvent.correlation_id.ilike(pattern),
            )
        )

    # Count first, against the same filters, without ever materializing
    # the full matching population (§4's "avoid loading the entire
    # enterprise event population into memory").
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
        items=[_to_summary_read(e) for e in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{event_id}",
    response_model=SafetyEventDetailRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_event(
    event_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.SAFETY_DATA_READ)),
    db: Session = Depends(get_db),
) -> SafetyEventDetailRead:
    event = db.execute(
        select(SafetyEvent)
        .where(SafetyEvent.id == event_id, SafetyEvent.organization_id == organization_id)
        .options(joinedload(SafetyEvent.site))
    ).scalar_one_or_none()
    if event is None:
        # Deliberately identical whether event_id doesn't exist at all or
        # belongs to a different organization -- see module docstring's
        # own "Event ID isolation" note. Never a 403 here, which would
        # itself disclose that the id exists elsewhere.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    data_source_name: str | None = None
    if event.ingestion_source_id is not None:
        data_source = db.get(DataSource, event.ingestion_source_id)
        data_source_name = data_source.name if data_source is not None else None

    attributed_project_name: str | None = None
    if event.attributed_project_id is not None:
        project = db.get(Project, event.attributed_project_id)
        attributed_project_name = project.name if project is not None else None

    return _to_detail_read(event, data_source_name=data_source_name, attributed_project_name=attributed_project_name)


__all__ = ["router"]
