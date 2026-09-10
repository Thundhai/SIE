"""Trend analysis — milestone item 23. Pure unit tests over
`classify_trend()`.
"""

from datetime import datetime, timedelta, timezone

from app.intelligence.enums import TrendDirection
from app.intelligence.trends import TrendPeriod, classify_trend

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _periods(values: list[float | None]) -> list[TrendPeriod]:
    return [
        TrendPeriod(period_start=_START + timedelta(days=30 * i), period_end=_START + timedelta(days=30 * (i + 1)), value=v)
        for i, v in enumerate(values)
    ]


def test_the_milestones_own_worked_example_is_increasing():
    """incident_count: January = 4, February = 6, March = 11."""
    result = classify_trend("incident_count", _periods([4, 6, 11]))
    assert result.direction == TrendDirection.INCREASING.value


def test_a_clearly_decreasing_series_is_classified_decreasing():
    result = classify_trend("incident_count", _periods([11, 6, 4]))
    assert result.direction == TrendDirection.DECREASING.value


def test_a_flat_series_is_classified_stable():
    result = classify_trend("incident_count", _periods([5, 5, 5, 5]))
    assert result.direction == TrendDirection.STABLE.value


def test_fewer_than_the_minimum_periods_is_insufficient_data():
    result = classify_trend("incident_count", _periods([4, 6]), min_periods=3)
    assert result.direction == TrendDirection.INSUFFICIENT_DATA.value


def test_periods_with_no_value_are_excluded_from_the_calculation():
    result = classify_trend("incident_count", _periods([4, None, 6, 11]), min_periods=3)
    # 3 non-empty periods remain -- enough to classify.
    assert result.direction != TrendDirection.INSUFFICIENT_DATA.value


def test_the_method_is_documented_not_hidden():
    result = classify_trend("incident_count", _periods([4, 6, 11]))
    assert "least-squares" in result.method.lower()
    assert result.calculation_version == "trend-v1"


def test_small_fluctuations_relative_to_a_large_baseline_do_not_overfit_to_a_trend():
    """Milestone item 23: 'do not overfit trends.' A few points of noise
    around a large, stable baseline (50 +/- 1) must not be reported as a
    trend just because the raw slope is technically nonzero -- the
    *relative* slope is what matters."""
    result = classify_trend("incident_count", _periods([50, 51, 49, 50]))
    assert result.direction == TrendDirection.STABLE.value
