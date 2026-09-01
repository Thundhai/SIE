"""Real-data validation & dataset quality reporting — Model Validation &
Governance v0.1, items 5-7. DB-backed (SQLite) tests, covering item 50's
explicit list: valid, incomplete, duplicate, malformed, and insufficient
datasets."""

from datetime import datetime, timedelta, timezone

from app.predictions.data_requirements import (
    DataSufficiencyThresholds,
    check_minimum_requirements,
)
from app.predictions.data_validation import (
    OVERALL_GOOD,
    OVERALL_INSUFFICIENT,
    OVERALL_LIMITED,
    validate_dataset,
)
from app.predictions.dataset_registry import (
    register_real_dataset,
    register_synthetic_dataset,
)
from app.predictions.enums import DatasetEnvironment, ModelValidationStatus
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _seed_valid_dataset(db_session, org_id, site_id, *, count=60):
    for i in range(count):
        t = START + timedelta(days=i)
        db_session.add(
            make_safety_event(
                organization_id=org_id, site_id=site_id, event_type="NEAR_MISS",
                event_time=t, ingestion_time=t, data_quality_status="VALID",
                source_record_id=f"rec-{i}",
            )
        )
    db_session.commit()


def test_a_valid_well_formed_dataset_is_reported_good_or_limited(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_valid_dataset(db_session, org.id, site.id)
    report = validate_dataset(db_session, organization_id=org.id, date_range_start=START, date_range_end=END, as_of=END)
    assert report.record_count == 60
    assert report.quarantined_count == 0
    assert report.invalid_count == 0
    assert report.overall_quality in (OVERALL_GOOD, OVERALL_LIMITED)


def test_an_incomplete_dataset_reports_a_missing_site_rate(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_valid_dataset(db_session, org.id, site.id, count=20)
    # Add records with no site_id at all -- incomplete.
    for i in range(10):
        t = START + timedelta(days=i)
        db_session.add(
            make_safety_event(
                organization_id=org.id, site_id=None, event_type="NEAR_MISS",
                event_time=t, ingestion_time=t, data_quality_status="VALID",
                source_record_id=f"no-site-{i}",
            )
        )
    db_session.commit()
    report = validate_dataset(db_session, organization_id=org.id, date_range_start=START, date_range_end=END, as_of=END)
    assert report.completeness.missing_site_rate == round(10 / 30, 4)


def test_true_intra_organization_duplicates_are_rejected_at_the_database_level(db_session):
    """`SafetyEvent`'s own `UniqueConstraint` on
    `(organization_id, source_system, source_record_id)` means a genuine
    duplicate row can never actually be inserted for the same
    organization -- `validate_dataset()`'s duplicate count exists as
    defense in depth (e.g. against a future bulk-import path with looser
    guarantees), and legitimately reports 0 for any dataset that went
    through this schema's own constraint."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=START, ingestion_time=START, data_quality_status="VALID",
            source_system="system-a", source_record_id="shared-id",
        )
    )
    db_session.commit()

    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=START, ingestion_time=START, data_quality_status="VALID",
            source_system="system-a", source_record_id="shared-id",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    report = validate_dataset(db_session, organization_id=org.id, date_range_start=START, date_range_end=END, as_of=END)
    assert report.record_count == 1
    assert report.duplicate_record_count == 0


def test_a_malformed_dataset_with_quarantined_and_invalid_records_is_reported_insufficient(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    for i, status in enumerate(["QUARANTINED"] * 8 + ["INVALID"] * 8 + ["VALID"] * 4):
        t = START + timedelta(days=i)
        db_session.add(
            make_safety_event(
                organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
                event_time=t, ingestion_time=t, data_quality_status=status,
                source_record_id=f"malformed-{i}",
            )
        )
    db_session.commit()
    report = validate_dataset(db_session, organization_id=org.id, date_range_start=START, date_range_end=END, as_of=END)
    assert report.quarantined_count == 8
    assert report.invalid_count == 8
    assert report.overall_quality == OVERALL_INSUFFICIENT


def test_an_insufficient_empty_dataset_never_fabricates_a_quality_score(db_session):
    org = make_org(db_session)
    make_site(db_session, org.id)
    report = validate_dataset(db_session, organization_id=org.id, date_range_start=START, date_range_end=END, as_of=END)
    assert report.record_count == 0
    assert report.overall_quality == OVERALL_INSUFFICIENT


def test_temporal_integrity_flags_ingestion_before_event_time(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=START + timedelta(days=10), ingestion_time=START,  # ingested before it happened
            data_quality_status="VALID", source_record_id="backwards",
        )
    )
    db_session.commit()
    report = validate_dataset(db_session, organization_id=org.id, date_range_start=START, date_range_end=END, as_of=END)
    codes = {i.code for i in report.temporal_integrity_issues}
    assert "INGESTION_TIME_BEFORE_EVENT_TIME" in codes


def test_freshness_reports_staleness_relative_to_as_of(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=START, ingestion_time=START, data_quality_status="VALID", source_record_id="old",
        )
    )
    db_session.commit()
    report = validate_dataset(
        db_session, organization_id=org.id, date_range_start=START, date_range_end=START + timedelta(days=1),
        as_of=START + timedelta(days=200),
    )
    assert report.freshness.is_stale is True
    assert report.freshness.staleness_days == 200


def test_register_synthetic_dataset_is_tagged_synthetic(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_valid_dataset(db_session, org.id, site.id)
    dv = register_synthetic_dataset(
        db_session, organization_id=org.id, dataset_id="TEST-DS", date_range_start=START, date_range_end=END,
    )
    assert dv.environment == DatasetEnvironment.SYNTHETIC.value
    assert dv.dataset_version == "v1"
    assert dv.record_count == 60


def test_register_real_dataset_is_tagged_real_and_requires_a_named_source_system(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_valid_dataset(db_session, org.id, site.id)
    dv = register_real_dataset(
        db_session, organization_id=org.id, dataset_id="REAL-DS", date_range_start=START, date_range_end=END,
        source_systems=["safelytic"],
    )
    assert dv.environment == DatasetEnvironment.REAL.value

    import pytest

    with pytest.raises(ValueError):
        register_real_dataset(
            db_session, organization_id=org.id, dataset_id="REAL-DS-2", date_range_start=START, date_range_end=END,
            source_systems=[],
        )


def test_dataset_versions_never_mix_synthetic_and_real_silently(db_session):
    """Registering the same dataset_id as both environments produces two
    distinct, separately-versioned rows -- never one row whose
    environment could be ambiguous."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_valid_dataset(db_session, org.id, site.id)
    synthetic = register_synthetic_dataset(
        db_session, organization_id=org.id, dataset_id="SHARED-ID", date_range_start=START, date_range_end=END,
    )
    real = register_real_dataset(
        db_session, organization_id=org.id, dataset_id="SHARED-ID", date_range_start=START, date_range_end=END,
        source_systems=["safelytic"],
    )
    assert synthetic.id != real.id
    assert synthetic.environment != real.environment
    assert {synthetic.dataset_version, real.dataset_version} == {"v1", "v2"}


def test_minimum_data_requirements_flag_insufficient_history(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    # Only 10 days of history -- far short of the default 180-day minimum.
    _seed_valid_dataset(db_session, org.id, site.id, count=10)
    dv = register_synthetic_dataset(
        db_session, organization_id=org.id, dataset_id="SHORT-DS",
        date_range_start=START, date_range_end=START + timedelta(days=10),
    )
    result = check_minimum_requirements(dataset_version=dv)
    assert result.status == ModelValidationStatus.INSUFFICIENT_DATA.value
    assert any(c.name == "minimum_historical_duration" and not c.passed for c in result.checks)


def test_minimum_data_requirements_pass_with_configured_lower_thresholds(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_valid_dataset(db_session, org.id, site.id, count=10)
    dv = register_synthetic_dataset(
        db_session, organization_id=org.id, dataset_id="SHORT-DS-2",
        date_range_start=START, date_range_end=START + timedelta(days=10),
    )
    lenient = DataSufficiencyThresholds(
        min_historical_days=5, min_sites=1, min_exposure_coverage=0.0, min_completeness=0.0,
    )
    result = check_minimum_requirements(dataset_version=dv, thresholds=lenient)
    assert result.status == ModelValidationStatus.SUFFICIENT.value
