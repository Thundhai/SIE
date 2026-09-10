"""The one, shared feature-vectorization step between training
(`dataset.py`) and serving (`predictor.py`) — a single source of truth so
the two paths can never silently drift into train/serve skew.

`FeatureSnapshot.features` (and `FeatureSetV1.features`) is a dict of
uniform, JSON-shaped entries (see `feature_snapshot_service.py`'s
`SnapshotFeature`) — some numeric (counts, rates), some categorical
(`incident_trend`'s `INCREASING`/`STABLE`/`DECREASING`, an anomaly
status). A hand-rolled logistic regression (`logistic_regression.py`)
needs one flat `dict[str, float | None]` per entity — `encode_feature_value()`
is the one, versioned mapping from the stored representation to that
numeric one. `None` in the output is always genuine missingness (the
underlying `SnapshotFeature` had `value=None`, or an unrecognized
categorical value) — it is never silently coerced to `0.0` here; that
decision belongs to `logistic_regression.py`'s explicit, documented
imputation step, not to this module.
"""

from __future__ import annotations

VECTORIZATION_VERSION = "predictive-vectorization-v1"

TREND_FEATURE_NAMES = frozenset({"incident_trend", "near_miss_trend", "observation_trend"})
ANOMALY_FEATURE_NAMES = frozenset({"incident_anomaly", "equipment_failure_anomaly"})

_TREND_ENCODING = {"INCREASING": 1.0, "STABLE": 0.0, "DECREASING": -1.0}
_ANOMALY_ENCODING = {"ANOMALOUS": 1.0, "NORMAL": 0.0}

# The full, ordered FEATURE_SET_V1 feature list (milestone item 9) — the
# canonical column order every numeric feature vector uses. Any feature
# missing from a snapshot's `features` dict is treated as `None`
# (missing), never dropped silently from the vector.
FEATURE_NAMES: tuple[str, ...] = (
    "incident_count_7d",
    "incident_count_30d",
    "near_miss_count_30d",
    "observation_count_30d",
    "overdue_action_count_30d",
    "overdue_action_rate",
    "work_hours_30d",
    "incidents_per_100000_hours",
    "incident_count_90d",
    "severe_event_count_90d",
    "high_potential_event_count_90d",
    "equipment_failure_count_90d",
    "overdue_equipment_inspection_count",
    "training_compliance_rate",
    "expired_training_count",
    "action_closure_rate",
    "incident_trend",
    "near_miss_trend",
    "observation_trend",
    "incident_anomaly",
    "equipment_failure_anomaly",
)


def _entry_value(entry) -> object:
    """`entry` is either a `SnapshotFeature` dataclass instance (fresh
    from `compute_feature_set_v1()`) or the plain dict it round-trips to
    once persisted as JSON on `FeatureSnapshot.features` — accept both
    rather than forcing every caller to know which."""
    if entry is None:
        return None
    if isinstance(entry, dict):
        return entry.get("value")
    return entry.value


def encode_feature_value(name: str, entry) -> float | None:
    raw = _entry_value(entry)
    if raw is None:
        return None
    if name in TREND_FEATURE_NAMES:
        return _TREND_ENCODING.get(raw)  # unrecognized/INSUFFICIENT_DATA -> None
    if name in ANOMALY_FEATURE_NAMES:
        return _ANOMALY_ENCODING.get(raw)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def vectorize(features: dict[str, object]) -> dict[str, float | None]:
    """`features` is a `FeatureSetV1.features` dict or a persisted
    `FeatureSnapshot.features` JSON dict. Returns one entry per
    `FEATURE_NAMES` column, `None` for anything missing or unrecognized —
    a feature this snapshot never computed is exactly as missing as one
    whose stored value was `None`."""
    return {name: encode_feature_value(name, features.get(name)) for name in FEATURE_NAMES}
