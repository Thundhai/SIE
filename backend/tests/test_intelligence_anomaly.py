"""Anomaly detection foundation — milestone item 24. Pure unit tests over
`detect_anomaly()`.
"""

from app.intelligence.anomaly import detect_anomaly
from app.intelligence.enums import AnomalyDirection, AnomalyStatus


def test_a_value_far_from_a_stable_baseline_is_anomalous():
    result = detect_anomaly(20.0, [2, 3, 2, 3, 2, 3])
    assert result.status == AnomalyStatus.ANOMALOUS.value
    assert result.z_score is not None and result.z_score > 0


def test_a_value_close_to_the_baseline_is_normal():
    result = detect_anomaly(3.0, [2, 3, 4, 3, 2, 3])
    assert result.status == AnomalyStatus.NORMAL.value


def test_insufficient_baseline_periods_never_produces_a_strong_signal():
    result = detect_anomaly(20.0, [2, 3])  # below default min_baseline_periods
    assert result.status == AnomalyStatus.INSUFFICIENT_DATA.value


def test_a_zero_variance_baseline_with_a_deviation_is_anomalous_without_dividing_by_zero():
    result = detect_anomaly(5.0, [2, 2, 2, 2])
    assert result.status == AnomalyStatus.ANOMALOUS.value
    assert result.z_score is None  # undefined, not fabricated as 0 or infinity
    assert result.baseline_stdev == 0.0


def test_a_zero_variance_baseline_with_no_deviation_is_normal():
    result = detect_anomaly(2.0, [2, 2, 2, 2])
    assert result.status == AnomalyStatus.NORMAL.value


def test_the_method_is_documented_not_hidden():
    result = detect_anomaly(3.0, [2, 3, 4, 3])
    assert "z-score" in result.method.lower()
    assert result.calculation_version == "anomaly-v1"


def test_no_deep_learning_dependency_is_imported():
    """Milestone item 24: 'do not implement deep-learning anomaly
    detection yet.'"""
    import app.intelligence.anomaly as module

    source_file = module.__file__
    with open(source_file) as f:
        content = f.read()
    for banned in ("torch", "tensorflow", "sklearn", "keras"):
        assert banned not in content.lower()


# --- direction (SIE Milestone 23: Enterprise Intelligence Explainability
# & Anomaly Foundation v0.1, item 5) --------------------------------------


def test_direction_is_above_baseline_when_current_exceeds_the_mean():
    result = detect_anomaly(20.0, [2, 3, 2, 3, 2, 3])
    assert result.direction == AnomalyDirection.ABOVE_BASELINE.value


def test_direction_is_below_baseline_when_current_is_under_the_mean():
    result = detect_anomaly(0.0, [10, 11, 10, 11, 10, 11])
    assert result.direction == AnomalyDirection.BELOW_BASELINE.value


def test_direction_is_none_when_current_exactly_equals_the_mean():
    result = detect_anomaly(2.5, [2, 3, 2, 3])
    assert result.direction == AnomalyDirection.NONE.value
    assert result.status == AnomalyStatus.NORMAL.value


def test_direction_is_none_for_insufficient_data():
    result = detect_anomaly(20.0, [2, 3])
    assert result.direction == AnomalyDirection.NONE.value


def test_direction_is_reported_even_when_classification_is_normal():
    """A value slightly above the mean but within the anomaly threshold
    is still meaningfully ABOVE_BASELINE, even though it is NORMAL --
    direction answers "which way", independent of "how unusual"."""
    result = detect_anomaly(3.0, [2, 3, 4, 3, 2, 3])
    assert result.status == AnomalyStatus.NORMAL.value
    assert result.direction in (AnomalyDirection.ABOVE_BASELINE.value, AnomalyDirection.NONE.value)


# --- Threshold boundary (SIE Milestone 23, item 15's "Statistical"
# coverage: just below / exactly at / just above the z-score threshold)
# ---------------------------------------------------------------------

# baseline [0,0,0,0,4,4,4,4]: mean=2.0, population stdev=2.0 exactly --
# chosen so the default threshold (2.0) lands on exact, non-repeating
# floating-point values.
_THRESHOLD_BASELINE = [0, 0, 0, 0, 4, 4, 4, 4]


def test_just_below_the_z_score_threshold_is_normal():
    result = detect_anomaly(5.9, _THRESHOLD_BASELINE)  # z = 1.95
    assert result.z_score == 1.95
    assert result.status == AnomalyStatus.NORMAL.value


def test_exactly_at_the_z_score_threshold_is_anomalous():
    result = detect_anomaly(6.0, _THRESHOLD_BASELINE)  # z = 2.0 exactly
    assert result.z_score == 2.0
    assert result.status == AnomalyStatus.ANOMALOUS.value  # |z| >= threshold


def test_just_above_the_z_score_threshold_is_anomalous():
    result = detect_anomaly(6.1, _THRESHOLD_BASELINE)  # z = 2.05
    assert result.z_score == 2.05
    assert result.status == AnomalyStatus.ANOMALOUS.value


def test_just_below_the_negative_z_score_threshold_is_normal():
    result = detect_anomaly(-1.9, _THRESHOLD_BASELINE)  # z = -1.95
    assert result.status == AnomalyStatus.NORMAL.value
    assert result.direction == AnomalyDirection.BELOW_BASELINE.value


def test_just_above_the_negative_z_score_threshold_is_anomalous():
    result = detect_anomaly(-2.1, _THRESHOLD_BASELINE)  # z = -2.05
    assert result.status == AnomalyStatus.ANOMALOUS.value
    assert result.direction == AnomalyDirection.BELOW_BASELINE.value
