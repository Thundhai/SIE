"""Exposure normalization — milestone items 18/51. Runs against
`db_session` (SQLite) — plain datetime/aggregation, no pgvector needed.
"""

import uuid
from datetime import datetime, timezone

from app.intelligence.exposure import (
    EXPOSURE_DATA_UNAVAILABLE,
    compute_exposure_hours,
    normalize_rate_per_100k_hours,
)
from app.models.organization import Organization
from tests.intelligence_test_helpers import make_safety_event


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="Exposure Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


def _seed_exposure(db_session, org_id, hours, **overrides):
    event = make_safety_event(
        organization_id=org_id,
        event_type="WORKFORCE",
        event_subtype="EXPOSURE_HOURS",
        attributes={"hours": hours},
        **overrides,
    )
    db_session.add(event)
    db_session.commit()
    return event


def test_compute_exposure_hours_sums_matching_records(db_session):
    org_id = _make_org(db_session)
    as_of = datetime(2026, 6, 30, tzinfo=timezone.utc)
    window_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    _seed_exposure(
        db_session, org_id, 5000,
        event_time=datetime(2026, 6, 10, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 6, 10, tzinfo=timezone.utc),
        source_record_id="exp-1",
    )
    _seed_exposure(
        db_session, org_id, 5000,
        event_time=datetime(2026, 6, 20, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 6, 20, tzinfo=timezone.utc),
        source_record_id="exp-2",
    )

    total = compute_exposure_hours(db_session, organization_id=org_id, as_of=as_of, window_start=window_start)
    assert total == 10000.0


def test_compute_exposure_hours_returns_none_when_no_records_exist(db_session):
    org_id = _make_org(db_session)
    as_of = datetime(2026, 6, 30, tzinfo=timezone.utc)
    window_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    total = compute_exposure_hours(db_session, organization_id=org_id, as_of=as_of, window_start=window_start)
    assert total is None


def test_compute_exposure_hours_ignores_other_workforce_subtypes(db_session):
    org_id = _make_org(db_session)
    as_of = datetime(2026, 6, 30, tzinfo=timezone.utc)
    window_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    other = make_safety_event(
        organization_id=org_id,
        event_type="WORKFORCE",
        event_subtype="HEADCOUNT",
        attributes={"headcount": 50},
        event_time=datetime(2026, 6, 10, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 6, 10, tzinfo=timezone.utc),
        source_record_id="headcount-1",
    )
    db_session.add(other)
    db_session.commit()

    total = compute_exposure_hours(db_session, organization_id=org_id, as_of=as_of, window_start=window_start)
    assert total is None


# --- The milestone's own worked example (items 18/51) ------------------------------


def test_normalize_rate_per_100k_hours_reflects_differing_exposure_for_equal_counts():
    """Site A: 10 incidents / 10,000 hours. Site B: 10 incidents / 500
    hours. Equal raw counts must NOT produce an equal reported rate."""
    rate_a = normalize_rate_per_100k_hours(10, 10000)
    rate_b = normalize_rate_per_100k_hours(10, 500)
    assert rate_a != rate_b
    assert rate_a == 100.0
    assert rate_b == 2000.0
    assert rate_b > rate_a


def test_normalize_rate_returns_the_unavailable_sentinel_never_a_fabricated_number():
    assert normalize_rate_per_100k_hours(10, None) == EXPOSURE_DATA_UNAVAILABLE
    assert normalize_rate_per_100k_hours(10, 0) == EXPOSURE_DATA_UNAVAILABLE
