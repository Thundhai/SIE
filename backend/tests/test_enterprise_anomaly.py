"""SIE Milestone 23: Enterprise Intelligence Explainability & Anomaly
Foundation v0.1 — `app/intelligence/enterprise_anomaly.py`. Runs against
`db_session` (SQLite) — plain datetime/aggregation, no pgvector needed,
mirroring `tests/test_enterprise_intelligence_service.py`'s own
established shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.enterprise_anomaly import SUPPORTED_ANOMALY_METRICS, compute_enterprise_anomalies
from app.intelligence.temporal import events_as_of, window_bounds
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

AS_OF = datetime(2026, 7, 1, tzinfo=timezone.utc)
WINDOW_DAYS = 30


def _as_utc(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _seed_event(db_session, org_id, *, site_id=None, event_type="INCIDENT", event_subtype=None, event_time):
    event = make_safety_event(
        organization_id=org_id,
        site_id=site_id,
        event_type=event_type,
        event_subtype=event_subtype,
        event_time=event_time,
        ingestion_time=event_time,
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(event)
    return event


def _seed_baseline(db_session, org_id, *, window_start, site_id=None, event_type="INCIDENT", event_subtype=None, counts_oldest_first):
    """Seed exactly `counts_oldest_first[i]` events of the given type in
    each of `len(counts_oldest_first)` consecutive 30-day periods
    immediately preceding `window_start` -- oldest period first, so
    `counts_oldest_first[-1]` is the period immediately before
    `window_start`.

    Every event lands safely *inside* its own period (never exactly on a
    shared boundary) except the very first event of the very *oldest*
    period, which lands exactly at that period's own start -- so
    `_available_baseline_periods()`'s earliest-event lookup sees the
    full requested history depth precisely, while no event is ever
    double-counted by `bucketed_counts()`'s own inclusive-both-ends
    bucket boundaries (adjacent buckets share a boundary instant; an
    event placed exactly there would satisfy both — this fixture
    deliberately avoids that everywhere except the one boundary nothing
    else precedes)."""
    period_end = window_start
    # Walk backwards from window_start so the *last* entry in
    # counts_oldest_first lands in the period immediately preceding it.
    periods = []
    for _ in counts_oldest_first:
        period_start = period_end - timedelta(days=WINDOW_DAYS)
        periods.append((period_start, period_end))
        period_end = period_start
    periods.reverse()  # oldest first, matching counts_oldest_first
    for idx, ((period_start, period_end), count) in enumerate(zip(periods, counts_oldest_first)):
        for i in range(count):
            if idx == 0 and i == 0:
                offset = timedelta(hours=0)
            else:
                offset = timedelta(days=15, hours=i)  # safely interior
            _seed_event(
                db_session, org_id, site_id=site_id, event_type=event_type, event_subtype=event_subtype,
                event_time=period_start + offset,
            )
    db_session.commit()


def _seed_current(db_session, org_id, *, as_of, count, site_id=None, event_type="INCIDENT", event_subtype=None):
    for i in range(count):
        _seed_event(db_session, org_id, site_id=site_id, event_type=event_type, event_subtype=event_subtype,
                    event_time=as_of - timedelta(days=i))
    db_session.commit()


def _current_events(db_session, org_id, *, as_of, window_start, site_id=None):
    events = list(
        db_session.execute(events_as_of(organization_id=org_id, as_of=as_of, window_start=window_start, site_id=site_id))
        .scalars()
        .all()
    )
    return [e for e in events if _as_utc(e.event_time) > window_start]


def _run(db_session, org_id, *, as_of=AS_OF, window_days=WINDOW_DAYS, site_id=None):
    window_start, _ = window_bounds(as_of, window_days)
    current_events = _current_events(db_session, org_id, as_of=as_of, window_start=window_start, site_id=site_id)
    return compute_enterprise_anomalies(
        db_session, organization_id=org_id, site_id=site_id, current_events=current_events,
        as_of=as_of, window_start=window_start, window_days=window_days,
    )


def _by_metric(results, metric):
    return next(r for r in results if r.metric == metric)


# --- Basic (milestone item 15) --------------------------------------------------------


def test_a_normal_metric_is_classified_normal(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 3, 2, 3])
    _seed_current(db_session, org.id, as_of=AS_OF, count=3)

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.status == "NORMAL"


def test_an_anomalously_high_metric_is_classified_anomalous_above_baseline(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 3, 2, 3])
    _seed_current(db_session, org.id, as_of=AS_OF, count=20)

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.status == "ANOMALOUS"
    assert result.direction == "ABOVE_BASELINE"


def test_an_anomalously_low_metric_is_classified_anomalous_below_baseline(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[10, 11, 10, 11])
    _seed_current(db_session, org.id, as_of=AS_OF, count=0)

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.status == "ANOMALOUS"
    assert result.direction == "BELOW_BASELINE"


def test_insufficient_baseline_history_is_reported_explicitly(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    # Only 2 periods of history -- below the default minimum (4).
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 2])
    _seed_current(db_session, org.id, as_of=AS_OF, count=8)

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.status == "INSUFFICIENT_DATA"
    assert result.direction == "NONE"
    assert result.baseline_mean is None
    assert result.z_score is None


def test_zero_standard_deviation_with_a_deviation_is_anomalous_without_dividing_by_zero(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 2, 2, 2])
    _seed_current(db_session, org.id, as_of=AS_OF, count=9)

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.status == "ANOMALOUS"
    assert result.baseline_stdev == 0.0
    assert result.z_score is None  # undefined, never fabricated
    assert result.direction == "ABOVE_BASELINE"


def test_zero_current_value_against_a_real_baseline_is_evaluated_normally(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 2, 2, 2])
    # No current-period events at all -- count is a real, meaningful 0.
    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.current_value == 0.0
    assert result.status == "ANOMALOUS"  # 0 deviates from a constant baseline of 2
    assert result.direction == "BELOW_BASELINE"


def test_zero_baseline_mean_with_zero_current_is_normal(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    # Zero INCIDENT events anywhere -- but a lone OBSERVATION 4 periods
    # back establishes this organization's own history depth (the
    # earliest-event lookup spans *any* event type -- see
    # `_available_baseline_periods()`'s own docstring), so this is a
    # real all-zero baseline, not "insufficient data" merely because
    # the metric itself never fired.
    _seed_baseline(db_session, org.id, window_start=window_start, event_type="OBSERVATION", counts_oldest_first=[1, 0, 0, 0])
    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.baseline_mean == 0.0
    assert result.current_value == 0.0
    assert result.status == "NORMAL"
    assert result.direction == "NONE"


def test_deterministic_repeated_calculation(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 3, 2, 3])
    _seed_current(db_session, org.id, as_of=AS_OF, count=8)

    first = _by_metric(_run(db_session, org.id), "incident_count")
    second = _by_metric(_run(db_session, org.id), "incident_count")
    assert first.status == second.status
    assert first.z_score == second.z_score
    assert first.baseline_mean == second.baseline_mean
    assert first.baseline_stdev == second.baseline_stdev


# --- Temporal (milestone item 15) ------------------------------------------------------


def test_a_future_event_is_excluded_from_the_current_value(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 3, 2, 3])
    _seed_current(db_session, org.id, as_of=AS_OF, count=2)
    # An event dated after AS_OF must never be visible to this as_of query.
    _seed_event(db_session, org.id, event_time=AS_OF + timedelta(days=5))
    db_session.commit()

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.current_value == 2.0


def test_an_event_ingested_after_as_of_is_excluded_even_if_it_occurred_earlier(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 3, 2, 3])
    _seed_current(db_session, org.id, as_of=AS_OF, count=2)
    backdated = make_safety_event(
        organization_id=org.id, event_type="INCIDENT",
        event_time=AS_OF - timedelta(days=3), ingestion_time=AS_OF + timedelta(days=1),
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(backdated)
    db_session.commit()

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.current_value == 2.0


def test_historical_baseline_cannot_see_future_data(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 2, 2, 2])
    _seed_current(db_session, org.id, as_of=AS_OF, count=2)
    # An event within a baseline period's date range, but ingested after
    # AS_OF -- must not silently inflate the baseline mean.
    baseline_period_start = window_start - timedelta(days=30)
    late_baseline_event = make_safety_event(
        organization_id=org.id, event_type="INCIDENT",
        event_time=baseline_period_start + timedelta(hours=5), ingestion_time=AS_OF + timedelta(days=1),
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(late_baseline_event)
    db_session.commit()

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.baseline_mean == 2.0  # unaffected by the late-ingested event


# --- Tenant (milestone item 15) --------------------------------------------------------


def test_organization_isolation(db_session):
    org_a = make_org(db_session, name="Org A")
    org_b = make_org(db_session, name="Org B")
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org_a.id, window_start=window_start, counts_oldest_first=[2, 2, 2, 2])
    _seed_current(db_session, org_a.id, as_of=AS_OF, count=2)
    # Org B has wildly different (anomalous-looking) data -- must never
    # influence Org A's own result.
    _seed_baseline(db_session, org_b.id, window_start=window_start, counts_oldest_first=[50, 50, 50, 50])
    _seed_current(db_session, org_b.id, as_of=AS_OF, count=200)

    result_a = _by_metric(_run(db_session, org_a.id), "incident_count")
    assert result_a.baseline_mean == 2.0
    assert result_a.current_value == 2.0
    assert result_a.status == "NORMAL"


def test_site_isolation(db_session):
    org = make_org(db_session)
    site_a = make_site(db_session, org.id, name="Site A")
    site_b = make_site(db_session, org.id, name="Site B")
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, site_id=site_a.id, counts_oldest_first=[2, 2, 2, 2])
    _seed_current(db_session, org.id, as_of=AS_OF, site_id=site_a.id, count=2)
    _seed_baseline(db_session, org.id, window_start=window_start, site_id=site_b.id, counts_oldest_first=[50, 50, 50, 50])
    _seed_current(db_session, org.id, as_of=AS_OF, site_id=site_b.id, count=200)

    result_a = _by_metric(_run(db_session, org.id, site_id=site_a.id), "incident_count")
    assert result_a.baseline_mean == 2.0
    assert result_a.current_value == 2.0


def test_evidence_never_leaks_a_foreign_organizations_event_ids(db_session):
    org_a = make_org(db_session, name="Org A2")
    org_b = make_org(db_session, name="Org B2")
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org_a.id, window_start=window_start, counts_oldest_first=[2, 2, 2, 2])
    _seed_current(db_session, org_a.id, as_of=AS_OF, count=2)
    b_event = _seed_event(db_session, org_b.id, event_time=AS_OF - timedelta(days=1))
    db_session.commit()

    result_a = _by_metric(_run(db_session, org_a.id), "incident_count")
    assert b_event.id not in result_a.supporting_event_ids


# --- Statistical (milestone item 15) ---------------------------------------------------


def test_known_fixture_produces_the_expected_mean_and_stdev(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    # baseline [2,3,2,3,2,3,2,3] -- mean 2.5, population stdev 0.5.
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 3, 2, 3, 2, 3, 2, 3])
    _seed_current(db_session, org.id, as_of=AS_OF, count=8)

    result = _by_metric(_run(db_session, org.id), "incident_count")
    assert result.baseline_mean == 2.5
    assert result.baseline_stdev == 0.5


def test_known_fixture_produces_the_expected_z_score(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 3, 2, 3, 2, 3, 2, 3])
    _seed_current(db_session, org.id, as_of=AS_OF, count=8)

    result = _by_metric(_run(db_session, org.id), "incident_count")
    # z = (8 - 2.5) / 0.5 = 11.0
    assert result.z_score == 11.0
    assert result.status == "ANOMALOUS"
    assert result.direction == "ABOVE_BASELINE"


# --- Multi-metric (milestone item 15) --------------------------------------------------


def test_multiple_metrics_are_returned_for_one_scan(db_session):
    org = make_org(db_session)
    results = _run(db_session, org.id)
    assert {r.metric for r in results} == set(SUPPORTED_ANOMALY_METRICS)
    assert len(results) == 7


def test_unsupported_metrics_are_never_fabricated(db_session):
    org = make_org(db_session)
    results = _run(db_session, org.id)
    for metric in ("fire_count", "recordable_incident_rate", "ppe_violation_count"):
        assert metric not in {r.metric for r in results}


def test_one_insufficient_metric_does_not_invalidate_other_valid_metrics(db_session):
    org = make_org(db_session)
    window_start, _ = window_bounds(AS_OF, WINDOW_DAYS)
    # Enough overall history (INCIDENT) to clear the minimum-baseline-
    # periods gate...
    _seed_baseline(db_session, org.id, window_start=window_start, counts_oldest_first=[2, 3, 2, 3])
    _seed_current(db_session, org.id, as_of=AS_OF, count=20)
    # ...but zero NEAR_MISS events anywhere -- still evaluated (a real
    # baseline of all-zeros), not "insufficient" merely because it's zero.
    results = _run(db_session, org.id)
    incident = _by_metric(results, "incident_count")
    near_miss = _by_metric(results, "near_miss_count")
    assert incident.status == "ANOMALOUS"
    assert near_miss.baseline_period_count == incident.baseline_period_count
    assert near_miss.status == "NORMAL"  # 0 vs. an all-zero baseline -- no deviation
