"""Anomaly detection foundation — milestone item 24. Pure unit tests over
`detect_anomaly()`.
"""

from app.intelligence.anomaly import detect_anomaly
from app.intelligence.enums import AnomalyStatus


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
