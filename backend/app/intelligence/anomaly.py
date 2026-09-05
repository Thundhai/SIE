"""Explainable anomaly detection foundation — milestone item 24. A
z-score against a rolling baseline mean/standard deviation — chosen
specifically because it is fully explainable (every number in
`AnomalyResult` is directly inspectable, nothing is a learned weight):

    current period value
        -> baseline period values (e.g. the preceding N periods)
        -> mean, population standard deviation
        -> z = (current - mean) / stdev
        -> |z| >= threshold -> ANOMALOUS

No deep learning, no learned model — see the milestone's own instruction
("Do not implement deep-learning anomaly detection yet").

**`direction` (SIE Milestone 23: Enterprise Intelligence Explainability
& Anomaly Foundation v0.1, item 5) — additive, non-breaking.** Every
existing caller of `detect_anomaly()`
(`app/predictions/feature_snapshot_service.py`,
`app/validation/enterprise_dataset_validation.py`,
`tests/evaluation/calibration_harness.py`) reads only `.status`/
`.z_score`/`.calculation_version` and is unaffected by this new field.
`direction` answers "which way", independent of `status` ("how
unusual") — `ABOVE_BASELINE`/`BELOW_BASELINE` is reported whenever the
current value differs from the baseline mean, *whether or not* that
difference clears the anomaly threshold (a value slightly above the
mean is still meaningfully `ABOVE_BASELINE`, even when classified
`NORMAL`) — see `app/intelligence/enums.py::AnomalyDirection`'s own
docstring for why this is kept distinct from `status`.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.core.config import settings
from app.intelligence.enums import AnomalyDirection, AnomalyStatus

ANOMALY_CALCULATION_VERSION = "anomaly-v1"
ANOMALY_METHOD = "z-score against rolling baseline mean/population-standard-deviation"


def _direction(current_value: float, mean: float) -> AnomalyDirection:
    if current_value > mean:
        return AnomalyDirection.ABOVE_BASELINE
    if current_value < mean:
        return AnomalyDirection.BELOW_BASELINE
    return AnomalyDirection.NONE


@dataclass
class AnomalyResult:
    status: str  # AnomalyStatus value
    current_value: float
    baseline_mean: float | None = None
    baseline_stdev: float | None = None
    z_score: float | None = None
    baseline_period_count: int = 0
    calculation_version: str = ANOMALY_CALCULATION_VERSION
    method: str = ANOMALY_METHOD
    direction: str = AnomalyDirection.NONE.value  # AnomalyDirection value


def detect_anomaly(
    current_value: float,
    baseline_values: list[float],
    *,
    min_baseline_periods: int | None = None,
    z_threshold: float | None = None,
) -> AnomalyResult:
    min_baseline_periods = (
        min_baseline_periods
        if min_baseline_periods is not None
        else settings.INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS
    )
    z_threshold = z_threshold if z_threshold is not None else settings.INTELLIGENCE_ANOMALY_Z_SCORE_THRESHOLD

    if len(baseline_values) < min_baseline_periods:
        return AnomalyResult(
            status=AnomalyStatus.INSUFFICIENT_DATA.value,
            current_value=current_value,
            baseline_period_count=len(baseline_values),
        )

    mean = statistics.fmean(baseline_values)
    stdev = statistics.pstdev(baseline_values)

    if stdev == 0:
        # A constant baseline -- any deviation at all is meaningful; no
        # deviation is unremarkable. z-score is undefined (division by
        # zero), not fabricated as 0 or infinity.
        status = AnomalyStatus.ANOMALOUS if current_value != mean else AnomalyStatus.NORMAL
        return AnomalyResult(
            status=status.value,
            current_value=current_value,
            baseline_mean=mean,
            baseline_stdev=0.0,
            z_score=None,
            baseline_period_count=len(baseline_values),
            direction=_direction(current_value, mean).value,
        )

    z = (current_value - mean) / stdev
    status = AnomalyStatus.ANOMALOUS if abs(z) >= z_threshold else AnomalyStatus.NORMAL
    return AnomalyResult(
        status=status.value,
        current_value=current_value,
        baseline_mean=round(mean, 4),
        baseline_stdev=round(stdev, 4),
        z_score=round(z, 4),
        baseline_period_count=len(baseline_values),
        direction=_direction(current_value, mean).value,
    )
