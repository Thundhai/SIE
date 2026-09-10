"""Trend analysis — milestone item 23. A documented, explainable
statistical method (never a black box, never overfit to a handful of
points): ordinary least-squares linear regression over period-bucketed
values, classified against a relative-slope threshold.

    period buckets (e.g. incident_count per calendar month)
        -> least-squares slope
        -> slope / mean(values) ("relative slope")
        -> compare to settings.INTELLIGENCE_TREND_SLOPE_THRESHOLD
        -> INCREASING / DECREASING / STABLE / INSUFFICIENT_DATA
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime

from app.core.config import settings
from app.intelligence.enums import TrendDirection

TREND_CALCULATION_VERSION = "trend-v1"
TREND_METHOD = "ordinary least-squares linear regression on period-bucketed values"


@dataclass(frozen=True)
class TrendPeriod:
    period_start: datetime
    period_end: datetime
    value: float | None


@dataclass
class TrendResult:
    metric: str
    direction: str  # TrendDirection value
    periods: list[TrendPeriod] = field(default_factory=list)
    slope: float | None = None
    relative_slope: float | None = None
    calculation_version: str = TREND_CALCULATION_VERSION
    method: str = TREND_METHOD


def _least_squares_slope(values: list[float]) -> float:
    n = len(values)
    xs = list(range(n))
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    return numerator / denominator if denominator else 0.0


def classify_trend(
    metric: str,
    periods: list[TrendPeriod],
    *,
    min_periods: int | None = None,
    slope_threshold: float | None = None,
) -> TrendResult:
    min_periods = min_periods if min_periods is not None else settings.INTELLIGENCE_TREND_MIN_PERIODS
    slope_threshold = (
        slope_threshold if slope_threshold is not None else settings.INTELLIGENCE_TREND_SLOPE_THRESHOLD
    )

    non_empty = [p for p in periods if p.value is not None]
    if len(non_empty) < min_periods:
        return TrendResult(metric=metric, direction=TrendDirection.INSUFFICIENT_DATA.value, periods=periods)

    values = [p.value for p in non_empty]
    slope = _least_squares_slope(values)
    mean = statistics.fmean(values)
    relative_slope = (slope / mean) if mean else (0.0 if slope == 0 else float("inf"))

    if relative_slope > slope_threshold:
        direction = TrendDirection.INCREASING
    elif relative_slope < -slope_threshold:
        direction = TrendDirection.DECREASING
    else:
        direction = TrendDirection.STABLE

    return TrendResult(
        metric=metric,
        direction=direction.value,
        periods=periods,
        slope=round(slope, 6),
        relative_slope=round(relative_slope, 6) if relative_slope != float("inf") else None,
    )
