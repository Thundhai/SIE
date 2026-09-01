"""Deterministic risk signals — milestone item 22. Every signal here is a
rule-based comparison of a current-window count/rate against a
historical baseline (`app/intelligence/anomaly.py`'s method, or a
simpler fixed-multiplier "surge" check) — never a prediction, never a
probability (milestone item 29). A signal fires only when the underlying
feature's own `data_quality` is at least `LIMITED_DATA` (milestone item
53: "if a site only has a tiny amount of data, do not generate a strong
risk signal") — an `INSUFFICIENT_DATA` feature never produces a signal at
all, regardless of what the raw arithmetic would say.

**Baseline bucketing.** Rather than calendar-month buckets (which vary in
length and add boundary-condition complexity for no real benefit at
foundation-milestone scale), the baseline is `N` consecutive,
non-overlapping, `window_days`-length buckets immediately preceding the
current analysis window — e.g. with the default 30-day window and a
90-day `INTELLIGENCE_BASELINE_WINDOW_DAYS`, three preceding 30-day
buckets. Documented, not hidden — see `_baseline_bucket_counts()`.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.enums import DataSufficiency, RiskSignalSeverity, RiskSignalType
from app.intelligence.features import FeatureValue, feature_engineering_service
from app.intelligence.temporal import bucketed_counts, events_as_of, utcnow, window_bounds
from app.models.safety_event import SafetyEvent

RISK_SIGNAL_CALCULATION_VERSION = "risk-signal-v1"


@dataclass
class RiskSignal:
    signal_type: str
    severity: str
    observed_period_start: datetime
    observed_period_end: datetime
    entity_type: str
    entity_id: uuid.UUID | None
    supporting_features: dict[str, float | int | None] = field(default_factory=dict)
    supporting_event_ids: list[uuid.UUID] = field(default_factory=list)
    data_quality: str = DataSufficiency.INSUFFICIENT_DATA.value
    calculation_version: str = RISK_SIGNAL_CALCULATION_VERSION


def _baseline_bucket_counts(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
    window_start: datetime,
    window_days: int,
    event_type: str,
    predicate,
    num_buckets: int | None = None,
) -> list[int]:
    """Counts of `predicate(event)`-matching events in `num_buckets`
    consecutive `window_days`-length buckets immediately preceding
    `window_start` (i.e. strictly before the current analysis window —
    never overlapping it, so the baseline never includes the same events
    being compared against it). Thin wrapper over
    `app.intelligence.temporal.bucketed_counts()` returning just the
    counts, oldest first."""
    num_buckets = num_buckets or max(1, settings.INTELLIGENCE_BASELINE_WINDOW_DAYS // window_days)
    buckets = bucketed_counts(
        db,
        organization_id=organization_id,
        site_id=site_id,
        period_end=window_start,
        period_days=window_days,
        num_periods=num_buckets,
        event_type=event_type,
        predicate=predicate,
    )
    return [count for _, _, count in buckets]


def _surge_triggered(current_count: int, baseline_counts: list[int]) -> tuple[bool, str | None]:
    if current_count < settings.INTELLIGENCE_SIGNAL_MIN_EVENT_COUNT:
        return False, None
    baseline_avg = statistics.fmean(baseline_counts) if baseline_counts else 0.0
    threshold = baseline_avg * settings.INTELLIGENCE_SIGNAL_SURGE_MULTIPLIER
    if baseline_avg == 0:
        triggered = current_count >= settings.INTELLIGENCE_SIGNAL_MIN_EVENT_COUNT
    else:
        triggered = current_count >= threshold
    if not triggered:
        return False, None
    severe_threshold = baseline_avg * settings.INTELLIGENCE_SIGNAL_SURGE_MULTIPLIER * 1.5
    severity = (
        RiskSignalSeverity.HIGH.value
        if current_count >= max(severe_threshold, settings.INTELLIGENCE_SIGNAL_MIN_EVENT_COUNT * 2)
        else RiskSignalSeverity.MEDIUM.value
    )
    return True, severity


class RiskSignalService:
    def detect_all(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        as_of: datetime | None = None,
        window_days: int | None = None,
        site_id: uuid.UUID | None = None,
        entity_type: str = "organization",
        entity_id: uuid.UUID | None = None,
    ) -> list[RiskSignal]:
        as_of = as_of or utcnow()
        window_days = window_days or settings.INTELLIGENCE_DEFAULT_WINDOW_DAYS
        window_start, _ = window_bounds(as_of, window_days)
        entity_id = entity_id if entity_id is not None else site_id

        features = feature_engineering_service.compute(
            db,
            organization_id=organization_id,
            as_of=as_of,
            window_days=window_days,
            site_id=site_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        signals: list[RiskSignal] = []
        common = dict(
            db=db,
            organization_id=organization_id,
            site_id=site_id,
            window_start=window_start,
            as_of=as_of,
            window_days=window_days,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        signal = self._surge_signal(
            RiskSignalType.HIGH_POTENTIAL_EVENT_CLUSTER,
            feature=features["high_potential_event_count"],
            event_type="INCIDENT",
            predicate=lambda e: e.potential_severity in ("HIGH", "CRITICAL"),
            secondary_event_type="NEAR_MISS",
            **common,
        )
        if signal:
            signals.append(signal)

        signal = self._surge_signal(
            RiskSignalType.OVERDUE_ACTION_SURGE,
            feature=features["overdue_action_count"],
            event_type="CORRECTIVE_ACTION",
            predicate=lambda e: e.status == "OVERDUE",
            **common,
        )
        if signal:
            signals.append(signal)

        signal = self._surge_signal(
            RiskSignalType.EQUIPMENT_FAILURE_CLUSTER,
            feature=features["equipment_failure_count"],
            event_type="EQUIPMENT",
            predicate=lambda e: e.event_subtype == "failure",
            **common,
        )
        if signal:
            signals.append(signal)

        unsafe_observation_feature = self._unsafe_observation_feature(db, organization_id, site_id, window_start, as_of, window_days, entity_type, entity_id)
        signal = self._surge_signal(
            RiskSignalType.UNSAFE_OBSERVATION_SURGE,
            feature=unsafe_observation_feature,
            event_type="OBSERVATION",
            predicate=is_unsafe_observation,
            **common,
        )
        if signal:
            signals.append(signal)

        signal = self._training_compliance_signal(features["training_completion_rate"], window_start, as_of, entity_type, entity_id)
        if signal:
            signals.append(signal)

        return signals

    def _surge_signal(
        self,
        signal_type: RiskSignalType,
        *,
        feature: FeatureValue,
        db: Session,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        window_start: datetime,
        as_of: datetime,
        window_days: int,
        entity_type: str,
        entity_id: uuid.UUID | None,
        event_type: str,
        predicate,
        secondary_event_type: str | None = None,
    ) -> RiskSignal | None:
        if feature.data_quality == DataSufficiency.INSUFFICIENT_DATA.value:
            return None  # milestone item 53 -- never a signal from too little data

        baseline = _baseline_bucket_counts(
            db,
            organization_id=organization_id,
            site_id=site_id,
            window_start=window_start,
            window_days=window_days,
            event_type=event_type,
            predicate=predicate,
        )
        if secondary_event_type:
            secondary = _baseline_bucket_counts(
                db,
                organization_id=organization_id,
                site_id=site_id,
                window_start=window_start,
                window_days=window_days,
                event_type=secondary_event_type,
                predicate=predicate,
            )
            baseline = [a + b for a, b in zip(baseline, secondary)]

        current_count = feature.value if isinstance(feature.value, int) else int(feature.value or 0)
        triggered, severity = _surge_triggered(current_count, baseline)
        if not triggered:
            return None

        baseline_avg = round(statistics.fmean(baseline), 3) if baseline else 0.0
        return RiskSignal(
            signal_type=signal_type.value,
            severity=severity,
            observed_period_start=window_start,
            observed_period_end=as_of,
            entity_type=entity_type,
            entity_id=entity_id,
            supporting_features={feature.name: feature.value, f"baseline_{window_days}d_avg": baseline_avg},
            supporting_event_ids=feature.source_event_ids,
            data_quality=feature.data_quality,
        )

    def _unsafe_observation_feature(
        self, db, organization_id, site_id, window_start, as_of, window_days, entity_type, entity_id
    ) -> FeatureValue:
        query = events_as_of(
            organization_id=organization_id, as_of=as_of, window_start=window_start, site_id=site_id,
            event_type="OBSERVATION",
        )
        events = [e for e in db.execute(query).scalars().all() if is_unsafe_observation(e)]
        from app.intelligence.sufficiency import classify_data_sufficiency

        return FeatureValue(
            name="unsafe_observation_count",
            value=len(events),
            window_days=window_days,
            as_of=as_of,
            entity_type=entity_type,
            entity_id=entity_id,
            source_event_ids=[e.id for e in events[:50]],
            calculation_version="feature-v1",
            data_quality=classify_data_sufficiency(len(events)).value,
        )

    def _training_compliance_signal(
        self, feature: FeatureValue, window_start: datetime, as_of: datetime, entity_type: str, entity_id
    ) -> RiskSignal | None:
        if feature.data_quality == DataSufficiency.INSUFFICIENT_DATA.value or feature.value is None:
            return None
        if feature.value >= settings.INTELLIGENCE_TRAINING_COMPLIANCE_THRESHOLD:
            return None
        return RiskSignal(
            signal_type=RiskSignalType.TRAINING_COMPLIANCE_DROP.value,
            severity=(
                RiskSignalSeverity.HIGH.value
                if feature.value < settings.INTELLIGENCE_TRAINING_COMPLIANCE_THRESHOLD * 0.75
                else RiskSignalSeverity.MEDIUM.value
            ),
            observed_period_start=window_start,
            observed_period_end=as_of,
            entity_type=entity_type,
            entity_id=entity_id,
            supporting_features={
                "training_completion_rate": feature.value,
                "threshold": settings.INTELLIGENCE_TRAINING_COMPLIANCE_THRESHOLD,
            },
            supporting_event_ids=feature.source_event_ids,
            data_quality=feature.data_quality,
        )


def is_unsafe_observation(event: SafetyEvent) -> bool:
    subtype = (event.event_subtype or "").lower()
    return "unsafe" in subtype


risk_signal_service = RiskSignalService()
