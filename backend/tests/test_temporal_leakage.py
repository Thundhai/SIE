"""Temporal leakage regression test — milestone item 16/50, the single
most important requirement in this milestone. Runs against a real
database (SQLite is sufficient here — no pgvector operator is involved,
just ordinary datetime comparison) via the shared `db_session` fixture.
"""

import uuid
from datetime import datetime, timezone

from app.intelligence.temporal import events_as_of
from app.models.organization import Organization
from tests.intelligence_test_helpers import make_safety_event


def _seed(db_session, org_id, **overrides):
    event = make_safety_event(organization_id=org_id, **overrides)
    db_session.add(event)
    db_session.commit()
    return event


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="Leakage Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


# --- The milestone's own worked example (item 16/50) ------------------------------


def test_a_future_event_never_leaks_into_a_historical_feature_calculation(db_session):
    """Prediction as-of 2026-06-01. Event A: 2026-05-20 (past -- must be
    included). Event B: 2026-06-15 (future -- must NOT be included)."""
    org_id = _make_org(db_session)
    as_of = datetime(2026, 6, 1, tzinfo=timezone.utc)

    event_a = _seed(
        db_session, org_id,
        event_time=datetime(2026, 5, 20, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 5, 20, tzinfo=timezone.utc),
        source_record_id="event-a",
    )
    event_b = _seed(
        db_session, org_id,
        event_time=datetime(2026, 6, 15, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 6, 15, tzinfo=timezone.utc),
        source_record_id="event-b",
    )

    query = events_as_of(organization_id=org_id, as_of=as_of, window_start=None)
    results = db_session.execute(query).scalars().all()
    result_ids = {e.id for e in results}

    assert event_a.id in result_ids
    assert event_b.id not in result_ids


def test_event_time_exactly_equal_to_as_of_is_included(db_session):
    org_id = _make_org(db_session)
    as_of = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    boundary_event = _seed(
        db_session, org_id, event_time=as_of, ingestion_time=as_of, source_record_id="boundary"
    )

    query = events_as_of(organization_id=org_id, as_of=as_of, window_start=None)
    result_ids = {e.id for e in db_session.execute(query).scalars().all()}
    assert boundary_event.id in result_ids


# --- Backdated reporting: ingestion_time leakage, not just event_time -------------


def test_a_backdated_report_ingested_after_as_of_is_excluded_in_strict_mode(db_session):
    """An event that *happened* before as_of but was only *reported/
    ingested* afterward would not actually have been knowable at that
    historical moment -- see app/intelligence/temporal.py's own
    docstring on why both timestamps are checked by default."""
    org_id = _make_org(db_session)
    as_of = datetime(2026, 6, 1, tzinfo=timezone.utc)

    backdated = _seed(
        db_session, org_id,
        event_time=datetime(2026, 5, 1, tzinfo=timezone.utc),  # happened before as_of
        ingestion_time=datetime(2026, 6, 10, tzinfo=timezone.utc),  # but only ingested after
        source_record_id="backdated",
    )

    strict_query = events_as_of(organization_id=org_id, as_of=as_of, window_start=None, strict_point_in_time=True)
    assert backdated.id not in {e.id for e in db_session.execute(strict_query).scalars().all()}

    lenient_query = events_as_of(organization_id=org_id, as_of=as_of, window_start=None, strict_point_in_time=False)
    assert backdated.id in {e.id for e in db_session.execute(lenient_query).scalars().all()}


# --- Window start filtering --------------------------------------------------------


def test_window_start_excludes_events_before_the_window(db_session):
    org_id = _make_org(db_session)
    as_of = datetime(2026, 6, 30, tzinfo=timezone.utc)
    window_start = datetime(2026, 6, 1, tzinfo=timezone.utc)

    inside = _seed(
        db_session, org_id, event_time=datetime(2026, 6, 15, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 6, 15, tzinfo=timezone.utc), source_record_id="inside",
    )
    outside = _seed(
        db_session, org_id, event_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 5, 1, tzinfo=timezone.utc), source_record_id="outside",
    )

    query = events_as_of(organization_id=org_id, as_of=as_of, window_start=window_start)
    result_ids = {e.id for e in db_session.execute(query).scalars().all()}
    assert inside.id in result_ids
    assert outside.id not in result_ids


# --- Data quality filtering --------------------------------------------------------


def test_quarantined_and_invalid_events_are_excluded_by_default(db_session):
    org_id = _make_org(db_session)
    as_of = datetime(2026, 6, 1, tzinfo=timezone.utc)

    valid = _seed(db_session, org_id, data_quality_status="VALID", source_record_id="v")
    quarantined = _seed(db_session, org_id, data_quality_status="QUARANTINED", source_record_id="q")
    invalid = _seed(db_session, org_id, data_quality_status="INVALID", source_record_id="i")

    query = events_as_of(organization_id=org_id, as_of=as_of, window_start=None)
    result_ids = {e.id for e in db_session.execute(query).scalars().all()}
    assert valid.id in result_ids
    assert quarantined.id not in result_ids
    assert invalid.id not in result_ids

    include_query = events_as_of(organization_id=org_id, as_of=as_of, window_start=None, include_quarantined=True)
    include_ids = {e.id for e in db_session.execute(include_query).scalars().all()}
    assert quarantined.id in include_ids
    assert invalid.id not in include_ids  # include_quarantined does not also include INVALID


# --- Tenant isolation, checked here too (temporal filtering must not leak across orgs) --


def test_events_as_of_never_returns_another_organizations_events(db_session):
    org_a = _make_org(db_session)
    org_b = _make_org(db_session)
    as_of = datetime(2026, 6, 1, tzinfo=timezone.utc)

    event_a = _seed(db_session, org_a, source_record_id="a")
    event_b = _seed(db_session, org_b, source_record_id="b")

    query = events_as_of(organization_id=org_a, as_of=as_of, window_start=None)
    result_ids = {e.id for e in db_session.execute(query).scalars().all()}
    assert event_a.id in result_ids
    assert event_b.id not in result_ids
