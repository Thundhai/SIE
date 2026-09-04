"""SIE Milestone 22: Enterprise Intelligence & Risk Analytics Foundation
v0.1, items 9-10 — `app/intelligence/risk_score.py`. Pure-function tests
(no database) constructing `EnterpriseIndicator`/`EnterpriseTrendResult`/
`RecurrencePattern` dataclasses directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.intelligence.enterprise_indicators import EnterpriseIndicator
from app.intelligence.enterprise_trend import EnterpriseTrendResult
from app.intelligence.recurrence import RecurrencePattern
from app.intelligence.risk_score import classify_risk_score, compute_risk_score

AS_OF = datetime(2026, 7, 1, tzinfo=timezone.utc)
WINDOW_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PREV_START = datetime(2026, 5, 2, tzinfo=timezone.utc)


def _indicator(key, value, previous_value=0, **overrides) -> EnterpriseIndicator:
    defaults = dict(
        key=key, label=key, value=value, category="LAGGING",
        period_start=WINDOW_START, period_end=AS_OF, window_days=30,
        previous_value=previous_value, absolute_change=value - previous_value,
    )
    defaults.update(overrides)
    return EnterpriseIndicator(**defaults)


def _base_indicators(**overrides) -> list[EnterpriseIndicator]:
    values = dict(
        incident_count=0, severity_high_count=0, severity_critical_count=0,
        near_miss_count=0, observation_count=0, inspection_count=0,
    )
    values.update(overrides)
    return [_indicator(k, v) for k, v in values.items()]


def _trend(classification="STABLE", current=0, previous=0, pct=0.0) -> EnterpriseTrendResult:
    return EnterpriseTrendResult(
        classification=classification, metric="incident_count", current_value=current,
        previous_value=previous, absolute_change=current - previous, percentage_change=pct,
        current_period_start=WINDOW_START, current_period_end=AS_OF,
        previous_period_start=PREV_START, previous_period_end=WINDOW_START,
    )


def _pattern(classification) -> RecurrencePattern:
    return RecurrencePattern(
        pattern_key="k", scope="site:x", site_id=uuid.uuid4(), site_label="Site",
        event_type="INCIDENT", event_subtype=None, count=3, first_seen=AS_OF, last_seen=AS_OF,
        window_start=WINDOW_START, window_end=AS_OF, window_days=30, classification=classification,
    )


def test_score_is_bounded_0_to_100():
    indicators = _base_indicators(
        incident_count=50, severity_high_count=20, severity_critical_count=20,
        near_miss_count=0, observation_count=0, inspection_count=0,
    )
    patterns = [_pattern("HIGH_RECURRENCE") for _ in range(10)]
    trend = _trend("DETERIORATING", current=50, previous=5, pct=900.0)
    result = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=patterns, event_count=50)
    assert result.score is not None
    assert 0.0 <= result.score <= 100.0


def test_deterministic_same_input_same_output():
    indicators = _base_indicators(incident_count=6, severity_high_count=2)
    trend = _trend("DETERIORATING", current=6, previous=3, pct=100.0)
    patterns = [_pattern("WATCH")]
    r1 = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=patterns, event_count=10)
    r2 = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=patterns, event_count=10)
    assert r1.score == r2.score
    assert r1.classification == r2.classification
    assert [c.contribution for c in r1.components] == [c.contribution for c in r2.components]


def test_component_normalized_weights_sum_to_100_when_all_present():
    indicators = _base_indicators(incident_count=6, severity_high_count=2, near_miss_count=3, observation_count=2, inspection_count=1)
    trend = _trend("DETERIORATING", current=6, previous=3, pct=100.0)
    patterns = [_pattern("RECURRING")]
    result = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=patterns, event_count=10)
    assert len(result.components) == 5  # all 5 documented components computable
    assert round(sum(c.normalized_weight for c in result.components), 1) == 100.0


def test_component_contribution_sum_equals_score():
    indicators = _base_indicators(incident_count=6, severity_high_count=2)
    trend = _trend("DETERIORATING", current=6, previous=3, pct=100.0)
    patterns = [_pattern("RECURRING")]
    result = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=patterns, event_count=10)
    assert round(sum(c.contribution for c in result.components), 1) == result.score


def test_omitted_component_reweights_the_rest_to_still_sum_to_100():
    # No leading activity and no lagging activity at all -> imbalance
    # component omitted; trend insufficient -> trend component omitted.
    indicators = _base_indicators(incident_count=3, severity_high_count=1, near_miss_count=0, observation_count=0, inspection_count=0)
    trend = _trend("INSUFFICIENT_DATA", current=3, previous=0, pct=None)
    result = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=[], event_count=10)
    present_keys = {c.key for c in result.components}
    assert "deteriorating_trend" not in present_keys
    assert "leading_lagging_imbalance" in present_keys  # incident_count=3 > 0, so lagging alone is enough
    assert round(sum(c.normalized_weight for c in result.components), 1) == 100.0


def test_score_classification_bands():
    assert classify_risk_score(0.0).value == "LOW"
    assert classify_risk_score(24.9).value == "LOW"
    assert classify_risk_score(25.0).value == "MODERATE"
    assert classify_risk_score(49.9).value == "MODERATE"
    assert classify_risk_score(50.0).value == "HIGH"
    assert classify_risk_score(74.9).value == "HIGH"
    assert classify_risk_score(75.0).value == "CRITICAL"
    assert classify_risk_score(100.0).value == "CRITICAL"


def test_insufficient_data_produces_no_score():
    indicators = _base_indicators(incident_count=1)
    trend = _trend("INSUFFICIENT_DATA", current=1, previous=0, pct=None)
    result = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=[], event_count=1)
    assert result.score is None
    assert result.classification is None
    assert result.insufficient_data_reason is not None
    assert result.components == []


def test_zero_activity_produces_a_real_zero_score_not_none_when_event_count_sufficient():
    # event_count sufficient (e.g. many AUDIT events) but zero incidents/
    # near-misses/observations/inspections at all -- severity and
    # frequency components are still computable (both legitimately 0),
    # only imbalance is omitted (0/0 is genuinely undefined).
    indicators = _base_indicators()
    trend = _trend("STABLE", current=0, previous=0, pct=0.0)
    result = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=[], event_count=10)
    assert result.score == 0.0
    assert result.classification == "LOW"
    present_keys = {c.key for c in result.components}
    assert "leading_lagging_imbalance" not in present_keys
