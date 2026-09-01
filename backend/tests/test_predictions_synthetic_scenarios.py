"""Structural tests for the named synthetic evaluation scenarios —
Model Validation & Governance v0.1, item 42 ("never an unrealistically
perfect synthetic dataset").

These tests check the *shape* of the generated data (event counts,
status mixes, freshness) against what each scenario's own docstring in
`tests/fixtures/predictions/synthetic_training_dataset.py` promises —
never a model's learned performance (that belongs to the model-facing
test files; this file only proves the fixtures themselves are honest
about what they generate).
"""

from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy import func, select

from app.models.safety_event import SafetyEvent
from app.predictions.data_validation import validate_dataset
from tests.fixtures.predictions.synthetic_training_dataset import (
    DEFAULT_START,
    _decreasing_risk_regime,
    _increasing_risk_regime,
    _stable_risk_regime,
    seed_corrective_action_deterioration_organization,
    seed_decreasing_risk_organization,
    seed_equipment_failure_leading_indicator_organization,
    seed_increasing_risk_organization,
    seed_reporting_bias_organization,
    seed_sparse_data_organization,
    seed_stable_organization,
    seed_stale_data_organization,
    seed_synthetic_organization,
    seed_training_deterioration_organization,
)


def _count(db_session, org_id, event_type, start, end, *, status=None, event_subtype=None):
    stmt = select(func.count()).select_from(SafetyEvent).where(
        SafetyEvent.organization_id == org_id,
        SafetyEvent.event_type == event_type,
        SafetyEvent.event_time >= start,
        SafetyEvent.event_time < end,
    )
    if status is not None:
        stmt = stmt.where(SafetyEvent.status == status)
    if event_subtype is not None:
        stmt = stmt.where(SafetyEvent.event_subtype == event_subtype)
    return db_session.execute(stmt).scalar_one()


def test_risk_regime_functions_have_the_documented_shape():
    """Pure-function check, no DB -- the three regime curves actually do
    what their docstrings claim."""
    num_days = 400
    assert _stable_risk_regime(0, num_days) == _stable_risk_regime(num_days - 1, num_days)
    assert _increasing_risk_regime(0, num_days) < _increasing_risk_regime(num_days - 1, num_days)
    assert _decreasing_risk_regime(0, num_days) > _decreasing_risk_regime(num_days - 1, num_days)


def test_stable_scenario_incident_rate_does_not_trend_across_the_window(db_session):
    # A large window and two sites, so the per-half incident counts are
    # large enough that ordinary sampling noise doesn't produce a false
    # "trend" -- this scenario has no regime change to detect at all.
    num_days = 900
    org, _sites = seed_stable_organization(db_session, seed=101, num_days=num_days, site_names=["Site 1", "Site 2"])
    midpoint = DEFAULT_START + timedelta(days=num_days // 2)
    first_half = _count(db_session, org.id, "INCIDENT", DEFAULT_START, midpoint)
    second_half = _count(db_session, org.id, "INCIDENT", midpoint, DEFAULT_START + timedelta(days=num_days))

    assert first_half > 0
    assert second_half > 0
    # A flat base rate should never show a strong directional trend --
    # generous bound so this stays non-flaky across seeds/refactors while
    # still failing if the "stable" scenario actually drifted.
    assert max(first_half, second_half) / min(first_half, second_half) < 4


def test_increasing_risk_scenario_has_more_incidents_late_than_early(db_session):
    num_days = 400
    org, _sites = seed_increasing_risk_organization(db_session, seed=102, num_days=num_days)
    midpoint = DEFAULT_START + timedelta(days=num_days // 2)
    first_half = _count(db_session, org.id, "INCIDENT", DEFAULT_START, midpoint)
    second_half = _count(db_session, org.id, "INCIDENT", midpoint, DEFAULT_START + timedelta(days=num_days))

    assert second_half > first_half


def test_decreasing_risk_scenario_has_fewer_incidents_late_than_early(db_session):
    num_days = 400
    org, _sites = seed_decreasing_risk_organization(db_session, seed=103, num_days=num_days)
    midpoint = DEFAULT_START + timedelta(days=num_days // 2)
    first_half = _count(db_session, org.id, "INCIDENT", DEFAULT_START, midpoint)
    second_half = _count(db_session, org.id, "INCIDENT", midpoint, DEFAULT_START + timedelta(days=num_days))

    assert second_half < first_half


def test_sparse_scenario_produces_far_fewer_events_than_the_default_regime_change_dataset(db_session):
    sparse_org, _sparse_sites = seed_sparse_data_organization(db_session, seed=104)
    dense_org, _dense_sites = seed_synthetic_organization(
        db_session, name="Dense Comparison Org", site_names=["Site 1"], seed=105, num_days=400
    )

    sparse_count = db_session.execute(
        select(func.count()).select_from(SafetyEvent).where(SafetyEvent.organization_id == sparse_org.id)
    ).scalar_one()
    dense_count = db_session.execute(
        select(func.count()).select_from(SafetyEvent).where(SafetyEvent.organization_id == dense_org.id)
    ).scalar_one()

    assert sparse_count > 0
    assert sparse_count < dense_count


def test_stale_scenario_events_stop_well_before_the_declared_window_ends_and_is_flagged_by_validate_dataset(db_session):
    num_days = 400
    stale_gap_days = 150
    org, _sites = seed_stale_data_organization(
        db_session, seed=106, num_days=num_days, stale_gap_days=stale_gap_days
    )
    window_end = DEFAULT_START + timedelta(days=num_days)

    latest_event_time = db_session.execute(
        select(func.max(SafetyEvent.event_time)).where(SafetyEvent.organization_id == org.id)
    ).scalar_one()
    assert latest_event_time is not None
    if latest_event_time.tzinfo is None:  # SQLite round-trips datetimes as naive; see app/predictions' own _as_utc()
        latest_event_time = latest_event_time.replace(tzinfo=timezone.utc)
    assert latest_event_time <= DEFAULT_START + timedelta(days=num_days - stale_gap_days + 1)

    report = validate_dataset(
        db_session, organization_id=org.id, date_range_start=DEFAULT_START, date_range_end=window_end, as_of=window_end
    )
    assert report.freshness.is_stale is True
    assert report.freshness.staleness_days >= stale_gap_days - 30  # slack for stride/commit granularity


def test_reporting_bias_scenario_reporting_volume_drops_while_incident_rate_stays_flat(db_session):
    num_days = 450
    org, _sites = seed_reporting_bias_organization(db_session, seed=107, num_days=num_days)
    early_end = DEFAULT_START + timedelta(days=int(2 * num_days / 3))
    window_end = DEFAULT_START + timedelta(days=num_days)

    early_reports = _count(db_session, org.id, "NEAR_MISS", DEFAULT_START, early_end) + _count(
        db_session, org.id, "OBSERVATION", DEFAULT_START, early_end
    )
    late_reports = _count(db_session, org.id, "NEAR_MISS", early_end, window_end) + _count(
        db_session, org.id, "OBSERVATION", early_end, window_end
    )
    # Normalize by window length (the "late" window is shorter).
    early_days = int(2 * num_days / 3)
    late_days = num_days - early_days
    early_rate = early_reports / early_days
    late_rate = late_reports / late_days
    assert late_rate < early_rate * 0.7  # a real, not incidental, drop in reporting volume

    early_incidents = _count(db_session, org.id, "INCIDENT", DEFAULT_START, early_end)
    late_incidents = _count(db_session, org.id, "INCIDENT", early_end, window_end)
    early_incident_rate = early_incidents / early_days
    late_incident_rate = late_incidents / late_days
    # The actual risk (INCIDENT rate) must NOT have moved anywhere near as
    # much as the reporting volume did -- that is the entire point of this
    # scenario (a model/report must not mistake less reporting for less risk).
    assert late_incident_rate > early_incident_rate * 0.4


def test_equipment_leading_indicator_scenario_clusters_failures_ahead_of_the_elevated_period(db_session):
    num_days = 600  # matches _risk_regime's own thirds cleanly
    org, _sites = seed_equipment_failure_leading_indicator_organization(db_session, seed=108, num_days=num_days)
    third = num_days / 3
    pre_elevated_start = DEFAULT_START + timedelta(days=int(third - 30))
    elevated_start = DEFAULT_START + timedelta(days=int(third))
    baseline_start = DEFAULT_START
    baseline_end = DEFAULT_START + timedelta(days=int(third - 60))

    pre_elevated_count = _count(db_session, org.id, "EQUIPMENT", pre_elevated_start, elevated_start)
    baseline_count = _count(db_session, org.id, "EQUIPMENT", baseline_start, baseline_end)

    pre_elevated_days = 30
    baseline_days = int(third - 60)
    pre_elevated_rate = pre_elevated_count / pre_elevated_days
    baseline_rate = baseline_count / max(baseline_days, 1)

    assert pre_elevated_rate > baseline_rate


def test_corrective_action_deterioration_scenario_overdue_share_rises_over_time(db_session):
    num_days = 400
    org, _sites = seed_corrective_action_deterioration_organization(db_session, seed=109, num_days=num_days)
    midpoint = DEFAULT_START + timedelta(days=num_days // 2)
    window_end = DEFAULT_START + timedelta(days=num_days)

    def _overdue_share(start, end):
        total = _count(db_session, org.id, "CORRECTIVE_ACTION", start, end)
        overdue = _count(db_session, org.id, "CORRECTIVE_ACTION", start, end, status="OVERDUE") + _count(
            db_session, org.id, "CORRECTIVE_ACTION", start, end, status="OPEN"
        )
        return overdue / total if total else 0.0

    early_share = _overdue_share(DEFAULT_START, midpoint)
    late_share = _overdue_share(midpoint, window_end)
    assert late_share > early_share


def test_training_deterioration_scenario_overdue_expired_share_rises_over_time(db_session):
    num_days = 400
    org, _sites = seed_training_deterioration_organization(db_session, seed=110, num_days=num_days)
    midpoint = DEFAULT_START + timedelta(days=num_days // 2)
    window_end = DEFAULT_START + timedelta(days=num_days)

    def _noncompliant_share(start, end):
        total = _count(db_session, org.id, "TRAINING", start, end)
        noncompliant = _count(db_session, org.id, "TRAINING", start, end, status="OVERDUE") + _count(
            db_session, org.id, "TRAINING", start, end, status="EXPIRED"
        )
        return noncompliant / total if total else 0.0

    early_share = _noncompliant_share(DEFAULT_START, midpoint)
    late_share = _noncompliant_share(midpoint, window_end)
    assert late_share > early_share
