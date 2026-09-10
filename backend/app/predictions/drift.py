"""Data drift, feature drift, and model performance drift — Model
Validation & Governance v0.1, items 29-32.

**Explainable statistical methods only — no deep-learning drift
detection** (item 29's own instruction): Population Stability Index
(PSI) and mean/standard-deviation comparison for feature drift, a simple
event-frequency ratio for data drift, and a direct before/after metric
comparison for performance drift. Every number here is a value a human
can recompute by hand from the two inputs.

**Detecting drift never retrains, redeploys, or retires a model on its
own (item 32, non-negotiable).** `check_model_for_review()` is the one
function that acts on a drift finding, and the only thing it ever does
is create a `ModelReviewFlag` row and audit-log it —
`app/predictions/model_registry.py` is never called from here. Whatever
happens next (retrain, redeploy a different version, retire, or
determine it's a false alarm) is a separate, human-initiated decision.
"""

from __future__ import annotations

import math
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.model_registry_entry import ModelRegistryEntry
from app.models.model_review_flag import ModelReviewFlag
from app.predictions.enums import ReviewFlagReason
from app.predictions.vectorization import FEATURE_NAMES
from app.services.audit_service import AuditAction, audit_service

# --- INITIAL GOVERNANCE DEFAULT thresholds ---------------------------------------------
# PSI conventions borrowed from common industry practice (< 0.1 stable,
# 0.1-0.25 moderate, > 0.25 significant) -- documented here as a starting
# point this codebase has not independently validated, not a claim of
# universal correctness (milestone item 30's own instruction).
DEFAULT_PSI_MODERATE_THRESHOLD = 0.10
DEFAULT_PSI_SIGNIFICANT_THRESHOLD = 0.25
DEFAULT_MIN_SAMPLES_FOR_DRIFT = 20
DEFAULT_EVENT_FREQUENCY_RATIO_THRESHOLD = 3.0
DEFAULT_PERFORMANCE_DRIFT_THRESHOLD = 0.15  # absolute drop in a metric that triggers review


def compute_psi(baseline: list[float], current: list[float], *, n_bins: int = 10) -> float | None:
    """Population Stability Index between two numeric samples — bins are
    the baseline sample's own quantiles (so bin membership is meaningful
    for the baseline by construction), then each sample's proportion per
    bin is compared. `None` if either sample is too small to bin
    meaningfully."""
    if len(baseline) < DEFAULT_MIN_SAMPLES_FOR_DRIFT or len(current) < DEFAULT_MIN_SAMPLES_FOR_DRIFT:
        return None

    sorted_baseline = sorted(baseline)
    edges = [sorted_baseline[int(q * (len(sorted_baseline) - 1))] for q in (i / n_bins for i in range(1, n_bins))]
    edges = sorted(set(edges))
    if not edges:
        return None  # a constant baseline can't be usefully binned

    def _bin_counts(values: list[float]) -> list[int]:
        counts = [0] * (len(edges) + 1)
        for v in values:
            i = 0
            while i < len(edges) and v > edges[i]:
                i += 1
            counts[i] += 1
        return counts

    baseline_counts = _bin_counts(baseline)
    current_counts = _bin_counts(current)
    psi = 0.0
    for b_count, c_count in zip(baseline_counts, current_counts):
        b_pct = max(b_count / len(baseline), 1e-6)
        c_pct = max(c_count / len(current), 1e-6)
        psi += (c_pct - b_pct) * math.log(c_pct / b_pct)
    return round(psi, 6)


def _psi_status(psi: float | None) -> str:
    if psi is None:
        return "INSUFFICIENT_DATA"
    if psi >= DEFAULT_PSI_SIGNIFICANT_THRESHOLD:
        return "SIGNIFICANT_SHIFT"
    if psi >= DEFAULT_PSI_MODERATE_THRESHOLD:
        return "MODERATE_SHIFT"
    return "STABLE"


@dataclass
class FeatureDriftResult:
    feature_name: str
    baseline_mean: float | None
    current_mean: float | None
    baseline_stdev: float | None
    current_stdev: float | None
    psi: float | None
    status: str


@dataclass
class FeatureDriftReport:
    results: list[FeatureDriftResult] = field(default_factory=list)

    @property
    def shifted_features(self) -> list[FeatureDriftResult]:
        return [r for r in self.results if r.status in ("MODERATE_SHIFT", "SIGNIFICANT_SHIFT")]


def compute_feature_drift(
    baseline_vectors: list[dict[str, float | None]],
    current_vectors: list[dict[str, float | None]],
    *,
    feature_names: tuple[str, ...] = FEATURE_NAMES,
) -> FeatureDriftReport:
    """`baseline_vectors` is typically the model's own training feature
    vectors; `current_vectors` is a recent sample of production feature
    snapshots, vectorized the same way (`app/predictions/vectorization.py::vectorize()`)."""
    results: list[FeatureDriftResult] = []
    for name in feature_names:
        baseline_values = [v[name] for v in baseline_vectors if v.get(name) is not None]
        current_values = [v[name] for v in current_vectors if v.get(name) is not None]
        psi = compute_psi(baseline_values, current_values)
        results.append(
            FeatureDriftResult(
                feature_name=name,
                baseline_mean=statistics.fmean(baseline_values) if baseline_values else None,
                current_mean=statistics.fmean(current_values) if current_values else None,
                baseline_stdev=statistics.pstdev(baseline_values) if len(baseline_values) > 1 else None,
                current_stdev=statistics.pstdev(current_values) if len(current_values) > 1 else None,
                psi=psi,
                status=_psi_status(psi),
            )
        )
    return FeatureDriftReport(results=results)


@dataclass
class DataDriftResult:
    baseline_record_count: int
    current_record_count: int
    baseline_period_days: int
    current_period_days: int
    baseline_daily_rate: float | None
    current_daily_rate: float | None
    frequency_ratio: float | None
    status: str  # STABLE | SHIFTED | INSUFFICIENT_DATA


def compute_data_drift(
    *,
    baseline_record_count: int,
    baseline_period_days: int,
    current_record_count: int,
    current_period_days: int,
    ratio_threshold: float = DEFAULT_EVENT_FREQUENCY_RATIO_THRESHOLD,
) -> DataDriftResult:
    """A deliberately simple event-frequency comparison — records/day in
    a baseline period versus a current period. Not a claim about *why*
    the rate changed (see `app/predictions/spec.py` item 5's
    reporting-bias note) — only that it changed enough to flag."""
    baseline_rate = (baseline_record_count / baseline_period_days) if baseline_period_days else None
    current_rate = (current_record_count / current_period_days) if current_period_days else None
    if baseline_rate is None or current_rate is None or baseline_rate == 0:
        return DataDriftResult(
            baseline_record_count=baseline_record_count, current_record_count=current_record_count,
            baseline_period_days=baseline_period_days, current_period_days=current_period_days,
            baseline_daily_rate=baseline_rate, current_daily_rate=current_rate,
            frequency_ratio=None, status="INSUFFICIENT_DATA",
        )
    ratio = current_rate / baseline_rate
    status = "SHIFTED" if (ratio >= ratio_threshold or ratio <= 1 / ratio_threshold) else "STABLE"
    return DataDriftResult(
        baseline_record_count=baseline_record_count, current_record_count=current_record_count,
        baseline_period_days=baseline_period_days, current_period_days=current_period_days,
        baseline_daily_rate=round(baseline_rate, 4), current_daily_rate=round(current_rate, 4),
        frequency_ratio=round(ratio, 4), status=status,
    )


def check_model_for_review(
    db: Session,
    model: ModelRegistryEntry,
    *,
    reason: ReviewFlagReason,
    metric_name: str,
    historical_value: float | None,
    current_value: float | None,
    threshold: float = DEFAULT_PERFORMANCE_DRIFT_THRESHOLD,
    detail: str | None = None,
) -> ModelReviewFlag | None:
    """Flags `model` for human review if `current_value` has degraded
    from `historical_value` by more than `threshold` (absolute) — never
    retrains, redeploys, or retires anything itself (milestone item 32).
    Returns `None` (and writes nothing) when the values are too close to
    warrant a flag, or either value is unavailable to compare."""
    if historical_value is None or current_value is None:
        return None
    if abs(historical_value - current_value) < threshold:
        return None

    flag = ModelReviewFlag(
        organization_id=model.organization_id,
        model_id=model.id,
        reason=reason.value,
        metric_name=metric_name,
        historical_value=historical_value,
        current_value=current_value,
        detail=detail,
        status="OPEN",
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)

    audit_service.log(
        db,
        action=AuditAction.MODEL_REVIEW_REQUIRED,
        resource_type="model_review_flag",
        resource_id=flag.id,
        organization_id=model.organization_id,
        metadata={
            "model_id": str(model.id), "reason": reason.value, "metric_name": metric_name,
            "historical_value": historical_value, "current_value": current_value,
        },
    )
    return flag


def acknowledge_review_flag(db: Session, flag: ModelReviewFlag, *, user_id: uuid.UUID) -> ModelReviewFlag:
    flag.status = "ACKNOWLEDGED"
    flag.acknowledged_at = datetime.now(timezone.utc)
    flag.acknowledged_by_user_id = user_id
    db.commit()
    db.refresh(flag)
    audit_service.log(
        db,
        action=AuditAction.MODEL_REVIEW_ACKNOWLEDGED,
        resource_type="model_review_flag",
        resource_id=flag.id,
        organization_id=flag.organization_id,
        user_id=user_id,
        metadata={"model_id": str(flag.model_id)},
    )
    return flag


__all__ = [
    "DEFAULT_EVENT_FREQUENCY_RATIO_THRESHOLD",
    "DEFAULT_PERFORMANCE_DRIFT_THRESHOLD",
    "DEFAULT_PSI_MODERATE_THRESHOLD",
    "DEFAULT_PSI_SIGNIFICANT_THRESHOLD",
    "DataDriftResult",
    "FeatureDriftReport",
    "FeatureDriftResult",
    "acknowledge_review_flag",
    "check_model_for_review",
    "compute_data_drift",
    "compute_feature_drift",
    "compute_psi",
]
