"""Deterministic label generation — milestone item 6. DB-backed (SQLite)
tests over `generate_label()`."""

from datetime import datetime, timedelta, timezone

from app.predictions.labels import generate_label
from app.predictions.spec import HORIZON_DAYS, LABEL_DEFINITION_VERSION
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_label_is_one_when_a_qualifying_incident_occurs_within_the_horizon(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF + timedelta(days=10), data_quality_status="VALID",
        )
    )
    db_session.commit()

    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 1
    assert result.label_definition_version == LABEL_DEFINITION_VERSION
    assert result.horizon_days == HORIZON_DAYS


def test_label_is_zero_when_no_qualifying_incident_occurs(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 0
    assert result.supporting_event_ids == []


def test_near_misses_and_observations_never_create_a_positive_label(db_session):
    """Milestone item 4: the target is never casually equated with
    leading-indicator report types."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    for event_type in ("NEAR_MISS", "OBSERVATION"):
        db_session.add(
            make_safety_event(
                organization_id=org.id, site_id=site.id, event_type=event_type,
                event_time=AS_OF + timedelta(days=5),
            )
        )
    db_session.commit()
    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 0


def test_quarantined_or_invalid_future_incidents_never_flip_the_label(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    for status in ("QUARANTINED", "INVALID"):
        db_session.add(
            make_safety_event(
                organization_id=org.id, site_id=site.id, event_type="INCIDENT",
                event_time=AS_OF + timedelta(days=5), data_quality_status=status,
            )
        )
    db_session.commit()
    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 0


def test_an_incident_exactly_at_as_of_does_not_count_horizon_start_is_exclusive(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF, data_quality_status="VALID",
        )
    )
    db_session.commit()
    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 0


def test_an_incident_exactly_at_horizon_end_counts_horizon_end_is_inclusive(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    horizon_end = AS_OF + timedelta(days=HORIZON_DAYS)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=horizon_end, data_quality_status="VALID",
        )
    )
    db_session.commit()
    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 1


def test_an_incident_beyond_the_horizon_never_counts(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF + timedelta(days=HORIZON_DAYS + 1), data_quality_status="VALID",
        )
    )
    db_session.commit()
    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 0


def test_an_incident_at_a_different_site_never_counts(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    other_site = make_site(db_session, org.id, name="Other Site")
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=other_site.id, event_type="INCIDENT",
            event_time=AS_OF + timedelta(days=5), data_quality_status="VALID",
        )
    )
    db_session.commit()
    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 0
