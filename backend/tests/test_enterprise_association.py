"""SIE Milestone 24: Enterprise Intelligence Pattern & Correlation
Foundation v0.1 — `app/intelligence/enterprise_association.py`. Runs
against `db_session` (SQLite) — plain datetime/aggregation, no pgvector
needed, mirroring `tests/test_enterprise_anomaly.py`'s own established
shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.enterprise_association import SUPPORTED_ASSOCIATION_METRICS, compute_enterprise_associations
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

AS_OF = datetime(2026, 7, 1, tzinfo=timezone.utc)
WINDOW_DAYS = 30


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


def _seed_depth_marker(db_session, org_id, *, as_of=AS_OF, num_periods, window_days=WINDOW_DAYS, site_id=None):
    """One `AUDIT` event exactly at the oldest period's own start --
    establishes this organization's (or site's) history depth for
    `_available_periods()` without affecting any association-eligible
    metric (`AUDIT` is not part of `SUPPORTED_ASSOCIATION_METRICS`'s
    underlying event types: `INCIDENT`/`NEAR_MISS`/`OBSERVATION`)."""
    oldest_start = as_of - timedelta(days=window_days * num_periods)
    _seed_event(db_session, org_id, site_id=site_id, event_type="AUDIT", event_time=oldest_start)
    db_session.commit()


def _seed_metric_periods(
    db_session, org_id, *, as_of=AS_OF, window_days=WINDOW_DAYS, event_type, event_subtype=None, site_id=None,
    counts_oldest_first,
):
    """Seed exactly `counts_oldest_first[i]` events of the given type in
    each of `len(counts_oldest_first)` consecutive `window_days`-length
    periods ending at `as_of` -- oldest period first. Every event lands
    safely *interior* to its own period (never exactly on a shared
    boundary) -- unlike `tests/test_enterprise_anomaly.py`'s own fixture,
    no event needs to sit exactly on a boundary here, since organization
    history depth is established independently via `_seed_depth_marker()`
    above."""
    period_end = as_of
    periods = []
    for _ in counts_oldest_first:
        period_start = period_end - timedelta(days=window_days)
        periods.append((period_start, period_end))
        period_end = period_start
    periods.reverse()
    for (period_start, _period_end), count in zip(periods, counts_oldest_first):
        for i in range(count):
            _seed_event(
                db_session, org_id, site_id=site_id, event_type=event_type, event_subtype=event_subtype,
                event_time=period_start + timedelta(days=15, hours=i),
            )
    db_session.commit()


def _run(db_session, org_id, *, as_of=AS_OF, window_days=WINDOW_DAYS, site_id=None):
    return compute_enterprise_associations(
        db_session, organization_id=org_id, site_id=site_id, as_of=as_of, window_days=window_days
    )


def _pair(results, metric_a, metric_b):
    key = {metric_a, metric_b}
    return next(r for r in results if {r.metric_a, r.metric_b} == key)


# --- Correlation (milestone item 17) ---------------------------------------------------


def test_perfectly_positively_correlated_metrics_are_strong_positive(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[2, 3, 4, 5, 6, 7])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[4, 6, 8, 10, 12, 14])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.correlation_coefficient == 1.0
    assert result.classification == "STRONG_POSITIVE"


def test_strong_positive_association_below_perfect(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[1, 2, 3, 4, 5, 6])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[1, 3, 2, 5, 4, 7])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.correlation_coefficient == 0.8908
    assert result.classification == "STRONG_POSITIVE"


def test_moderate_positive_association(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[1, 2, 3, 4, 5, 6])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[3, 1, 4, 2, 6, 5])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.correlation_coefficient == 0.6571
    assert result.classification == "MODERATE_POSITIVE"


def test_weak_or_no_association(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[1, 2, 3, 4, 5, 6])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[4, 1, 6, 2, 5, 3])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.correlation_coefficient == 0.0857
    assert result.classification == "WEAK"


def test_moderate_negative_association(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[1, 2, 3, 4, 5, 6])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[5, 6, 2, 4, 1, 3])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.correlation_coefficient == -0.6571
    assert result.classification == "MODERATE_NEGATIVE"


def test_perfectly_negatively_correlated_metrics_are_strong_negative(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[1, 2, 3, 4, 5, 6])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[6, 5, 4, 3, 2, 1])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.correlation_coefficient == -1.0
    assert result.classification == "STRONG_NEGATIVE"


def test_a_constant_metric_series_is_insufficient_data_not_a_fabricated_correlation(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[3, 3, 3, 3, 3, 3])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[1, 2, 3, 4, 5, 6])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.correlation_coefficient is None
    assert result.classification == "INSUFFICIENT_DATA"


def test_insufficient_periods_is_reported_explicitly_not_computed(db_session):
    org = make_org(db_session)
    # Only 2 periods of history -- below the default minimum (4).
    _seed_depth_marker(db_session, org.id, num_periods=2)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[2, 2])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[3, 3])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.classification == "INSUFFICIENT_DATA"
    assert result.period_count == 0  # no history to fabricate a period count from
    assert result.correlation_coefficient is None


def test_deterministic_repeated_calculation(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[2, 3, 4, 5, 6, 7])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[1, 3, 2, 5, 4, 7])

    first = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    second = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert first.correlation_coefficient == second.correlation_coefficient
    assert first.classification == second.classification
    assert first.period_count == second.period_count


# --- Temporal (milestone item 17) ------------------------------------------------------


def test_a_future_event_is_excluded_from_the_most_recent_period(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[2, 2, 2, 2, 2, 2])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[1, 1, 1, 1, 1, 1])
    # An event dated after AS_OF must never be visible to this as_of query.
    _seed_event(db_session, org.id, event_type="INCIDENT", event_time=AS_OF + timedelta(days=5))
    db_session.commit()

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.values_a == [2.0, 2.0, 2.0, 2.0, 2.0, 2.0]  # unaffected by the future event


def test_an_event_ingested_after_as_of_is_excluded_even_if_it_occurred_earlier(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[2, 2, 2, 2, 2, 2])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[1, 1, 1, 1, 1, 1])
    backdated = make_safety_event(
        organization_id=org.id, event_type="INCIDENT",
        event_time=AS_OF - timedelta(days=3), ingestion_time=AS_OF + timedelta(days=1),
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(backdated)
    db_session.commit()

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.values_a[-1] == 2.0  # backdated-but-late-ingested event never counted


def test_a_historical_period_cannot_see_an_event_ingested_after_as_of(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[2, 2, 2, 2, 2, 2])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[1, 1, 1, 1, 1, 1])
    # An event within the oldest period's date range, but ingested after
    # AS_OF -- must not silently inflate that period's count.
    oldest_period_start = AS_OF - timedelta(days=WINDOW_DAYS * 6)
    late_event = make_safety_event(
        organization_id=org.id, event_type="INCIDENT",
        event_time=oldest_period_start + timedelta(days=5), ingestion_time=AS_OF + timedelta(days=1),
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(late_event)
    db_session.commit()

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.values_a[0] == 2.0  # oldest period unaffected by the late-ingested event


def test_period_boundaries_are_contiguous_and_reconstructable(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[1, 2, 3, 4, 5, 6])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[2, 4, 6, 8, 10, 12])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert result.period_end == AS_OF
    assert result.period_start == AS_OF - timedelta(days=WINDOW_DAYS * 6)
    assert result.period_count == 6
    assert result.window_days == WINDOW_DAYS


# --- Tenant (milestone item 17) --------------------------------------------------------


def test_organization_isolation(db_session):
    org_a = make_org(db_session, name="Org A4")
    org_b = make_org(db_session, name="Org B4")
    _seed_depth_marker(db_session, org_a.id, num_periods=6)
    _seed_metric_periods(db_session, org_a.id, event_type="INCIDENT", counts_oldest_first=[2, 3, 4, 5, 6, 7])
    _seed_metric_periods(db_session, org_a.id, event_type="NEAR_MISS", counts_oldest_first=[4, 6, 8, 10, 12, 14])
    # Org B has wildly different (negatively correlated) data -- must
    # never influence Org A's own result.
    _seed_depth_marker(db_session, org_b.id, num_periods=6)
    _seed_metric_periods(db_session, org_b.id, event_type="INCIDENT", counts_oldest_first=[1, 2, 3, 4, 5, 6])
    _seed_metric_periods(db_session, org_b.id, event_type="NEAR_MISS", counts_oldest_first=[6, 5, 4, 3, 2, 1])

    result_a = _pair(_run(db_session, org_a.id), "incident_count", "near_miss_count")
    assert result_a.correlation_coefficient == 1.0
    assert result_a.classification == "STRONG_POSITIVE"


def test_site_isolation(db_session):
    org = make_org(db_session)
    site_a = make_site(db_session, org.id, name="Site A4")
    site_b = make_site(db_session, org.id, name="Site B4")
    _seed_depth_marker(db_session, org.id, num_periods=6, site_id=site_a.id)
    _seed_metric_periods(db_session, org.id, site_id=site_a.id, event_type="INCIDENT", counts_oldest_first=[2, 3, 4, 5, 6, 7])
    _seed_metric_periods(db_session, org.id, site_id=site_a.id, event_type="NEAR_MISS", counts_oldest_first=[4, 6, 8, 10, 12, 14])
    _seed_depth_marker(db_session, org.id, num_periods=6, site_id=site_b.id)
    _seed_metric_periods(db_session, org.id, site_id=site_b.id, event_type="INCIDENT", counts_oldest_first=[1, 2, 3, 4, 5, 6])
    _seed_metric_periods(db_session, org.id, site_id=site_b.id, event_type="NEAR_MISS", counts_oldest_first=[6, 5, 4, 3, 2, 1])

    result_a = _pair(_run(db_session, org.id, site_id=site_a.id), "incident_count", "near_miss_count")
    assert result_a.correlation_coefficient == 1.0
    assert result_a.classification == "STRONG_POSITIVE"


def test_evidence_never_leaks_a_foreign_organizations_event_ids(db_session):
    org_a = make_org(db_session, name="Org A5")
    org_b = make_org(db_session, name="Org B5")
    _seed_depth_marker(db_session, org_a.id, num_periods=6)
    _seed_metric_periods(db_session, org_a.id, event_type="INCIDENT", counts_oldest_first=[2, 3, 4, 5, 6, 7])
    _seed_metric_periods(db_session, org_a.id, event_type="NEAR_MISS", counts_oldest_first=[4, 6, 8, 10, 12, 14])
    b_event = _seed_event(db_session, org_b.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=1))
    db_session.commit()

    results_a = _run(db_session, org_a.id)
    all_evidence_ids = {eid for r in results_a for eid in r.supporting_event_ids}
    assert b_event.id not in all_evidence_ids


# --- Multi-metric / closed vocabulary (milestone items 16, 17) -------------------------


def test_exactly_the_fixed_twenty_one_pairs_are_returned(db_session):
    org = make_org(db_session)
    results = _run(db_session, org.id)
    assert len(SUPPORTED_ASSOCIATION_METRICS) == 7
    assert len(results) == 21  # C(7, 2)
    pair_keys = {frozenset((r.metric_a, r.metric_b)) for r in results}
    assert len(pair_keys) == 21  # every pair appears exactly once


def test_unsupported_metrics_are_never_fabricated(db_session):
    org = make_org(db_session)
    results = _run(db_session, org.id)
    all_metrics = {r.metric_a for r in results} | {r.metric_b for r in results}
    assert all_metrics == set(SUPPORTED_ASSOCIATION_METRICS)


def test_bounded_supporting_event_ids(db_session):
    org = make_org(db_session)
    _seed_depth_marker(db_session, org.id, num_periods=6)
    _seed_metric_periods(db_session, org.id, event_type="INCIDENT", counts_oldest_first=[10, 10, 10, 10, 10, 10])
    _seed_metric_periods(db_session, org.id, event_type="NEAR_MISS", counts_oldest_first=[10, 10, 10, 10, 10, 10])

    result = _pair(_run(db_session, org.id), "incident_count", "near_miss_count")
    assert len(result.supporting_event_ids) <= 20
