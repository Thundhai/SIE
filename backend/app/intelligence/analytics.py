"""Analytics composition — the layer `app/api/v1/intelligence.py`'s
read/analytics endpoints call. Ties together
`app/intelligence/features.py`, `indicators.py`, `signals.py`,
`trends.py`, `sufficiency.py`, and `reliability.py` into the two shapes
the milestone's own API list needs: a point-in-time summary, and a
trend series for one named metric.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.features import FeatureValue, feature_engineering_service
from app.intelligence.indicators import IndicatorValue, compute_indicators
from app.intelligence.reliability import SourceReliability, compute_source_reliability
from app.intelligence.signals import RiskSignal, is_unsafe_observation, risk_signal_service
from app.intelligence.sufficiency import classify_data_sufficiency
from app.intelligence.temporal import bucketed_counts, events_as_of, utcnow, window_bounds
from app.intelligence.trends import TrendPeriod, TrendResult, classify_trend

# metric name -> (event_type, predicate | None) -- the vocabulary
# GET /api/v1/intelligence/analytics/trends accepts for `metric`.
TREND_METRIC_REGISTRY: dict[str, tuple[str, object]] = {
    "incident_count": ("INCIDENT", None),
    "near_miss_count": ("NEAR_MISS", None),
    "observation_count": ("OBSERVATION", None),
    "audit_count": ("AUDIT", None),
    "inspection_count": ("INSPECTION", None),
    "overdue_action_count": ("CORRECTIVE_ACTION", lambda e: e.status == "OVERDUE"),
    "equipment_failure_count": ("EQUIPMENT", lambda e: e.event_subtype == "failure"),
    "unsafe_observation_count": ("OBSERVATION", is_unsafe_observation),
}


@dataclass
class AnalyticsSummary:
    organization_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    event_count: int
    data_sufficiency: str
    features: dict[str, FeatureValue] = field(default_factory=dict)
    indicators: list[IndicatorValue] = field(default_factory=list)
    signals: list[RiskSignal] = field(default_factory=list)
    source_reliability: list[SourceReliability] = field(default_factory=list)


def compute_summary(
    db: Session,
    *,
    organization_id: uuid.UUID,
    as_of: datetime | None = None,
    window_days: int | None = None,
    site_id: uuid.UUID | None = None,
    entity_type: str = "organization",
    entity_id: uuid.UUID | None = None,
) -> AnalyticsSummary:
    as_of = as_of or utcnow()
    window_days = window_days or settings.INTELLIGENCE_DEFAULT_WINDOW_DAYS
    entity_id = entity_id if entity_id is not None else site_id
    window_start, _ = window_bounds(as_of, window_days)

    event_count = db.execute(
        select(func.count()).select_from(
            events_as_of(
                organization_id=organization_id, as_of=as_of, window_start=window_start, site_id=site_id
            ).subquery()
        )
    ).scalar_one()

    features = feature_engineering_service.compute(
        db,
        organization_id=organization_id,
        as_of=as_of,
        window_days=window_days,
        site_id=site_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    indicators = compute_indicators(features)
    signals = risk_signal_service.detect_all(
        db,
        organization_id=organization_id,
        as_of=as_of,
        window_days=window_days,
        site_id=site_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    reliability = compute_source_reliability(db, organization_id=organization_id, as_of=as_of)

    return AnalyticsSummary(
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        as_of=as_of,
        window_days=window_days,
        event_count=event_count,
        data_sufficiency=classify_data_sufficiency(event_count).value,
        features=features,
        indicators=indicators,
        signals=signals,
        source_reliability=reliability,
    )


def compute_trend(
    db: Session,
    *,
    organization_id: uuid.UUID,
    metric: str,
    as_of: datetime | None = None,
    period_days: int | None = None,
    num_periods: int | None = None,
    site_id: uuid.UUID | None = None,
) -> TrendResult:
    if metric not in TREND_METRIC_REGISTRY:
        raise ValueError(
            f"Unknown metric {metric!r}. Supported: {sorted(TREND_METRIC_REGISTRY)}."
        )
    event_type, predicate = TREND_METRIC_REGISTRY[metric]

    as_of = as_of or utcnow()
    period_days = period_days or settings.INTELLIGENCE_DEFAULT_WINDOW_DAYS
    num_periods = num_periods or max(settings.INTELLIGENCE_TREND_MIN_PERIODS, 4)

    buckets = bucketed_counts(
        db,
        organization_id=organization_id,
        site_id=site_id,
        period_end=as_of,
        period_days=period_days,
        num_periods=num_periods,
        event_type=event_type,
        predicate=predicate,
    )
    periods = [TrendPeriod(period_start=s, period_end=e, value=float(c)) for s, e, c in buckets]
    return classify_trend(metric, periods)
