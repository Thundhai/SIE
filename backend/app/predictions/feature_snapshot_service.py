"""Feature snapshot construction — milestone items 8-11. Builds
`FeatureSetV1` (item 9) entirely from the already-existing, already
point-in-time-safe `app/intelligence/` modules — no new feature
computation logic, no new temporal filtering logic, just composition and
persistence.

    build_feature_snapshot(organization_id, site_id, as_of)
        -> app.intelligence.features.feature_engineering_service.compute()
           at 7d / 30d / 90d windows
        -> app.intelligence.trends.classify_trend() for incident/near-miss/
           observation counts
        -> app.intelligence.anomaly.detect_anomaly() for incident/
           equipment-failure counts
        -> merge into FeatureSetV1, persist as FeatureSnapshot (idempotent
           on (organization_id, entity_type, entity_id, as_of, feature_set_version))

Every entry is a `SnapshotFeature` — a uniform, JSON-serializable
representation regardless of whether the underlying computation was a
count/rate (`FeatureValue`), a trend (`TrendResult`), or an anomaly
(`AnomalyResult`) — so `feature_snapshots.features` stays one flat,
consistently-shaped dict. **Never fabricated**: a feature this module
cannot reliably compute keeps `value=None` with an explicit
`unavailable_reason` (milestone item 10) — never replaced with `0`
unless `0` is the real, computed answer.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.anomaly import detect_anomaly
from app.intelligence.enums import DataSufficiency
from app.intelligence.features import feature_engineering_service
from app.intelligence.temporal import bucketed_counts
from app.intelligence.trends import classify_trend
from app.models.feature_snapshot import FeatureSnapshot
from app.predictions.spec import FEATURE_SET_VERSION

CALCULATION_VERSION = "predictive-features-v1"

_TREND_PERIOD_DAYS = 30
_TREND_NUM_PERIODS = 4
_ANOMALY_BASELINE_PERIODS = 4


@dataclass
class SnapshotFeature:
    """One uniform entry in a feature snapshot — see module docstring."""

    value: float | int | str | None
    data_quality: str
    calculation_version: str
    source_event_ids: list[str] = field(default_factory=list)
    unavailable_reason: str | None = None
    exposure_basis: float | None = None


@dataclass
class FeatureSetV1:
    entity_type: str
    entity_id: uuid.UUID
    organization_id: uuid.UUID
    as_of: datetime
    feature_set_version: str
    features: dict[str, SnapshotFeature]
    data_quality: str  # snapshot-level rollup
    source_event_ids: list[str]
    exposure_basis: float | None


def _from_feature_value(fv) -> SnapshotFeature:
    return SnapshotFeature(
        value=fv.value,
        data_quality=fv.data_quality,
        calculation_version=fv.calculation_version,
        # Stringified -- SnapshotFeature is stored as JSON (see
        # get_or_build_feature_snapshot() below), and a raw uuid.UUID is
        # not JSON-serializable.
        source_event_ids=[str(i) for i in fv.source_event_ids],
        unavailable_reason=fv.unavailable_reason,
        exposure_basis=fv.exposure_basis,
    )


def compute_feature_set_v1(
    db: Session, *, organization_id: uuid.UUID, site_id: uuid.UUID, as_of: datetime
) -> FeatureSetV1:
    features: dict[str, SnapshotFeature] = {}
    all_source_event_ids: set[str] = set()

    # --- Windowed counts/rates -- reuses app.intelligence.features unchanged ---------
    windows = feature_engineering_service.compute(
        db, organization_id=organization_id, as_of=as_of, window_days=7, site_id=site_id,
        entity_type="site", entity_id=site_id,
    )
    features["incident_count_7d"] = _from_feature_value(windows["incident_count"])

    w30 = feature_engineering_service.compute(
        db, organization_id=organization_id, as_of=as_of, window_days=30, site_id=site_id,
        entity_type="site", entity_id=site_id,
    )
    features["incident_count_30d"] = _from_feature_value(w30["incident_count"])
    features["near_miss_count_30d"] = _from_feature_value(w30["near_miss_count"])
    features["observation_count_30d"] = _from_feature_value(w30["observation_count"])
    features["overdue_action_count_30d"] = _from_feature_value(w30["overdue_action_count"])
    features["work_hours_30d"] = _from_feature_value(w30["exposure_hours"])
    features["incidents_per_100000_hours"] = _from_feature_value(w30["incidents_per_100000_hours"])

    w90 = feature_engineering_service.compute(
        db, organization_id=organization_id, as_of=as_of, window_days=90, site_id=site_id,
        entity_type="site", entity_id=site_id,
    )
    features["incident_count_90d"] = _from_feature_value(w90["incident_count"])
    features["severe_event_count_90d"] = _from_feature_value(w90["severe_event_count"])
    features["high_potential_event_count_90d"] = _from_feature_value(w90["high_potential_event_count"])
    features["equipment_failure_count_90d"] = _from_feature_value(w90["equipment_failure_count"])
    features["overdue_equipment_inspection_count"] = _from_feature_value(
        w90["overdue_equipment_inspection_count"]
    )
    features["training_compliance_rate"] = _from_feature_value(w90["training_completion_rate"])
    features["expired_training_count"] = _from_feature_value(w90["expired_certification_count"])
    features["action_closure_rate"] = _from_feature_value(w90["action_closure_rate"])

    # overdue_action_rate: derived, not a feature app.intelligence.features
    # computes directly -- open_action_count/overdue_action_count share
    # the same 90d window's determinable-actions denominator.
    open_count = w90["open_action_count"]
    overdue_count = w90["overdue_action_count"]
    determinable = (open_count.value or 0) + (overdue_count.value or 0)
    if open_count.value is not None and overdue_count.value is not None and determinable > 0:
        rate_value = overdue_count.value / determinable
        features["overdue_action_rate"] = SnapshotFeature(
            value=round(rate_value, 4),
            data_quality=overdue_count.data_quality,
            calculation_version=CALCULATION_VERSION,
            source_event_ids=[str(i) for i in overdue_count.source_event_ids]
            + [str(i) for i in open_count.source_event_ids],
        )
    else:
        features["overdue_action_rate"] = SnapshotFeature(
            value=None, data_quality=DataSufficiency.INSUFFICIENT_DATA.value,
            calculation_version=CALCULATION_VERSION, unavailable_reason="NO_ACTION_STATUS_DATA",
        )

    for f in features.values():
        all_source_event_ids.update(f.source_event_ids)

    # --- Trends (item 9) -- reuses app.intelligence.trends unchanged -----------------
    for name, event_type, predicate in (
        ("incident_trend", "INCIDENT", None),
        ("near_miss_trend", "NEAR_MISS", None),
        ("observation_trend", "OBSERVATION", None),
    ):
        buckets = bucketed_counts(
            db, organization_id=organization_id, site_id=site_id, period_end=as_of,
            period_days=_TREND_PERIOD_DAYS, num_periods=_TREND_NUM_PERIODS, event_type=event_type,
            predicate=predicate,
        )
        from app.intelligence.trends import TrendPeriod

        periods = [TrendPeriod(period_start=s, period_end=e, value=float(c)) for s, e, c in buckets]
        trend = classify_trend(name, periods)
        features[name] = SnapshotFeature(
            value=trend.direction,
            data_quality=(
                DataSufficiency.INSUFFICIENT_DATA.value
                if trend.direction == "INSUFFICIENT_DATA"
                else DataSufficiency.SUFFICIENT_DATA.value
            ),
            calculation_version=trend.calculation_version,
        )

    # --- Anomalies (item 9) -- reuses app.intelligence.anomaly unchanged -------------
    for name, event_type, predicate in (
        ("incident_anomaly", "INCIDENT", None),
        ("equipment_failure_anomaly", "EQUIPMENT", lambda e: e.event_subtype == "failure"),
    ):
        buckets = bucketed_counts(
            db, organization_id=organization_id, site_id=site_id, period_end=as_of,
            period_days=_TREND_PERIOD_DAYS, num_periods=_ANOMALY_BASELINE_PERIODS + 1, event_type=event_type,
            predicate=predicate,
        )
        *baseline_buckets, current_bucket = buckets
        baseline_values = [float(c) for _, _, c in baseline_buckets]
        current_value = float(current_bucket[2])
        anomaly = detect_anomaly(current_value, baseline_values)
        features[name] = SnapshotFeature(
            value=anomaly.status,
            data_quality=(
                DataSufficiency.INSUFFICIENT_DATA.value
                if anomaly.status == "INSUFFICIENT_DATA"
                else DataSufficiency.SUFFICIENT_DATA.value
            ),
            calculation_version=anomaly.calculation_version,
        )

    # --- Snapshot-level rollup ---------------------------------------------------------
    quality_values = {f.data_quality for f in features.values()}
    if DataSufficiency.INSUFFICIENT_DATA.value in quality_values and len(quality_values) == 1:
        overall_quality = DataSufficiency.INSUFFICIENT_DATA.value
    elif DataSufficiency.INSUFFICIENT_DATA.value in quality_values or DataSufficiency.LIMITED_DATA.value in quality_values:
        overall_quality = DataSufficiency.LIMITED_DATA.value
    else:
        overall_quality = DataSufficiency.SUFFICIENT_DATA.value

    exposure_basis = w30["exposure_hours"].value

    return FeatureSetV1(
        entity_type="site",
        entity_id=site_id,
        organization_id=organization_id,
        as_of=as_of,
        feature_set_version=FEATURE_SET_VERSION,
        features=features,
        data_quality=overall_quality,
        source_event_ids=sorted(all_source_event_ids, key=str),
        exposure_basis=exposure_basis,
    )


def get_or_build_feature_snapshot(
    db: Session, *, organization_id: uuid.UUID, site_id: uuid.UUID, as_of: datetime, persist: bool = True
) -> FeatureSnapshot:
    """Idempotent: reuses an existing snapshot for the same
    (organization, entity, as_of, feature_set_version) rather than
    recomputing/duplicating it — see `FeatureSnapshot`'s own docstring."""
    existing = db.execute(
        select(FeatureSnapshot).where(
            FeatureSnapshot.organization_id == organization_id,
            FeatureSnapshot.entity_type == "site",
            FeatureSnapshot.entity_id == site_id,
            FeatureSnapshot.as_of == as_of,
            FeatureSnapshot.feature_set_version == FEATURE_SET_VERSION,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    feature_set = compute_feature_set_v1(db, organization_id=organization_id, site_id=site_id, as_of=as_of)

    row = FeatureSnapshot(
        organization_id=organization_id,
        entity_type=feature_set.entity_type,
        entity_id=feature_set.entity_id,
        as_of=feature_set.as_of,
        feature_set_version=feature_set.feature_set_version,
        calculation_version=CALCULATION_VERSION,
        features={name: asdict(f) for name, f in feature_set.features.items()},
        data_quality=feature_set.data_quality,
        source_event_ids=[str(i) for i in feature_set.source_event_ids],
        exposure_basis=feature_set.exposure_basis,
    )
    if persist:
        db.add(row)
        db.commit()
        db.refresh(row)
    return row
