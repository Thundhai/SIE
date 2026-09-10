"""Feature engineering — milestone items 19-20. Pure unit tests over
`compute_feature_set()` — no database.
"""

from datetime import datetime, timezone

import pytest

from app.intelligence.enums import DataSufficiency
from app.intelligence.features import compute_feature_set
from tests.intelligence_test_helpers import make_safety_event

AS_OF = datetime(2026, 6, 30, tzinfo=timezone.utc)


def test_event_frequency_counts_are_computed_per_domain():
    events = [
        make_safety_event(event_type="INCIDENT"),
        make_safety_event(event_type="INCIDENT"),
        make_safety_event(event_type="NEAR_MISS"),
        make_safety_event(event_type="OBSERVATION"),
    ]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["incident_count"].value == 2
    assert features["near_miss_count"].value == 1
    assert features["observation_count"].value == 1
    assert features["audit_count"].value == 0  # a legitimate, meaningful zero


def test_zero_events_of_a_domain_is_a_real_zero_not_none():
    features = compute_feature_set([], window_days=30, as_of=AS_OF)
    assert features["incident_count"].value == 0
    assert features["incident_count"].data_quality == DataSufficiency.INSUFFICIENT_DATA.value


def test_avg_severity_averages_only_incidents_and_near_misses_with_a_recognized_severity():
    events = [
        make_safety_event(event_type="INCIDENT", severity="LOW"),
        make_safety_event(event_type="INCIDENT", severity="CRITICAL"),
        make_safety_event(event_type="NEAR_MISS", severity=None),  # excluded -- no severity
        make_safety_event(event_type="OBSERVATION", severity="HIGH"),  # excluded -- wrong domain
    ]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["avg_severity"].value == (1 + 4) / 2


def test_avg_severity_is_none_with_reason_when_no_severity_data_exists():
    events = [make_safety_event(event_type="INCIDENT", severity=None)]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["avg_severity"].value is None
    assert features["avg_severity"].unavailable_reason == "NO_SEVERITY_DATA"


def test_high_potential_and_severe_event_counts():
    events = [
        make_safety_event(event_type="INCIDENT", potential_severity="HIGH"),
        make_safety_event(event_type="NEAR_MISS", potential_severity="CRITICAL"),
        make_safety_event(event_type="INCIDENT", potential_severity="LOW"),
        make_safety_event(event_type="INCIDENT", severity="CRITICAL"),
    ]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["high_potential_event_count"].value == 2
    assert features["severe_event_count"].value == 1


def test_corrective_action_closure_rate_and_overdue_count():
    events = [
        make_safety_event(event_type="CORRECTIVE_ACTION", status="OPEN"),
        make_safety_event(event_type="CORRECTIVE_ACTION", status="OVERDUE"),
        make_safety_event(event_type="CORRECTIVE_ACTION", status="OVERDUE"),
        make_safety_event(event_type="CORRECTIVE_ACTION", status="CLOSED"),
    ]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["open_action_count"].value == 1
    assert features["overdue_action_count"].value == 2
    assert features["action_closure_rate"].value == 1 / 4


def test_action_closure_rate_is_none_when_no_action_status_data_exists():
    features = compute_feature_set([], window_days=30, as_of=AS_OF)
    assert features["action_closure_rate"].value is None
    assert features["action_closure_rate"].unavailable_reason == "NO_ACTION_STATUS_DATA"


def test_recurring_action_count_matches_subtype_containing_recurring():
    events = [
        make_safety_event(event_type="CORRECTIVE_ACTION", event_subtype="recurring_action"),
        make_safety_event(event_type="CORRECTIVE_ACTION", event_subtype="action_opened"),
    ]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["recurring_action_count"].value == 1


def test_training_completion_rate_and_expired_certification_count():
    events = [
        make_safety_event(event_type="TRAINING", status="COMPLETED"),
        make_safety_event(event_type="TRAINING", status="COMPLETED"),
        make_safety_event(event_type="TRAINING", status="OVERDUE"),
        make_safety_event(event_type="TRAINING", status="EXPIRED"),
    ]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["training_completion_rate"].value == pytest.approx(2 / 3, abs=1e-3)
    assert features["expired_certification_count"].value == 1


def test_equipment_features():
    events = [
        make_safety_event(event_type="EQUIPMENT", event_subtype="failure"),
        make_safety_event(event_type="EQUIPMENT", event_subtype="failure"),
        make_safety_event(event_type="EQUIPMENT", event_subtype="inspection", status="OVERDUE"),
        make_safety_event(event_type="EQUIPMENT", event_subtype="maintenance", status="OVERDUE"),
    ]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["equipment_failure_count"].value == 2
    assert features["overdue_equipment_inspection_count"].value == 1
    assert features["maintenance_overdue_count"].value == 1


def test_operational_context_features():
    events = [
        make_safety_event(contractor="Acme Rigging", activity="lifting", location="North Yard"),
        make_safety_event(contractor="Acme Rigging", activity="welding", location="North Yard"),
        make_safety_event(contractor="Bolt Contractors", activity="welding", location="South Yard"),
    ]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert features["contractor_activity_count"].value == 2
    assert features["activity_diversity"].value == 2
    assert features["location_concentration"].value == pytest.approx(2 / 3, abs=1e-3)  # North Yard: 2 of 3


def test_exposure_normalized_features_use_the_supplied_exposure_hours():
    events = [make_safety_event(event_type="INCIDENT") for _ in range(10)]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF, exposure_hours=10000.0)
    assert features["exposure_hours"].value == 10000.0
    assert features["incidents_per_100000_hours"].value == 100.0


def test_exposure_normalized_features_are_unavailable_without_exposure_data():
    events = [make_safety_event(event_type="INCIDENT") for _ in range(10)]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF, exposure_hours=None)
    assert features["incidents_per_100000_hours"].value is None
    assert features["incidents_per_100000_hours"].unavailable_reason == "EXPOSURE_DATA_UNAVAILABLE"


def test_every_feature_records_calculation_version_and_as_of():
    events = [make_safety_event(event_type="INCIDENT")]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF, entity_type="site")
    for feature in features.values():
        assert feature.calculation_version == "feature-v1"
        assert feature.as_of == AS_OF
        assert feature.window_days == 30
        assert feature.entity_type == "site"


def test_source_event_ids_are_traceable_back_to_the_original_events():
    """Milestone item 19: 'source events' -- proves the
    signal -> feature -> event provenance chain the README demonstrates."""
    events = [make_safety_event(event_type="INCIDENT") for _ in range(3)]
    features = compute_feature_set(events, window_days=30, as_of=AS_OF)
    assert set(features["incident_count"].source_event_ids) == {e.id for e in events}
