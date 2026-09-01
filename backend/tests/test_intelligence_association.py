"""Correlation vs. causation — milestone items 26/54. Pure unit tests."""

from app.intelligence.association import detect_association


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
