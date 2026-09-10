"""Leading/lagging indicators — milestone item 21. Pure unit tests."""

from datetime import datetime, timezone

from app.intelligence.features import compute_feature_set
from app.intelligence.indicators import compute_indicators
from tests.intelligence_test_helpers import make_safety_event

AS_OF = datetime(2026, 6, 30, tzinfo=timezone.utc)


def test_indicators_are_categorized_leading_or_lagging():
    features = compute_feature_set(
        [make_safety_event(event_type="INCIDENT"), make_safety_event(event_type="NEAR_MISS")],
        window_days=30, as_of=AS_OF,
    )
    indicators = compute_indicators(features)
    by_name = {i.name: i.category for i in indicators}
    assert by_name["incident_count"] == "LAGGING"
    assert by_name["near_miss_count"] == "LEADING"


def test_indicators_never_reinvent_their_own_value_they_wrap_the_feature():
    features = compute_feature_set([make_safety_event(event_type="INCIDENT")], window_days=30, as_of=AS_OF)
    indicators = compute_indicators(features)
    incident_indicator = next(i for i in indicators if i.name == "incident_count")
    assert incident_indicator.feature is features["incident_count"]


def test_indicators_are_never_labeled_a_predictive_probability():
    """Checked structurally, over the actual code (not the module's own
    prose docstring, which explains this rule using the word itself):
    `compute_indicators` never touches anything called `probability`."""
    import inspect

    from app.intelligence.indicators import compute_indicators

    source = inspect.getsource(compute_indicators)
    assert "probability" not in source.lower()
