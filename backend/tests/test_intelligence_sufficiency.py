"""Data sufficiency — milestone item 30. Pure unit tests over the exact,
documented thresholds.
"""

from app.intelligence.enums import DataSufficiency
from app.intelligence.sufficiency import classify_data_sufficiency


def test_below_the_limited_threshold_is_insufficient_data(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS", 3)
    assert classify_data_sufficiency(0) == DataSufficiency.INSUFFICIENT_DATA
    assert classify_data_sufficiency(2) == DataSufficiency.INSUFFICIENT_DATA


def test_between_limited_and_sufficient_is_limited_data(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS", 3)
    monkeypatch.setattr("app.core.config.settings.INTELLIGENCE_SUFFICIENT_DATA_MIN_EVENTS", 10)
    assert classify_data_sufficiency(3) == DataSufficiency.LIMITED_DATA
    assert classify_data_sufficiency(9) == DataSufficiency.LIMITED_DATA


def test_at_or_above_the_sufficient_threshold_is_sufficient_data(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.INTELLIGENCE_SUFFICIENT_DATA_MIN_EVENTS", 10)
    assert classify_data_sufficiency(10) == DataSufficiency.SUFFICIENT_DATA
    assert classify_data_sufficiency(1000) == DataSufficiency.SUFFICIENT_DATA


def test_three_days_of_data_is_not_treated_the_same_as_three_years():
    """Milestone item 30's own framing."""
    three_days_of_data = classify_data_sufficiency(2)
    three_years_of_data = classify_data_sufficiency(2000)
    assert three_days_of_data != three_years_of_data
