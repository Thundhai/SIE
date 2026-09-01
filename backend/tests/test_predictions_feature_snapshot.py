"""Feature snapshot construction & persistence — milestone items 8-11.
DB-backed (SQLite) tests."""

from datetime import datetime, timedelta, timezone

from app.models.feature_snapshot import FeatureSnapshot
from app.predictions.feature_snapshot_service import (
    compute_feature_set_v1,
    get_or_build_feature_snapshot,
)
from app.predictions.spec import FEATURE_SET_VERSION
from app.predictions.vectorization import FEATURE_NAMES
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _seed_history(db_session, org_id, site_id, *, days_back=200):
    for d in range(0, days_back, 5):
        db_session.add(
            make_safety_event(
                organization_id=org_id, site_id=site_id, event_type="NEAR_MISS",
                event_time=AS_OF - timedelta(days=d), ingestion_time=AS_OF - timedelta(days=d),
            )
        )
    db_session.commit()


def test_feature_set_v1_covers_every_declared_feature_name(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_history(db_session, org.id, site.id)
    feature_set = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert set(feature_set.features.keys()) == set(FEATURE_NAMES)


def test_a_legitimate_zero_count_is_not_confused_with_missing_data(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_history(db_session, org.id, site.id)
    feature_set = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    # No incidents were seeded -- a real, meaningful zero, not None.
    assert feature_set.features["incident_count_30d"].value == 0
    assert feature_set.features["incident_count_30d"].unavailable_reason is None


def test_a_feature_with_no_computable_denominator_is_none_with_a_reason_never_fabricated_as_zero(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    # No CORRECTIVE_ACTION events at all -- overdue_action_rate has
    # nothing to divide.
    feature_set = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert feature_set.features["overdue_action_rate"].value is None
    assert feature_set.features["overdue_action_rate"].unavailable_reason is not None


def test_get_or_build_feature_snapshot_is_idempotent(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_history(db_session, org.id, site.id)

    first = get_or_build_feature_snapshot(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    second = get_or_build_feature_snapshot(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)

    assert first.id == second.id
    count = db_session.query(FeatureSnapshot).count()
    assert count == 1


def test_persisted_snapshot_round_trips_through_json_cleanly(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_history(db_session, org.id, site.id)
    snapshot = get_or_build_feature_snapshot(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert snapshot.feature_set_version == FEATURE_SET_VERSION
    assert isinstance(snapshot.features, dict)
    assert all(isinstance(v, dict) for v in snapshot.features.values())
    # source_event_ids must be JSON-safe strings, not raw UUID objects.
    for entry in snapshot.features.values():
        assert all(isinstance(i, str) for i in entry["source_event_ids"])


def test_a_different_as_of_produces_a_distinct_snapshot(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_history(db_session, org.id, site.id)
    first = get_or_build_feature_snapshot(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    second = get_or_build_feature_snapshot(
        db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF - timedelta(days=30)
    )
    assert first.id != second.id


def test_trend_and_anomaly_features_are_well_defined_with_zero_history(db_session):
    """Zero events in every bucket is a real, computable (flat) trend/
    anomaly baseline -- STABLE/NORMAL, not a fabricated INSUFFICIENT_DATA
    (bucketed_counts() always returns a real, if zero, count per
    period -- see app/intelligence/temporal.py::bucketed_counts())."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    feature_set = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert feature_set.features["incident_trend"].value == "STABLE"
    assert feature_set.features["incident_anomaly"].value == "NORMAL"
