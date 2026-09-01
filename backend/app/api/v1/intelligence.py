"""Intelligence & Predictive Analytics API — milestone items 9, 27, 37.

    external system -> Authorization: Bearer <client_id>:<secret>
        -> require_scope(SAFETY_DATA_WRITE)
        -> POST .../events | .../events/batch
        -> GenericJSONAdapter -> SafetyEventIngestionService -> SafetyEvent rows

    human user -> authorization_service.can(INTELLIGENCE_READ, organization_id)
        -> GET .../analytics/summary | .../analytics/trends | .../analytics/signals | .../features

**External applications never touch the database directly** (milestone
item 37) — every write goes through validation/normalization/idempotent
upsert (`app/intelligence/ingestion_service.py`); every read goes through
`app/intelligence/analytics.py`'s composition layer.

**Tenant isolation (milestone item 36).** Ingestion trusts only the
authenticated `MachineClientContext.organization_id` — never a client-
supplied `organization_id` field in the payload (there is no such field
on `SafetyEventCreate` at all). Reads require `organization_id` as an
explicit, authorized query parameter, the same
authenticate-then-authorize-then-pass-a-trusted-value shape
`app/api/v1/retrieval.py`/`app/api/v1/rag.py` already establish.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_dev_authenticated_user_id
from app.api.deps_machine_auth import MachineClientContext, require_scope
from app.intelligence.adapters import GenericJSONAdapter
from app.intelligence.analytics import compute_summary, compute_trend
from app.intelligence.features import feature_engineering_service
from app.intelligence.ingestion_service import safety_event_ingestion_service
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.signals import risk_signal_service
from app.schemas.intelligence import (
    AnalyticsSummaryRead,
    BatchIngestionRead,
    FeaturesRead,
    FeatureValueRead,
    IndicatorValueRead,
    IngestionIssueRead,
    IngestionRecordRead,
    RiskSignalRead,
    SafetyEventBatchCreate,
    SafetyEventCreate,
    SourceReliabilityRead,
    TrendPeriodRead,
    TrendResultRead,
)
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

_adapter = GenericJSONAdapter()


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


# --- Ingestion (machine-client authenticated) ---------------------------------------


@router.post("/events", response_model=IngestionRecordRead)
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


@router.post("/events/batch", response_model=BatchIngestionRead)
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


# --- Analytics (human-authenticated, tenant-authorized) ------------------------------


def _authorize_read(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    if not authorization_service.can(
        db, user_id=user_id, permission=Permission.INTELLIGENCE_READ, organization_id=organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing intelligence:read permission in the requested organization.",
        )


@router.get("/analytics/summary", response_model=AnalyticsSummaryRead)
def analytics_summary(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> AnalyticsSummaryRead:
    _authorize_read(db, user_id, organization_id)
    entity_type = "site" if site_id is not None else "organization"
    summary = compute_summary(
        db, organization_id=organization_id, site_id=site_id, window_days=window_days, entity_type=entity_type
    )
    _audit_analytics_query(db, user_id=user_id, organization_id=organization_id, endpoint="summary")
    return AnalyticsSummaryRead(
        organization_id=summary.organization_id,
        entity_type=summary.entity_type,
        entity_id=summary.entity_id,
        as_of=summary.as_of,
        window_days=summary.window_days,
        event_count=summary.event_count,
        data_sufficiency=summary.data_sufficiency,
        features={name: _feature_read(f) for name, f in summary.features.items()},
        indicators=[
            IndicatorValueRead(name=i.name, category=i.category, feature=_feature_read(i.feature))
            for i in summary.indicators
        ],
        signals=[_signal_read(s) for s in summary.signals],
        source_reliability=[SourceReliabilityRead(**vars(r)) for r in summary.source_reliability],
    )


@router.get("/analytics/trends", response_model=TrendResultRead)
def analytics_trends(
    organization_id: uuid.UUID = Query(...),
    metric: str = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    period_days: int | None = Query(default=None, ge=1, le=3650),
    num_periods: int | None = Query(default=None, ge=2, le=52),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> TrendResultRead:
    _authorize_read(db, user_id, organization_id)
    try:
        trend = compute_trend(
            db,
            organization_id=organization_id,
            metric=metric,
            site_id=site_id,
            period_days=period_days,
            num_periods=num_periods,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit_analytics_query(db, user_id=user_id, organization_id=organization_id, endpoint="trends")
    return TrendResultRead(
        metric=trend.metric,
        direction=trend.direction,
        periods=[TrendPeriodRead(period_start=p.period_start, period_end=p.period_end, value=p.value) for p in trend.periods],
        slope=trend.slope,
        relative_slope=trend.relative_slope,
        calculation_version=trend.calculation_version,
        method=trend.method,
    )


@router.get("/analytics/signals", response_model=list[RiskSignalRead])
def analytics_signals(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> list[RiskSignalRead]:
    _authorize_read(db, user_id, organization_id)
    signals = risk_signal_service.detect_all(
        db, organization_id=organization_id, site_id=site_id, window_days=window_days
    )
    _audit_analytics_query(db, user_id=user_id, organization_id=organization_id, endpoint="signals")
    return [_signal_read(s) for s in signals]


@router.get("/features", response_model=FeaturesRead)
def features(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> FeaturesRead:
    _authorize_read(db, user_id, organization_id)
    entity_type = "site" if site_id is not None else "organization"
    feature_values = feature_engineering_service.compute(
        db, organization_id=organization_id, site_id=site_id, window_days=window_days, entity_type=entity_type
    )
    _audit_analytics_query(db, user_id=user_id, organization_id=organization_id, endpoint="features")
    return FeaturesRead(
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=site_id,
        as_of=next(iter(feature_values.values())).as_of,
        window_days=next(iter(feature_values.values())).window_days,
        features={name: _feature_read(f) for name, f in feature_values.items()},
    )


def _feature_read(f) -> FeatureValueRead:
    return FeatureValueRead(
        name=f.name,
        value=f.value,
        window_days=f.window_days,
        as_of=f.as_of,
        entity_type=f.entity_type,
        entity_id=f.entity_id,
        source_event_ids=f.source_event_ids,
        calculation_version=f.calculation_version,
        data_quality=f.data_quality,
        exposure_basis=f.exposure_basis,
        unavailable_reason=f.unavailable_reason,
    )


def _signal_read(s) -> RiskSignalRead:
    return RiskSignalRead(
        signal_type=s.signal_type,
        severity=s.severity,
        observed_period_start=s.observed_period_start,
        observed_period_end=s.observed_period_end,
        entity_type=s.entity_type,
        entity_id=s.entity_id,
        supporting_features=s.supporting_features,
        supporting_event_ids=s.supporting_event_ids,
        data_quality=s.data_quality,
        calculation_version=s.calculation_version,
    )


def _audit_analytics_query(db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID, endpoint: str) -> None:
    from app.services.audit_service import AuditAction, audit_service

    audit_service.log(
        db,
        action=AuditAction.INTELLIGENCE_ANALYTICS_QUERIED,
        resource_type="IntelligenceAnalytics",
        organization_id=organization_id,
        user_id=user_id,
        metadata={"endpoint": endpoint},
    )
