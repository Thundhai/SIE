"""Correlation vs. causation — milestone items 26/54. Pure unit tests.

Extended by SIE Milestone 24: Enterprise Intelligence Pattern &
Correlation Foundation v0.1, items 5-7/17 (classification vocabulary,
threshold boundaries, statistical safeguards)."""

from app.intelligence.association import _classify_association, detect_association
from app.intelligence.enums import AssociationClassification


def test_two_variables_increasing_together_is_reported_as_association_observed():
    """Milestone item 54's own scenario: overtime and incidents both
    increasing across synthetic periods."""
    overtime_hours = [10, 20, 30, 40, 50]
    incident_counts = [1, 2, 3, 4, 5]
    result = detect_association(overtime_hours, incident_counts)
    assert result.outcome == "ASSOCIATION_OBSERVED"
    assert result.correlation_coefficient == 1.0


def test_the_result_never_claims_causation():
    """There is no CAUSATION_CONFIRMED outcome at all -- checked
    structurally over the actual function body (not this module's own
    prose docstring, which explains the rule using the term itself)."""
    import inspect

    from app.intelligence.association import detect_association

    source = inspect.getsource(detect_association)
    assert "CAUSATION_CONFIRMED" not in source
    assert "causation" not in source.lower()


def test_unrelated_series_report_no_association_observed():
    a = [1, 2, 3, 4, 5]
    b = [5, 2, 8, 1, 9]
    result = detect_association(a, b, threshold=0.9)
    assert result.outcome == "NO_ASSOCIATION_OBSERVED"


def test_too_few_periods_is_insufficient_data():
    result = detect_association([1, 2], [1, 2], min_periods=3)
    assert result.outcome == "INSUFFICIENT_DATA"


def test_mismatched_series_lengths_raise_rather_than_silently_misalign():
    import pytest

    with pytest.raises(ValueError):
        detect_association([1, 2, 3], [1, 2])


def test_every_result_carries_the_correlation_not_causation_note():
    result = detect_association([1, 2, 3], [1, 2, 3])
    assert "not causation" in result.note.lower()


# --- Classification (SIE Milestone 24, item 5) ---------------------------


def test_perfect_positive_correlation_is_strong_positive():
    result = detect_association([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
    assert result.correlation_coefficient == 1.0
    assert result.classification == AssociationClassification.STRONG_POSITIVE.value


def test_perfect_negative_correlation_is_strong_negative():
    result = detect_association([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert result.correlation_coefficient == -1.0
    assert result.classification == AssociationClassification.STRONG_NEGATIVE.value


def test_strong_positive_correlation_below_perfect_is_still_strong_positive():
    result = detect_association([1, 2, 3, 4, 5, 6], [1, 3, 2, 5, 4, 7])
    assert result.correlation_coefficient == 0.8908
    assert result.classification == AssociationClassification.STRONG_POSITIVE.value


def test_moderate_positive_correlation_is_classified_moderate_not_strong():
    result = detect_association([1, 2, 3, 4, 5, 6], [3, 1, 4, 2, 6, 5])
    assert result.correlation_coefficient == 0.6571
    assert result.classification == AssociationClassification.MODERATE_POSITIVE.value


def test_weak_or_no_association_is_classified_weak():
    result = detect_association([1, 2, 3, 4, 5, 6], [4, 1, 6, 2, 5, 3])
    assert result.correlation_coefficient == 0.0857
    assert result.classification == AssociationClassification.WEAK.value


def test_moderate_negative_correlation_is_classified_moderate_not_strong():
    result = detect_association([1, 2, 3, 4, 5, 6], [5, 6, 2, 4, 1, 3])
    assert result.correlation_coefficient == -0.6571
    assert result.classification == AssociationClassification.MODERATE_NEGATIVE.value


def test_strong_negative_correlation_below_perfect_is_still_strong_negative():
    result = detect_association([1, 2, 3, 4, 5, 6], [6, 4, 5, 2, 3, 1])
    assert result.correlation_coefficient == -0.8857
    assert result.classification == AssociationClassification.STRONG_NEGATIVE.value


def test_insufficient_data_classification_matches_insufficient_outcome():
    result = detect_association([1, 2], [1, 2], min_periods=3)
    assert result.outcome == "INSUFFICIENT_DATA"
    assert result.classification == AssociationClassification.INSUFFICIENT_DATA.value


def test_zero_variance_series_is_insufficient_data_not_a_fabricated_classification():
    """Milestone item 6: never NaN/Infinity -- a constant series makes the
    correlation coefficient mathematically undefined, so both `outcome`
    and `classification` become the explicit, governed INSUFFICIENT_DATA
    state, never a fabricated correlation of 0 or an error."""
    result = detect_association([5, 5, 5, 5, 5], [1, 2, 3, 4, 5])
    assert result.correlation_coefficient is None
    assert result.outcome == "INSUFFICIENT_DATA"
    assert result.classification == AssociationClassification.INSUFFICIENT_DATA.value


def test_identical_series_are_perfectly_correlated():
    result = detect_association([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert result.correlation_coefficient == 1.0
    assert result.classification == AssociationClassification.STRONG_POSITIVE.value


def test_inverse_series_are_perfectly_negatively_correlated():
    result = detect_association([1, 2, 3, 4, 5], [-1, -2, -3, -4, -5])
    assert result.correlation_coefficient == -1.0
    assert result.classification == AssociationClassification.STRONG_NEGATIVE.value


def test_repeated_calculation_over_the_same_series_is_deterministic():
    a, b = [2, 3, 5, 7, 4, 6], [1, 4, 6, 8, 3, 7]
    first = detect_association(a, b)
    second = detect_association(a, b)
    assert first == second


def test_a_correlation_coefficient_is_never_nan_or_infinite():
    import math

    for a, b in (([5, 5, 5], [1, 2, 3]), ([1, 2, 3], [5, 5, 5]), ([1, 2], [1, 2])):
        result = detect_association(a, b, min_periods=2)
        if result.correlation_coefficient is not None:
            assert math.isfinite(result.correlation_coefficient)


# --- Classification threshold boundaries (item 5/17 -- exact, pure
# unit tests over `_classify_association()` itself; constructing integer
# series that land on an *exact* r boundary is not generally possible,
# so the boundary itself is tested directly, the same way
# `tests/test_intelligence_anomaly.py` tests `detect_anomaly()`'s
# z-score threshold at its own exact boundary). ------------------------


def test_classification_just_below_the_strong_threshold_is_moderate_positive():
    assert _classify_association(0.69) == AssociationClassification.MODERATE_POSITIVE


def test_classification_exactly_at_the_strong_threshold_is_strong_positive():
    assert _classify_association(0.7) == AssociationClassification.STRONG_POSITIVE


def test_classification_just_below_the_moderate_threshold_is_weak():
    assert _classify_association(0.39) == AssociationClassification.WEAK


def test_classification_exactly_at_the_moderate_threshold_is_moderate_positive():
    assert _classify_association(0.4) == AssociationClassification.MODERATE_POSITIVE


def test_classification_exactly_at_the_negative_strong_threshold_is_strong_negative():
    assert _classify_association(-0.7) == AssociationClassification.STRONG_NEGATIVE


def test_classification_exactly_at_the_negative_moderate_threshold_is_moderate_negative():
    assert _classify_association(-0.4) == AssociationClassification.MODERATE_NEGATIVE


def test_classification_at_exactly_zero_is_weak():
    assert _classify_association(0.0) == AssociationClassification.WEAK
