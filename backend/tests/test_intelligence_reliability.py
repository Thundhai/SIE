"""Source reliability and freshness — milestone items 32-33, 52. Runs
against `db_session` (SQLite).
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.reliability import compute_source_reliability
from app.models.organization import Organization
from tests.intelligence_test_helpers import make_safety_event

NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="Reliability Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


def _seed(db_session, org_id, **overrides):
    event = make_safety_event(organization_id=org_id, **overrides)
    db_session.add(event)
    db_session.commit()
    return event


def test_record_counts_are_broken_down_by_data_quality_status(db_session):
    org_id = _make_org(db_session)
    _seed(db_session, org_id, source_system="safelytic", source_record_id="1", data_quality_status="VALID",
          ingestion_time=NOW)
    _seed(db_session, org_id, source_system="safelytic", source_record_id="2", data_quality_status="INVALID",
          ingestion_time=NOW)
    _seed(db_session, org_id, source_system="safelytic", source_record_id="3", data_quality_status="QUARANTINED",
          ingestion_time=NOW)

    results = compute_source_reliability(db_session, organization_id=org_id, as_of=NOW)
    safelytic = next(r for r in results if r.source_system == "safelytic")
    assert safelytic.record_count == 3
    assert safelytic.valid_count == 1
    assert safelytic.invalid_count == 1
    assert safelytic.quarantined_count == 1


def test_multiple_source_systems_are_reported_separately(db_session):
    org_id = _make_org(db_session)
    _seed(db_session, org_id, source_system="safelytic", source_record_id="1", ingestion_time=NOW)
    _seed(db_session, org_id, source_system="custom-csv-upload", source_record_id="1", ingestion_time=NOW)

    results = compute_source_reliability(db_session, organization_id=org_id, as_of=NOW)
    source_names = {r.source_system for r in results}
    assert source_names == {"safelytic", "custom-csv-upload"}


# --- Milestone items 32/52: staleness -----------------------------------------------


def test_recently_ingested_data_is_not_stale(db_session):
    org_id = _make_org(db_session)
    _seed(db_session, org_id, source_system="safelytic", source_record_id="1", ingestion_time=NOW - timedelta(days=1))
    results = compute_source_reliability(
        db_session, organization_id=org_id, as_of=NOW, freshness_threshold_days=7
    )
    assert results[0].is_stale is False


def test_data_older_than_the_freshness_threshold_is_stale(db_session):
    org_id = _make_org(db_session)
    _seed(db_session, org_id, source_system="safelytic", source_record_id="1", ingestion_time=NOW - timedelta(days=30))
    results = compute_source_reliability(
        db_session, organization_id=org_id, as_of=NOW, freshness_threshold_days=7
    )
    assert results[0].is_stale is True


def test_tenant_isolation_source_reliability_never_mixes_organizations(db_session):
    org_a = _make_org(db_session)
    org_b = _make_org(db_session)
    _seed(db_session, org_a, source_system="safelytic", source_record_id="1", ingestion_time=NOW)
    _seed(db_session, org_b, source_system="safelytic", source_record_id="1", ingestion_time=NOW)

    results_a = compute_source_reliability(db_session, organization_id=org_a, as_of=NOW)
    assert len(results_a) == 1
    assert results_a[0].record_count == 1
