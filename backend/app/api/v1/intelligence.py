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

    human OR machine caller -> GET .../features | .../enterprise | .../context |
        .../memory-context
        -> HTTP 501 (Commercial Core client integration not yet wired -- see
           docs/M43_IP_03_PUBLIC_EXTRACTION.md)

    human OR machine caller -> GET .../attention | .../sites/{site_id}/attention
        -> Task 01D-B: CommercialCoreClient -> cc_service (Thundhai/SIE-Commercial-Core)
           POST /internal/v1/attention -> sie_contract.AttentionResultDTO

    human OR machine caller -> GET .../analytics/summary | .../analytics/trends |
        .../analytics/signals
        -> Task 01D-F2: CommercialCoreClient -> cc_service (Thundhai/SIE-Commercial-Core)
           POST /internal/v1/analytics/{summary,trends,signals} ->
           sie_contract.AnalyticsSummaryDTO / AnalyticsTrendDTO / AnalyticsSignalsResultDTO

    Both of the above still return HTTP 501 (the existing
    NotConfiguredCommercialCoreClient fallback) whenever this deployment
    has no Commercial Core configured -- see
    app/integrations/commercial_core.py. `.../analytics/trends` adds one
    new, previously-absent required query parameter, `metric` -- the
    stub never needed one; the real implementation cannot run without it.

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
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sie_contract import AnalyticsSummaryDTO, AttentionResultDTO
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import (
    RequestContext,
    require_context_permission,
    resolve_authorized_organization_id,
)
from app.api.deps_machine_auth import MachineClientContext, require_scope
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.errors import ApiError, ErrorCode
from app.core.request_id import get_request_id
from app.integrations.commercial_core import (
    CommercialCoreIntegrationError,
    CommercialCoreUnavailable,
    CommercialCoreValidationError,
    commercial_core_client,
    get_commercial_core_client,
)
from app.intelligence.adapters import GenericJSONAdapter
from app.intelligence.ingestion_service import safety_event_ingestion_service
from app.intelligence.schemas import RawSafetyEventPayload
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


def _map_commercial_core_attention_error(exc: CommercialCoreIntegrationError) -> ApiError:
    """Maps a `CommercialCoreIntegrationError` onto Public SIE's existing
    error vocabulary (`app.core.errors.ErrorCode`) -- no new error code
    introduced.

    `CommercialCoreValidationError` (cc_service's own 422 -- the request
    body it received, built entirely from already-validated Public SIE
    inputs, still failed the Domain Service's own validation) is mapped
    to `ErrorCode.VALIDATION_ERROR` at 422, matching this codebase's own
    existing status-code convention (`app.core.errors._STATUS_CODE_DEFAULTS`
    already treats 422 as `VALIDATION_ERROR`) and preserving the contract's
    own `retryable=False` semantics for this case: unlike a transient
    dependency outage, resubmitting the exact same request will not
    succeed by simply waiting and retrying.

    Every other subclass (auth, authorization, dependency-unavailable,
    timeout, connection, malformed-response, unexpected-status -- see
    that module's own docstrings) maps to `ErrorCode.MODEL_NOT_AVAILABLE`
    at 503. Deliberately one outcome for all of *those*: none of them are
    the calling Public SIE user's or machine client's own fault (they
    were already authenticated and authorized by Public SIE itself before
    this client was ever invoked), so none should be presented to them as
    if their own request were invalid or unauthorized.

    `str(exc)` is always one of `app/integrations/commercial_core.py`'s
    own fixed, safe messages -- never a Commercial Core stack trace,
    credential, or URL, for either branch."""
    if isinstance(exc, CommercialCoreValidationError):
        return ApiError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message=str(exc),
        )
    return ApiError(
        status_code=503,
        code=ErrorCode.MODEL_NOT_AVAILABLE,
        message=str(exc),
    )


def _analytics_summary_response(dto: AnalyticsSummaryDTO) -> dict:
    """Task 01D-F2: reshapes `AnalyticsSummaryDTO` (the redacted,
    Commercial-Core-contract shape) into the flat response body
    `src/services/api/analytics.ts`'s existing `AnalyticsSummary`
    TypeScript type -- and, specifically, `HomePage.tsx`'s own
    `indicator.feature.value` access -- expect.

    Two deliberate, honest differences from that TypeScript type,
    neither of which this repository's current UI actually reads:

    - `features`/`source_reliability` are omitted entirely, rather than
      filled with fabricated placeholder data -- the contract redacts
      exactly this internal detail (see `sie_contract.analytics`'s own
      module docstring), so there is nothing real to put there.
    - each indicator's `feature` is a minimal `{value, unavailable_reason}`
      object, not the full internal `FeatureValue` shape (no
      `calculation_version`/`exposure_basis`/`source_event_ids` --
      none of those cross the contract boundary either).

    `entity_type` is synthesized, not fabricated: it is exactly what
    `entity_id`'s own presence already means, by this DTO's own field
    documentation ("the site_id when site-scoped; None when
    organization-scoped")."""
    as_of = dto.as_of
    return {
        "organization_id": str(dto.organization_id),
        "entity_type": "site" if dto.entity_id is not None else "organization",
        "entity_id": str(dto.entity_id) if dto.entity_id is not None else None,
        "as_of": as_of.as_of.isoformat(),
        "window_days": as_of.window_days,
        "event_count": dto.event_count,
        "data_sufficiency": dto.data_sufficiency.value,
        "indicators": [
            {
                "name": indicator.name,
                "category": indicator.category.value,
                "feature": {"value": indicator.value, "unavailable_reason": indicator.unavailable_reason},
            }
            for indicator in dto.indicators
        ],
        "signals": [signal.model_dump(mode="json") for signal in dto.signals],
    }


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
    request: Request,
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
    request_id: str | None = Depends(get_request_id),
):
    try:
        client = get_commercial_core_client()
        dto = client.get_analytics_summary(
            organization_id=resolve_authorized_organization_id(context, organization_id),
            site_id=site_id,
            as_of=None,
            window_days=window_days,
            request_id=request_id,
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_attention_error(exc) from exc
    return _analytics_summary_response(dto)


@router.get("/analytics/trends", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def analytics_trends(
    request: Request,
    metric: str = Query(..., description="A known trend metric name, e.g. 'incident_count'. See app/intelligence/analytics.py::TREND_METRIC_REGISTRY (Commercial Core) for the full vocabulary."),
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
    request_id: str | None = Depends(get_request_id),
):
    try:
        client = get_commercial_core_client()
        dto = client.get_analytics_trends(
            organization_id=resolve_authorized_organization_id(context, organization_id),
            metric=metric,
            site_id=site_id,
            as_of=None,
            window_days=window_days,
            request_id=request_id,
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_attention_error(exc) from exc
    return dto.model_dump(mode="json")


@router.get("/analytics/signals", dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def analytics_signals(
    request: Request,
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
    request_id: str | None = Depends(get_request_id),
):
    try:
        client = get_commercial_core_client()
        dto = client.get_analytics_signals(
            organization_id=resolve_authorized_organization_id(context, organization_id),
            site_id=site_id,
            as_of=None,
            window_days=window_days,
            request_id=request_id,
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_attention_error(exc) from exc
    # Task 01D-F2: the existing frontend (src/services/api/analytics.ts::
    # getAnalyticsSignals()) expects a bare `RiskSignal[]` array, not an
    # organization/as_of-enveloped object -- the envelope is the
    # contract's own shape (mirrors AttentionResultDTO), unwrapped here,
    # at the Public SIE API boundary, rather than changing that existing
    # frontend expectation.
    return [signal.model_dump(mode="json") for signal in dto.signals]


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


@router.get(
    "/attention",
    response_model=AttentionResultDTO,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def organization_attention(
    request: Request,
    organization_id: uuid.UUID = Query(...),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    as_of: datetime | None = Query(default=None),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
    request_id: str | None = Depends(get_request_id),
) -> AttentionResultDTO:
    try:
        client = get_commercial_core_client()
        return client.get_attention(
            organization_id=resolve_authorized_organization_id(context, organization_id),
            scope="organization",
            site_id=None,
            as_of=as_of,
            window_days=window_days,
            request_id=request_id,
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_attention_error(exc) from exc


@router.get(
    "/sites/{site_id}/attention",
    response_model=AttentionResultDTO,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def site_attention(
    site_id: uuid.UUID,
    request: Request,
    organization_id: uuid.UUID = Query(...),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    as_of: datetime | None = Query(default=None),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
    request_id: str | None = Depends(get_request_id),
) -> AttentionResultDTO:
    try:
        client = get_commercial_core_client()
        return client.get_attention(
            organization_id=resolve_authorized_organization_id(context, organization_id),
            scope="site",
            site_id=site_id,
            as_of=as_of,
            window_days=window_days,
            request_id=request_id,
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_attention_error(exc) from exc
