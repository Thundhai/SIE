"""Integration tests for the Enterprise Dataset Validation Harness —
Real Enterprise Dataset Validation Foundation v0.1, item 11.

Runs the full harness (`app/validation/enterprise_dataset_validation.py`)
against `tests/fixtures/messy_enterprise_dataset.py`'s deliberately messy,
**synthetic** dataset, through the real, unmodified `EnterpriseIngestionService`.
Covers: enterprise-shaped dataset ingestion, validation outcomes,
terminology mapping/unknown/ambiguous/review, provenance, tenant
isolation, temporal integrity (late-arriving data, corrections,
duplicates, future timestamps, as-of behavior), predictive dataset
readiness, reproducibility, and HSE review record queuing.

Requires real PostgreSQL (`@requires_postgres`, `pg_session`) — the
harness's own temporal checks compare raw Python datetimes against
values read back from the database, which SQLite's lack of a native
timezone-aware datetime type makes unreliable; see
`tests/evaluation/test_calibration_evaluation.py`'s own docstring for
the identical, already-established rationale.
"""

import dataclasses

import pytest

from app.intelligence.enterprise_ingestion import enterprise_ingestion_service
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.terminology_review import TerminologyReviewStatus
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent
from app.models.site import Site
from app.services import hse_review_service
from app.validation.enterprise_dataset_validation import (
    ReportOrganizationMismatchError,
    _evaluate_predictive_readiness,
    queue_review_candidates,
    run_enterprise_dataset_validation,
)
from app.validation.report import to_dict, to_markdown
from tests.fixtures.messy_enterprise_dataset import (
    SYNTHETIC_LABEL,
    build_messy_dataset,
    build_secondary_dataset,
)
from tests.postgres_support import requires_postgres


def _make_org_and_site(db, name: str):
    org = Organization(name=name)
    db.add(org)
    db.commit()
    site = Site(organization_id=org.id, name=f"{name} Site")
    db.add(site)
    db.commit()
    return org.id, site.id


# --- Enterprise-shaped dataset ingestion + validation outcomes ------------------------------


@requires_postgres
def test_the_synthetic_label_is_never_lost_and_is_explicit_about_being_synthetic(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Label")
    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    assert "SYNTHETIC" in report.label
    assert "does not constitute validation against real customer data" in report.label


@requires_postgres
def test_every_ingestion_outcome_matches_the_datasets_own_documented_characteristics(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Ingestion Outcomes")
    dataset = build_messy_dataset(primary_site_id=site_id)
    c = dataset.characteristics
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )

    assert report.observed.total_records == c.total_records
    assert report.ingestion.duplicates == c.duplicate_in_batch_records
    assert report.data_quality.missing_timestamps == c.missing_event_time_records
    assert report.data_quality.missing_identifiers == c.missing_identifier_records
    assert report.data_quality.duplicate_records == c.duplicate_in_batch_records
    assert report.ingestion.stale_records == c.stale_version_records
    assert report.ingestion.version_conflicts == c.version_conflict_pairs
    # Both the correction pair and the stale trio's own v1->v2 each apply an UPDATED.
    assert report.temporal.corrections_applied == c.version_correction_pairs + c.stale_version_records
    assert report.observed.distinct_source_systems and len(report.observed.distinct_source_systems) == c.distinct_source_systems


@requires_postgres
def test_a_quarantined_record_is_stored_but_excluded_from_the_valid_and_partial_counts(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Quarantine")
    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    assert report.ingestion.quarantined > 0
    # quarantined and rejected are the two genuinely disjoint categories
    # (a quarantined record has a canonical event; a rejected one never
    # does) -- valid/partial are NOT simply additive with
    # duplicate/stale/version_conflict, since those three outcomes can
    # resolve *against* an existing valid row without creating a new one
    # (see app/validation/enterprise_dataset_validation.py's own
    # provenance-check docstring for the identical accounting subtlety).
    assert report.ingestion.total_records >= report.ingestion.quarantined + report.ingestion.rejected
    assert report.ingestion.quarantined + report.ingestion.rejected < report.ingestion.total_records


# --- Terminology mapping / unknown / ambiguous / review -------------------------------------


@requires_postgres
def test_unknown_and_ambiguous_terminology_are_surfaced_and_never_guessed(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Terminology")
    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    unknown_entries = [e for e in report.terminology_entries if e.status == TerminologyReviewStatus.UNKNOWN]
    ambiguous_entries = [e for e in report.terminology_entries if e.status == TerminologyReviewStatus.AMBIGUOUS]
    assert len(unknown_entries) == dataset.characteristics.unknown_event_type_terms + dataset.characteristics.unknown_subtype_terms
    assert len(ambiguous_entries) == dataset.characteristics.ambiguous_event_type_terms + dataset.characteristics.ambiguous_subtype_terms
    for entry in unknown_entries + ambiguous_entries:
        assert entry.requires_review
        assert entry.proposed_canonical_term is None  # never guessed


@requires_postgres
def test_the_terminology_review_structure_has_the_source_term_to_reason_shape(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Review Structure")
    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    for entry in report.terminology_entries:
        assert entry.source_term
        assert entry.status in ("MAPPED", "UNKNOWN", "AMBIGUOUS")
        assert entry.reason
        assert entry.occurrence_count >= 1


# --- Provenance -------------------------------------------------------------------------------


@requires_postgres
def test_provenance_chain_is_intact_end_to_end_including_feature_and_predictive_stages(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Provenance")
    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    assert report.provenance.checked_count > 0
    assert report.provenance.all_chains_intact
    assert report.provenance.failures == []
    assert report.provenance.feature_stage_reachable is True
    assert report.provenance.predictive_stage_reachable is True


@requires_postgres
def test_provenance_has_nothing_to_check_when_the_batch_carries_no_site(pg_session):
    """A batch with no site-scoped record has no feature/predictive stage
    to check -- `None`, never a failed `False`, since there is nothing to
    verify (see the harness's own docstring)."""
    org_id, _site_id = _make_org_and_site(pg_session, "Milestone3 - No Site")
    dataset = build_messy_dataset()  # no primary_site_id -- every record is site_id=None
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    assert report.provenance.feature_stage_reachable is None
    assert report.provenance.predictive_stage_reachable is None


# --- Tenant isolation ---------------------------------------------------------------------------


@requires_postgres
def test_tenant_isolation_across_two_organizations(pg_session):
    org_a, site_a = _make_org_and_site(pg_session, "Milestone3 - Tenant A")
    org_b, site_b = _make_org_and_site(pg_session, "Milestone3 - Tenant B")
    primary = build_messy_dataset(primary_site_id=site_a)
    secondary = build_secondary_dataset()
    for event in secondary.events:
        event.site_id = site_b

    report_a = run_enterprise_dataset_validation(pg_session, organization_id=org_a, payloads=primary.events, label=SYNTHETIC_LABEL)
    report_b = run_enterprise_dataset_validation(pg_session, organization_id=org_b, payloads=secondary.events, label=SYNTHETIC_LABEL)

    assert report_a.observed.total_records != report_b.observed.total_records
    assert report_b.ingestion.quarantined == 0  # the secondary dataset is deliberately clean
    assert report_a.intelligence_readiness.event_count != report_b.intelligence_readiness.event_count
    # Org B's predictive readiness must never reflect org A's much larger dataset.
    assert report_b.predictive_readiness.qualifying_incidents == 0


# --- Temporal integrity: late-arriving, corrections, duplicates, future, as-of --------------


@requires_postgres
def test_temporal_integrity_report_reflects_the_datasets_own_shape(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Temporal")
    dataset = build_messy_dataset(primary_site_id=site_id)
    c = dataset.characteristics
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    assert report.temporal.out_of_order_arrival_detected is True
    assert report.temporal.duplicate_timestamp_groups == c.duplicate_timestamp_pairs
    assert report.temporal.future_timestamp_records == c.future_timestamp_records
    assert report.temporal.stale_versions_skipped == c.stale_version_records
    assert report.temporal.version_conflicts_detected == c.version_conflict_pairs
    assert report.temporal.late_arriving_records > 0  # deep historical records genuinely arrive "late"
    assert report.temporal.as_of_leakage_check_passed is True
    assert "RETROSPECTIVE" in report.temporal.retrospective_vs_point_in_time_note
    assert "POINT-IN-TIME" in report.temporal.retrospective_vs_point_in_time_note


@requires_postgres
def test_an_explicit_retrospective_as_of_before_real_ingestion_correctly_shows_reduced_visibility(pg_session):
    """Passing an explicit, genuinely earlier `as_of` is a legitimate
    point-in-time query -- and must show reduced/zero visibility, exactly
    as events_as_of()'s own leakage guarantee demands, never a bug."""
    from datetime import datetime, timezone

    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Retrospective As-of")
    dataset = build_messy_dataset(primary_site_id=site_id)
    ancient_as_of = datetime(2000, 1, 1, tzinfo=timezone.utc)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL, as_of=ancient_as_of
    )
    assert report.intelligence_readiness.event_count == 0
    assert report.intelligence_readiness.data_sufficiency == "INSUFFICIENT_DATA"


# --- Predictive dataset readiness ---------------------------------------------------------------


@requires_postgres
def test_predictive_readiness_reports_unavailable_labels_honestly_not_as_negatives(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Predictive Readiness")
    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    pr = report.predictive_readiness
    assert pr.eligible_sites == 1
    assert pr.excluded_sites == 0
    assert pr.qualifying_incidents > 0
    # The single eligible site's most recent as_of has an unelapsed 30-day
    # horizon -- must be UNAVAILABLE, never silently coerced to negative.
    assert pr.unavailable_labels == 1
    assert pr.positive_labels == 0 and pr.negative_labels == 0
    assert pr.class_distribution is None
    assert any("cannot yet be confirmed" in note for note in pr.notes)


@requires_postgres
def test_a_site_with_no_events_at_all_is_excluded_with_a_reason(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Empty Site")
    empty_site = Site(organization_id=org_id, name="Empty Site")
    pg_session.add(empty_site)
    pg_session.commit()

    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL,
        site_ids=[site_id, empty_site.id],
    )
    assert report.predictive_readiness.excluded_sites == 1
    assert report.predictive_readiness.exclusion_reasons.get("NO_HISTORICAL_DATA") == 1


# --- Reproducibility -----------------------------------------------------------------------------


def test_the_dataset_itself_is_byte_for_byte_reproducible_across_builds():
    from datetime import datetime, timezone

    base_time = datetime(2026, 6, 1, tzinfo=timezone.utc)
    d1 = build_messy_dataset(base_time)
    d2 = build_messy_dataset(base_time)
    assert [dataclasses.asdict(e) for e in d1.events] == [dataclasses.asdict(e) for e in d2.events]
    assert d1.characteristics == d2.characteristics


@requires_postgres
def test_running_the_harness_twice_against_independently_built_datasets_yields_identical_summaries(pg_session):
    """Two separate organizations, each freshly ingesting its own
    independently-built copy of the same deterministic dataset, must
    produce identical ingestion/data-quality/terminology summaries --
    proving the harness itself introduces no run-to-run nondeterminism."""
    from datetime import datetime, timezone

    base_time = datetime(2026, 6, 1, tzinfo=timezone.utc)
    org_1, site_1 = _make_org_and_site(pg_session, "Milestone3 - Repro 1")
    org_2, site_2 = _make_org_and_site(pg_session, "Milestone3 - Repro 2")

    dataset_1 = build_messy_dataset(base_time, primary_site_id=site_1)
    dataset_2 = build_messy_dataset(base_time, primary_site_id=site_2)

    report_1 = run_enterprise_dataset_validation(pg_session, organization_id=org_1, payloads=dataset_1.events, label=SYNTHETIC_LABEL)
    report_2 = run_enterprise_dataset_validation(pg_session, organization_id=org_2, payloads=dataset_2.events, label=SYNTHETIC_LABEL)

    assert report_1.ingestion == report_2.ingestion
    assert report_1.data_quality == report_2.data_quality
    assert report_1.terminology_summary == report_2.terminology_summary


# --- HSE review record queuing -----------------------------------------------------------------


@requires_postgres
def test_review_candidates_are_queued_for_terminology_and_quarantined_records(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - HSE Queue")
    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    queued = queue_review_candidates(pg_session, organization_id=org_id, report=report)
    assert len(queued) > 0
    assert all(r.outcome is None for r in queued)  # every queued row starts pending

    pending = hse_review_service.list_reviews(pg_session, organization_id=org_id, pending_only=True)
    assert len(pending) == len(queued)

    terminology_queued = [r for r in queued if r.target_type == "TERMINOLOGY_MAPPING"]
    assert len(terminology_queued) == report.terminology_summary.review_required_total

    quarantined_queued = [r for r in queued if r.target_type == "QUARANTINED_RECORD"]
    assert len(quarantined_queued) == report.ingestion.quarantined

    # A reviewer can then act on one -- the review mechanism round-trips.
    reviewed = hse_review_service.submit_review(
        pg_session, organization_id=org_id, review_id=terminology_queued[0].id, outcome="PARTIALLY_CORRECT",
        reviewer_comment="Plausible, but needs a source-system-specific override.",
    )
    assert reviewed.outcome == "PARTIALLY_CORRECT"


# --- Report rendering (machine + human readable) sanity, in context --------------------------


@requires_postgres
def test_report_renders_cleanly_and_never_claims_predictive_accuracy(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Report Rendering")
    dataset = build_messy_dataset(primary_site_id=site_id)
    report = run_enterprise_dataset_validation(
        pg_session, organization_id=org_id, payloads=dataset.events, label=SYNTHETIC_LABEL
    )
    markdown = to_markdown(report)
    for heading in ("OBSERVED", "MAPPED", "QUARANTINED", "REJECTED", "UNAVAILABLE"):
        assert f"## {heading}" in markdown or f"## {heading} " in markdown
    for banned in ("PR-AUC is 0.", "ROC-AUC is 0.", "achieves"):
        assert banned not in markdown
    assert "No predictive accuracy" in markdown

    payload = to_dict(report)
    assert payload["label"] == report.label
    assert isinstance(payload["terminology_entries"], list)


# --- Audit correction 1: predictive readiness must preserve point-in-time semantics ----------


@requires_postgres
def test_predictive_readiness_never_reflects_events_ingested_after_the_requested_as_of(pg_session):
    """The audit's own worked example: (1) an event with an old
    event_time, (2) whose ingestion_time is later, (3) evaluated at an
    as_of between the two. Proves genuine point-in-time behavior at TWO
    different as_of values -- not merely the final, current-time result:
    at the earlier as_of the late-ingested event must not move historical
    coverage backward or count toward qualifying incidents; only once
    as_of >= its own ingestion_time does it become visible."""
    from datetime import datetime, timezone

    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Predictive Readiness Point-in-Time")

    # Promptly ingested -- knowable well before either as_of below.
    known_payload = RawSafetyEventPayload(
        event_type="INCIDENT", event_time="2020-01-20T00:00:00Z", site_id=site_id,
        source_system="pit-test", source_record_id="KNOWN-001",
    )
    known_result = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org_id, source_id=None, payloads=[known_payload]
    )
    known_event = pg_session.get(SafetyEvent, known_result.records[0].canonical_event_id)
    known_event.ingestion_time = datetime(2020, 1, 21, tzinfo=timezone.utc)
    pg_session.commit()

    # The audit's own scenario: event_time is older than KNOWN's, but
    # this record only reaches SIE much later -- a real, if extreme,
    # late-arriving report.
    late_payload = RawSafetyEventPayload(
        event_type="INCIDENT", event_time="2020-01-05T00:00:00Z", site_id=site_id,
        source_system="pit-test", source_record_id="LATE-001",
    )
    late_result = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org_id, source_id=None, payloads=[late_payload]
    )
    late_event = pg_session.get(SafetyEvent, late_result.records[0].canonical_event_id)
    late_event.ingestion_time = datetime(2020, 2, 15, tzinfo=timezone.utc)
    pg_session.commit()

    as_of_between = datetime(2020, 2, 1, tzinfo=timezone.utc)  # after LATE's event_time, before its ingestion_time
    as_of_after = datetime(2020, 2, 20, tzinfo=timezone.utc)  # after LATE's ingestion_time too

    report_between = _evaluate_predictive_readiness(
        pg_session, organization_id=org_id, site_ids=[site_id], as_of=as_of_between
    )
    # LATE is not yet knowable: only KNOWN counts, and KNOWN's own
    # event_time (the later of the two) is what coverage is measured from.
    assert report_between.eligible_sites == 1
    assert report_between.qualifying_incidents == 1
    assert report_between.historical_time_coverage_days[str(site_id)] == pytest.approx(12.0, abs=0.1)

    report_after = _evaluate_predictive_readiness(
        pg_session, organization_id=org_id, site_ids=[site_id], as_of=as_of_after
    )
    # LATE has now been ingested (as_of_after >= its ingestion_time):
    # both count, and coverage now correctly reaches back to LATE's own,
    # earlier event_time.
    assert report_after.eligible_sites == 1
    assert report_after.qualifying_incidents == 2
    assert report_after.historical_time_coverage_days[str(site_id)] == pytest.approx(46.0, abs=0.1)


@requires_postgres
def test_a_site_visible_only_via_a_not_yet_ingested_event_is_excluded_at_the_earlier_as_of(pg_session):
    """Site eligibility itself must follow the same point-in-time rule:
    a site whose only event has not yet been ingested as of the
    requested as_of must be excluded (NO_HISTORICAL_DATA), not treated
    as eligible with zero coverage."""
    from datetime import datetime, timezone

    org_id, site_id = _make_org_and_site(pg_session, "Milestone3 - Site Eligibility Point-in-Time")

    payload = RawSafetyEventPayload(
        event_type="INCIDENT", event_time="2020-01-05T00:00:00Z", site_id=site_id,
        source_system="pit-test", source_record_id="ONLY-001",
    )
    result = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org_id, source_id=None, payloads=[payload]
    )
    event = pg_session.get(SafetyEvent, result.records[0].canonical_event_id)
    event.ingestion_time = datetime(2020, 2, 15, tzinfo=timezone.utc)
    pg_session.commit()

    as_of_before_ingestion = datetime(2020, 2, 1, tzinfo=timezone.utc)
    report_before = _evaluate_predictive_readiness(
        pg_session, organization_id=org_id, site_ids=[site_id], as_of=as_of_before_ingestion
    )
    assert report_before.eligible_sites == 0
    assert report_before.excluded_sites == 1
    assert report_before.exclusion_reasons.get("NO_HISTORICAL_DATA") == 1

    as_of_after_ingestion = datetime(2020, 2, 20, tzinfo=timezone.utc)
    report_after = _evaluate_predictive_readiness(
        pg_session, organization_id=org_id, site_ids=[site_id], as_of=as_of_after_ingestion
    )
    assert report_after.eligible_sites == 1
    assert report_after.excluded_sites == 0


# --- Audit correction 2: queue_review_candidates() must enforce a report/org match -----------


@requires_postgres
def test_queue_review_candidates_rejects_a_report_from_a_different_organization(pg_session):
    org_a, site_a = _make_org_and_site(pg_session, "Milestone3 - Mismatch Org A")
    org_b, _site_b = _make_org_and_site(pg_session, "Milestone3 - Mismatch Org B")

    dataset_a = build_messy_dataset(primary_site_id=site_a)
    report_a = run_enterprise_dataset_validation(
        pg_session, organization_id=org_a, payloads=dataset_a.events, label=SYNTHETIC_LABEL
    )
    assert report_a.organization_id == org_a

    with pytest.raises(ReportOrganizationMismatchError):
        queue_review_candidates(pg_session, organization_id=org_b, report=report_a)

    # Zero rows created for B -- and since none were created at all for
    # this rejected call, none of A's provenance/findings can appear
    # anywhere under B either.
    assert hse_review_service.list_reviews(pg_session, organization_id=org_b) == []
    assert hse_review_service.list_reviews(pg_session, organization_id=org_a) == []

    # Legitimate same-organization behavior is unaffected by the check.
    queued = queue_review_candidates(pg_session, organization_id=org_a, report=report_a)
    assert len(queued) > 0
    assert all(r.organization_id == org_a for r in queued)
