"""Intelligence API — milestone items 9, 27, 37; extended by Intelligence
Platform Integration & Enterprise API v0.1, items 17, 30, 38.

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** This router
used to serve both (a) generic Safety Event ingestion and (b) the
proprietary enterprise-intelligence analytics/attention/context/memory
reads. As of this milestone, (b)'s implementation --
`app/intelligence/analytics.py`, `attention.py`, `context_composition.py`,
`enterprise_intelligence_service.py`, `features.py`,
`memory_integration.py`, `signals.py`, and the response-shaping schema
modules that only existed to carry their output -- has been extracted to
the private Commercial Core repository, where the proprietary
computation actually lives now. Public SIE no longer contains it.

    external system -> Authorization: Bearer <client_id>:<secret>
        -> require_scope(SAFETY_DATA_WRITE)
        -> POST .../events | .../events/batch
        -> GenericJSONAdapter -> SafetyEventIngestionService -> SafetyEvent rows
        (unchanged -- generic ingestion, not proprietary intelligence)

    human OR machine caller -> GET .../analytics/summary | .../analytics/trends |
        .../analytics/signals | .../features | .../enterprise | .../context |
        .../memory-context | .../attention
        -> HTTP 501 (Commercial Core client integration not yet wired -- see
           docs/M43_IP_03_PUBLIC_EXTRACTION.md)

These reads are not deleted outright (the route, its path, and its
authorization requirement all still exist) because removing the route
entirely would silently 404 rather than honestly say why the data isn't
available, and because a genuine future integration (Public SIE calling
a deployed Commercial Core service, or the sie-contract package) plugs
into exactly this seam. Do not add the private algorithm back here to
make these endpoints "work again" -- see the milestone's own "No Fake
Extraction" rule.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.api.deps_machine_auth import MachineClientContext, require_scope
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.intelligence.adapters import GenericJSONAdapter
from app.intelligence.ingestion_service import safety_event_ingestion_service
from app.intelligence.schemas import RawSafetyEventPayload
from app.integrations.commercial_core import commercial_core_client
from app.schemas.intelligence import (
    BatchIngestionRead,
    IngestionIssueRead,
    IngestionRecordRead,
    SafetyEventBatchCreate,
    SafetyEventCreate,
)
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

_adapter = GenericJSONAdapter()


def _not_available() -> HTTPException:
    return commercial_core_client.unavailable("Enterprise intelligence analytics/attention/context")


def _to_raw_payload(body: SafetyEventCreate) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type=body.event_type,
        event_subtype=body.event_subtype,
        event_time=body.event_time,
        period_end=body.period_end,
        reported_time=body.reported_time,
        site_id=body.site_id,
        location=body.location,
        project=body.project,
        department=body.department,
        contractor=body.contractor,
        activity=body.activity,
        severity=body.severity,
        potential_severity=body.potential_severity,
        status=body.status,
        description=body.description,
        attributes=body.attributes,
        source_system=body.source_system,
        source_record_id=body.source_record_id,
        source_record_version=body.source_record_version,
        correlation_id=body.correlation_id,
        source_schema_version=body.source_schema_version,
    )


def _to_record_read(result) -> IngestionRecordRead:
    return IngestionRecordRead(
        outcome=result.outcome.value,
        event_id=result.event_id,
        data_quality_status=result.data_quality_status,
        issues=[IngestionIssueRead(**issue) for issue in result.issues],
        duplicate_in_batch=result.duplicate_in_batch,
        source_system=result.source_system,
        source_record_id=result.source_record_id,
    )


# --- Ingestion (machine-client authenticated) -- unchanged, generic, not proprietary --------


@router.post(
    "/events", response_model=IngestionRecordRead, dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))]
)
def ingest_event(
    body: SafetyEventCreate,
    context: MachineClientContext = Depends(require_scope(Permission.SAFETY_DATA_WRITE)),
    db: Session = Depends(get_db),
) -> IngestionRecordRead:
    result = safety_event_ingestion_service.ingest_event(
        db,
        organization_id=context.organization_id,
        payload=_to_raw_payload(body),
        adapter=_adapter,
    )
    return _to_record_read(result)


@router.post(
    "/events/batch",
    response_model=BatchIngestionRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def ingest_event_batch(
    body: SafetyEventBatchCreate,
    context: MachineClientContext = Depends(require_scope(Permission.SAFETY_DATA_WRITE)),
    db: Session = Depends(get_db),
) -> BatchIngestionRead:
    batch_result = safety_event_ingestion_service.ingest_batch(
        db,
        organization_id=context.organization_id,
        payloads=[_to_raw_payload(event) for event in body.events],
        adapter=_adapter,
    )
    return BatchIngestionRead(
        batch_id=batch_result.batch_id,
        record_count=len(batch_result.records),
        created_count=batch_result.created_count,
        updated_count=batch_result.updated_count,
        skipped_idempotent_count=batch_result.skipped_idempotent_count,
        rejected_count=batch_result.rejected_count,
        duplicate_in_batch_count=batch_result.duplicate_in_batch_count,
        records=[_to_record_read(r) for r in batch_result.records],
    )


# --- Analytics / attention / context / memory (extracted -- 501) ----------------------------


@router.get("/analytics/summary", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def analytics_summary(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/analytics/trends", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def analytics_trends(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/analytics/signals", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def analytics_signals(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/features", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def features(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/enterprise", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def enterprise_intelligence(
    organization_id: uuid.UUID = Query(...),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/sites/{site_id}", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def site_intelligence(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/context", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def field_intelligence_context(
    organization_id: uuid.UUID = Query(...),
    project_id: uuid.UUID | None = Query(default=None),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/sites/{site_id}/context", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def site_field_intelligence_context(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/memory-context", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def organization_memory_context(
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/sites/{site_id}/memory-context", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def site_memory_context(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/attention", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def organization_attention(
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()


@router.get("/sites/{site_id}/attention", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def site_attention(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    raise _not_available()
