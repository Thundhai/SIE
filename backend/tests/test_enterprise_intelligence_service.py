"""SIE Milestone 22: Enterprise Intelligence & Risk Analytics Foundation
v0.1 — point-in-time correctness, aggregation, trend classification, and
data sufficiency for `app/intelligence/enterprise_intelligence_service.py`.
Runs against `db_session` (SQLite) — plain datetime/aggregation, no
pgvector needed, mirroring `tests/test_intelligence_signals.py`'s own
established shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.enterprise_intelligence_service import compute_enterprise_intelligence
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

AS_OF = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _seed(db_session, org_id, *, site_id=None, event_time=AS_OF, ingestion_time=None, **overrides):
    event = make_safety_event(
        organization_id=org_id,
        site_id=site_id,
        event_time=event_time,
        ingestion_time=ingestion_time if ingestion_time is not None else event_time,
        source_record_id=str(uuid.uuid4()),
        **overrides,
    )
    db_session.add(event)
    db_session.commit()
    return event


# --- Point-in-time correctness (milestone item 3) -----------------------------------


def test_event_ingested_after_as_of_is_excluded_even_if_it_occurred_before(db_session):
    org = make_org(db_session)
    # Occurred well within the window, but backdated/ingested after as_of --
    # would not have been knowable "as of" AS_OF.
    _seed(
        db_session, org.id, event_type="INCIDENT",
        event_time=AS_OF - timedelta(days=5), ingestion_time=AS_OF + timedelta(days=1),
    )

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    assert result.event_count == 0
    incident_indicator = next(i for i in result.indicators if i.key == "incident_count")
    assert incident_indicator.value == 0


def test_event_occurred_and_ingested_before_as_of_is_included(db_session):
    org = make_org(db_session)
    _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=5))

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    assert result.event_count == 1
    incident_indicator = next(i for i in result.indicators if i.key == "incident_count")
    assert incident_indicator.value == 1


# --- Aggregation (milestone item 4) --------------------------------------------------


def test_current_period_counts_only_events_within_the_current_window(db_session):
    org = make_org(db_session)
    _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=10))
    _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=20))
    # Outside the 30-day current window (but within the previous window).
    _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=40))

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    incident = next(i for i in result.indicators if i.key == "incident_count")
    assert incident.value == 2
    assert incident.previous_value == 1


def test_previous_period_is_the_immediately_preceding_equal_length_window(db_session):
    org = make_org(db_session)
    # Previous window: (AS_OF - 60d, AS_OF - 30d]
    _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=45))
    _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=50))
    # Well before the previous window entirely.
    _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=100))

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    incident = next(i for i in result.indicators if i.key == "incident_count")
    assert incident.value == 0
    assert incident.previous_value == 2
    assert result.trend.previous_period_start == AS_OF - timedelta(days=60)
    assert result.trend.previous_period_end == AS_OF - timedelta(days=30)


def test_deterministic_boundaries_are_stable_across_repeated_calls(db_session):
    org = make_org(db_session)
    for i in range(6):
        _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=i * 3))

    first = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)
    second = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    incident_first = next(i for i in first.indicators if i.key == "incident_count")
    incident_second = next(i for i in second.indicators if i.key == "incident_count")
    assert incident_first.value == incident_second.value
    assert first.provenance.window_start == second.provenance.window_start == AS_OF - timedelta(days=30)


# --- Trend classification (milestone item 6) -----------------------------------------


def test_trend_is_deteriorating_when_incidents_rise_beyond_the_threshold(db_session):
    org = make_org(db_session)
    for i in range(2):
        _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=40 + i))
    for i in range(6):
        _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=i))

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    assert result.trend.classification == "DETERIORATING"
    assert result.trend.current_value == 6
    assert result.trend.previous_value == 2


def test_trend_is_improving_when_incidents_fall_beyond_the_threshold(db_session):
    org = make_org(db_session)
    for i in range(6):
        _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=40 + i))
    for i in range(1):
        _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=i))

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    assert result.trend.classification == "IMPROVING"


def test_trend_is_stable_when_change_is_within_the_threshold(db_session):
    org = make_org(db_session)
    for i in range(5):
        _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=40 + i))
    for i in range(5):
        _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=i))

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    assert result.trend.classification == "STABLE"
    assert result.trend.percentage_change == 0.0


def test_trend_is_insufficient_data_when_combined_count_is_too_low(db_session):
    org = make_org(db_session)
    _seed(db_session, org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=1))

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    assert result.trend.classification == "INSUFFICIENT_DATA"
    assert result.trend.percentage_change is None


# --- Data sufficiency (milestone item 13) --------------------------------------------


def test_data_sufficiency_reflects_event_count(db_session):
    org = make_org(db_session)
    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)
    assert result.data_sufficiency == "INSUFFICIENT_DATA"
    assert result.risk.score is None
    assert result.risk.classification is None
    assert result.risk.insufficient_data_reason is not None


# --- Site scope ------------------------------------------------------------------------


def test_site_scope_only_includes_that_sites_events(db_session):
    org = make_org(db_session)
    site_a = make_site(db_session, org.id, name="Site A")
    site_b = make_site(db_session, org.id, name="Site B")
    _seed(db_session, org.id, site_id=site_a.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=1))
    _seed(db_session, org.id, site_id=site_b.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=1))

    result = compute_enterprise_intelligence(
        db_session, organization_id=org.id, scope="site", site_id=site_a.id, as_of=AS_OF, window_days=30
    )

    assert result.event_count == 1
    assert result.entity_id == site_a.id
    assert all(e_id != site_b.id for e_id in [result.entity_id])


# --- Actions context (milestone item 18) ----------------------------------------------


def test_actions_context_reports_factual_counts_only(db_session):
    from app.models.safety_action import SafetyAction
    from app.models.safety_action_enums import ActionPriority, ActionStatus, ActionType

    org = make_org(db_session)
    action = SafetyAction(
        organization_id=org.id,
        title="Fix guard rail",
        action_type=ActionType.CORRECTIVE,
        priority=ActionPriority.HIGH,
        status=ActionStatus.OPEN,
    )
    db_session.add(action)
    db_session.commit()

    result = compute_enterprise_intelligence(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)

    assert result.actions_context is not None
    assert result.actions_context.open_action_count == 1
    assert result.actions_context.high_priority_action_count == 1
