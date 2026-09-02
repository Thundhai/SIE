"""Enterprise Dataset Validation Harness — Real Enterprise Dataset
Validation Foundation v0.1.

Answers exactly one question: *when real enterprise HSE data is
provided, can SIE ingest it, validate it, normalize it, preserve
provenance and temporal integrity, and determine whether the existing
intelligence and predictive pipelines have sufficient trustworthy data
to operate?* It does **not** attempt to prove predictive accuracy — see
`app/predictions/dataset.py`'s own feature/label-separation guarantees
for that boundary, unchanged here.

    RawSafetyEventPayload[] (already-in-hand raw records, from a real
    integration, a fixture, or a subsequent anonymized-customer supply)
        -> EnterpriseIngestionService.ingest_batch()      (UNCHANGED, reused)
        -> IngestionSummary + DataQualitySummary           (item 2)
        -> TerminologyReviewReport                         (item 3, via
           app/intelligence/terminology_review.py)
        -> TemporalIntegrityReport                         (item 4)
        -> ProvenanceValidationReport                       (item 5)
        -> IntelligenceReadinessReport                      (item 6)
        -> PredictiveReadinessReport                         (item 7)
        -> EnterpriseDatasetValidationReport (the above, assembled)

Every ingestion, validation, normalization, analytics, signal, anomaly,
and predictive-dataset call this module makes is the exact, unmodified
code prior milestones already built — `EnterpriseIngestionService`,
`SafetyEventIngestionService`, `app/intelligence/validation.py`/
`normalization.py`, `events_as_of()`/`bucketed_counts()`,
`compute_summary()`/`compute_trend()`, `risk_signal_service`,
`detect_anomaly()`, `get_or_build_feature_snapshot()`,
`build_training_example()`/`generate_label()`. This module adds no new
analytical logic — it orchestrates existing calls and reports what they
already say, exactly the "thin orchestration wrapper" shape
`app/intelligence/enterprise_ingestion.py` itself uses.

**Never tunes a threshold to make a dataset look better.** Every
`INTELLIGENCE_*`/`app/predictions/spec.py` constant used below is
whatever this codebase already has configured; if a result looks poor or
unexpected, this module reports it, with the underlying data, and moves
on — it never adjusts a threshold to produce a more desirable outcome
(item 6's own instruction).

**Never interprets missing data as evidence of absence.** A label that
cannot yet be confirmed (its prediction horizon has not fully elapsed),
a feature that has no data to compute from, a site excluded from
predictive readiness — every one of these is reported as `UNAVAILABLE`/
excluded with a reason, never silently coerced into a negative or a
zero (item 10's own instruction, carried through this whole module).
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.intelligence.analytics import (
    TREND_METRIC_REGISTRY,
    compute_summary,
    compute_trend,
)
from app.intelligence.anomaly import detect_anomaly
from app.intelligence.enterprise_ingestion import (
    EnterpriseIngestionResult,
    enterprise_ingestion_service,
)
from app.intelligence.enums import IngestionOutcome
from app.intelligence.normalization import normalize_datetime
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.signals import risk_signal_service
from app.intelligence.temporal import bucketed_counts, events_as_of, utcnow
from app.intelligence.terminology_mapping import TerminologyMappingAdapter
from app.intelligence.terminology_review import (
    TerminologyReviewEntry,
    TerminologyReviewSummary,
    build_terminology_review,
)
from app.models.data_source import DataSource
from app.models.enterprise_ingestion_record import EnterpriseIngestionRecord
from app.models.safety_event import SafetyEvent
from app.predictions.dataset import build_training_example
from app.predictions.feature_snapshot_service import get_or_build_feature_snapshot
from app.predictions.spec import HORIZON_DAYS, QUALIFYING_EVENT_TYPE
from app.services.hse_review_service import queue_for_review

SYNTHETIC_VALIDATION_LABEL = (
    "Synthetic validation only. Passing this harness against a "
    "synthetic, enterprise-shaped fixture does NOT constitute validation "
    "against real customer data. See docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md."
)

_MISSING_IDENTIFIER_ISSUE_CODES = {"MISSING_SOURCE_SYSTEM", "MISSING_SOURCE_RECORD_ID", "MALFORMED_SOURCE_RECORD_ID"}
_MISSING_TIMESTAMP_ISSUE_CODES = {"MISSING_EVENT_TIME"}
_INVALID_TIMESTAMP_ISSUE_CODES = {"INVALID_EVENT_TIME"}
_INVALID_CLASSIFICATION_ISSUE_CODES = {
    "UNRECOGNIZED_EVENT_TYPE", "INVALID_SEVERITY", "INVALID_POTENTIAL_SEVERITY",
    "AMBIGUOUS_EVENT_TYPE_MAPPING", "UNKNOWN_EVENT_TYPE_MAPPING",
    "AMBIGUOUS_SUBTYPE_MAPPING", "UNKNOWN_SUBTYPE_MAPPING",
}
_INCONSISTENT_VALUE_ISSUE_CODES = {"IMPOSSIBLE_DURATION"}
_MALFORMED_RECORD_ISSUE_CODES = {"INGESTION_ERROR"}


# --- Item 2: ingestion + data-quality summaries ----------------------------------------------


@dataclass
class IngestionSummary:
    total_records: int = 0
    successfully_processed: int = 0  # CREATED + UPDATED -- a canonical event resulted
    valid: int = 0
    partial: int = 0
    quarantined: int = 0
    rejected: int = 0
    duplicates: int = 0
    stale_records: int = 0
    version_conflicts: int = 0


@dataclass
class DataQualitySummary:
    missing_identifiers: int = 0
    missing_timestamps: int = 0
    invalid_timestamps: int = 0
    future_timestamps: int = 0
    invalid_classifications: int = 0
    incomplete_records: int = 0  # PARTIAL quality_state -- usable, but with a non-critical issue
    inconsistent_values: int = 0
    duplicate_records: int = 0
    malformed_records: int = 0


def _issue_codes(record: EnterpriseIngestionRecord) -> set[str]:
    return {issue["code"] for issue in (record.rejection_reason or [])}


def _summarize_ingestion(result: EnterpriseIngestionResult, *, reference_now: datetime) -> tuple[IngestionSummary, DataQualitySummary]:
    batch = result.batch
    ingestion = IngestionSummary(
        total_records=batch.total_records,
        successfully_processed=sum(
            1 for r in result.records if r.outcome in (IngestionOutcome.CREATED.value, IngestionOutcome.UPDATED.value)
        ),
        valid=batch.accepted_records,
        partial=batch.partial_records,
        quarantined=batch.quarantined_records,
        rejected=batch.rejected_records,
        duplicates=batch.duplicate_records,
        stale_records=sum(1 for r in result.records if r.outcome == IngestionOutcome.SKIPPED_STALE_VERSION.value),
        version_conflicts=sum(1 for r in result.records if r.outcome == IngestionOutcome.REJECTED_VERSION_CONFLICT.value),
    )

    quality = DataQualitySummary(duplicate_records=ingestion.duplicates)
    for record in result.records:
        codes = _issue_codes(record)
        if codes & _MISSING_IDENTIFIER_ISSUE_CODES:
            quality.missing_identifiers += 1
        if codes & _MISSING_TIMESTAMP_ISSUE_CODES:
            quality.missing_timestamps += 1
        if codes & _INVALID_TIMESTAMP_ISSUE_CODES:
            quality.invalid_timestamps += 1
        if codes & _INVALID_CLASSIFICATION_ISSUE_CODES:
            quality.invalid_classifications += 1
        if codes & _INCONSISTENT_VALUE_ISSUE_CODES:
            quality.inconsistent_values += 1
        if codes & _MALFORMED_RECORD_ISSUE_CODES:
            quality.malformed_records += 1
        if record.quality_state == "PARTIAL":
            quality.incomplete_records += 1

    return ingestion, quality


def _count_future_timestamps(payloads: list[RawSafetyEventPayload], *, reference_now: datetime) -> int:
    """A structural property of the raw data, not a validation-issue
    code -- only an *implausibly* far future date is flagged as an issue
    by `app/intelligence/validation.py` (a scheduled inspection or
    permit due date legitimately has a near-future `event_time`). Counted
    directly from the parsed timestamps so the report reflects "how many
    records are dated after now," a genuinely useful data-quality signal
    on its own."""
    count = 0
    for payload in payloads:
        parsed = normalize_datetime(payload.event_time)
        if parsed is not None and parsed > reference_now:
            count += 1
    return count


# --- Item 4: temporal integrity ---------------------------------------------------------------


@dataclass
class TemporalIntegrityReport:
    out_of_order_arrival_detected: bool = False
    duplicate_timestamp_groups: int = 0
    future_timestamp_records: int = 0
    corrections_applied: int = 0  # UPDATED
    stale_versions_skipped: int = 0  # SKIPPED_STALE_VERSION
    version_conflicts_detected: int = 0  # REJECTED_VERSION_CONFLICT
    late_arriving_records: int = 0  # ingestion_time meaningfully after event_time (see below)
    as_of_leakage_check_passed: bool | None = None
    retrospective_vs_point_in_time_note: str = ""
    notes: list[str] = field(default_factory=list)


_LATE_ARRIVAL_THRESHOLD_HOURS = 24
_RETROSPECTIVE_VS_POINT_IN_TIME_NOTE = (
    "Two distinct questions, never conflated: RETROSPECTIVE analysis ('what actually "
    "happened historically?') can query every accepted canonical event regardless of "
    "when it was ingested. POINT-IN-TIME intelligence ('what was knowable as of a "
    "particular moment?') uses events_as_of()'s strict ingestion_time <= as_of filter "
    "(app/intelligence/temporal.py, UNCHANGED) and will, correctly, exclude backfilled "
    "history from any as_of before it was actually ingested -- see "
    "docs/CALIBRATION_METHODOLOGY.md's own 'bulk backfill' finding (Milestone 2), "
    "reconfirmed, not re-litigated, here. This harness never weakens that filter to "
    "make a backfilled dataset look more complete."
)


def _validate_temporal_integrity(
    db: Session, *, organization_id: uuid.UUID, payloads: list[RawSafetyEventPayload],
    result: EnterpriseIngestionResult, reference_now: datetime,
) -> TemporalIntegrityReport:
    report = TemporalIntegrityReport(retrospective_vs_point_in_time_note=_RETROSPECTIVE_VS_POINT_IN_TIME_NOTE)

    parsed_times = [normalize_datetime(p.event_time) for p in payloads]
    parsed_times = [t for t in parsed_times if t is not None]
    report.out_of_order_arrival_detected = parsed_times != sorted(parsed_times)

    timestamp_counts = Counter(parsed_times)
    report.duplicate_timestamp_groups = sum(1 for c in timestamp_counts.values() if c > 1)

    report.future_timestamp_records = _count_future_timestamps(payloads, reference_now=reference_now)
    report.corrections_applied = sum(1 for r in result.records if r.outcome == IngestionOutcome.UPDATED.value)
    report.stale_versions_skipped = sum(
        1 for r in result.records if r.outcome == IngestionOutcome.SKIPPED_STALE_VERSION.value
    )
    report.version_conflicts_detected = sum(
        1 for r in result.records if r.outcome == IngestionOutcome.REJECTED_VERSION_CONFLICT.value
    )

    canonical_event_ids = [r.canonical_event_id for r in result.records if r.canonical_event_id is not None]
    late_count = 0
    if canonical_event_ids:
        events = db.execute(select(SafetyEvent).where(SafetyEvent.id.in_(canonical_event_ids))).scalars().all()
        for event in events:
            if event.ingestion_time - event.event_time > timedelta(hours=_LATE_ARRIVAL_THRESHOLD_HOURS):
                late_count += 1
    report.late_arriving_records = late_count

    # The milestone's own point-in-time leakage check, unchanged from
    # the existing regression suite's own worked example (item 4/5):
    # a snapshot taken well before this ingestion happened must never
    # see any of the just-ingested rows, no matter how old their
    # event_time claims to be.
    pre_ingestion_snapshot = reference_now - timedelta(days=3650)
    visible_before = {
        e.id for e in db.execute(
            events_as_of(organization_id=organization_id, as_of=pre_ingestion_snapshot)
        ).scalars().all()
    }
    report.as_of_leakage_check_passed = not (set(canonical_event_ids) & visible_before)
    if not report.as_of_leakage_check_passed:
        report.notes.append("LEAKAGE DETECTED: a just-ingested row was visible to a pre-ingestion as_of snapshot.")

    return report


# --- Item 5: provenance ------------------------------------------------------------------------


@dataclass
class ProvenanceValidationReport:
    checked_count: int = 0
    all_chains_intact: bool = False
    failures: list[str] = field(default_factory=list)
    feature_stage_reachable: bool | None = None  # canonical event -> FeatureSnapshot.source_event_ids
    predictive_stage_reachable: bool | None = None  # canonical event -> TrainingExample provenance
    notes: list[str] = field(default_factory=list)


def _validate_provenance(
    db: Session, *, organization_id: uuid.UUID, source_id: uuid.UUID | None, result: EnterpriseIngestionResult,
    as_of: datetime,
) -> ProvenanceValidationReport:
    report = ProvenanceValidationReport()
    batch = result.batch
    source = db.get(DataSource, source_id) if source_id else None

    site_id_for_feature_check: uuid.UUID | None = None
    canonical_event_ids: set[uuid.UUID] = set()

    # Content-hash equality is only a meaningful claim for whichever
    # record's own content is what is *currently* stored on the
    # canonical row -- i.e. the *last* CREATED/UPDATED/exact-replay
    # SKIPPED_IDEMPOTENT record processed for a given canonical event, not
    # every record that ever pointed at it. An earlier CREATED record
    # later superseded by an UPDATED correction legitimately has a
    # different content_hash from the row's current content -- that is
    # the correction working correctly, not a broken chain. A
    # SKIPPED_STALE_VERSION/REJECTED_VERSION_CONFLICT record's whole
    # point is that its content was deliberately *not* applied, so it is
    # never the "current content" record either.
    _content_bearing_outcomes = (
        IngestionOutcome.CREATED.value, IngestionOutcome.UPDATED.value, IngestionOutcome.SKIPPED_IDEMPOTENT.value,
    )
    current_content_record_id: dict[uuid.UUID, uuid.UUID] = {}
    for record in result.records:
        if record.canonical_event_id is not None and record.outcome in _content_bearing_outcomes:
            current_content_record_id[record.canonical_event_id] = record.id

    for record in result.records:
        if record.canonical_event_id is None:
            continue
        event = db.get(SafetyEvent, record.canonical_event_id)
        canonical_event_ids.add(record.canonical_event_id)
        if site_id_for_feature_check is None and event is not None and event.site_id is not None:
            site_id_for_feature_check = event.site_id

        content_hash_applicable = current_content_record_id.get(record.canonical_event_id) == record.id
        chain_ok = (
            event is not None
            and event.organization_id == organization_id
            and event.ingestion_batch_id == batch.id  # -> INGESTION BATCH
            and (source is None or event.ingestion_source_id == source.id)  # -> DATA SOURCE
            and event.source_record_id == record.external_record_id  # -> EXTERNAL RECORD
            and (not content_hash_applicable or event.source_content_hash == record.content_hash)
            and event.schema_version  # normalization status recorded
        )
        if not chain_ok:
            report.failures.append(str(record.id))
        report.checked_count += 1

    report.all_chains_intact = report.checked_count > 0 and not report.failures

    # -> FEATURE / INDICATOR: at least one canonical event from this
    # batch is reachable from a real feature snapshot's own provenance,
    # when the dataset carries a site to build one against. Genuinely
    # `None` (not False) when no record in the batch has a site_id --
    # there is nothing to check, not a failed check.
    if site_id_for_feature_check is not None:
        snapshot = get_or_build_feature_snapshot(
            db, organization_id=organization_id, site_id=site_id_for_feature_check, as_of=as_of, persist=False
        )
        snapshot_event_ids = {uuid.UUID(i) for i in snapshot.source_event_ids if i}
        report.feature_stage_reachable = bool(snapshot_event_ids & canonical_event_ids)
        if not report.feature_stage_reachable:
            report.notes.append(
                "No canonical event from this batch appeared in the feature snapshot's own "
                "source_event_ids -- expected if every site-scoped record falls outside the "
                "feature window, not necessarily a provenance break."
            )

        # -> PREDICTIVE DATASET: the training example built from that
        # same snapshot references it by id, and (only when the label is
        # a confirmed positive) its supporting events are real canonical
        # events too.
        example = build_training_example(
            db, organization_id=organization_id, site_id=site_id_for_feature_check, as_of=as_of, persist_snapshot=False
        )
        predictive_ok = example.feature_snapshot_id == snapshot.id or example.feature_set_version == snapshot.feature_set_version
        if example.label == 1:
            predictive_ok = predictive_ok and bool(example.supporting_event_ids)
        report.predictive_stage_reachable = predictive_ok

    return report


# --- Item 6: intelligence readiness -------------------------------------------------------------


@dataclass
class IntelligenceReadinessReport:
    data_sufficiency: str | None = None
    event_count: int = 0
    trend_readiness: dict[str, str] = field(default_factory=dict)  # metric -> direction, as computed, unaltered
    signals_detected: list[str] = field(default_factory=list)
    anomaly_status: str | None = None
    feature_availability: dict[str, bool] = field(default_factory=dict)  # feature name -> value is not None
    notes: list[str] = field(default_factory=list)


def _evaluate_intelligence_readiness(
    db: Session, *, organization_id: uuid.UUID, as_of: datetime, site_id: uuid.UUID | None = None
) -> IntelligenceReadinessReport:
    report = IntelligenceReadinessReport()
    summary = compute_summary(db, organization_id=organization_id, as_of=as_of, site_id=site_id, window_days=365)
    report.data_sufficiency = summary.data_sufficiency
    report.event_count = summary.event_count
    report.feature_availability = {name: fv.value is not None for name, fv in summary.features.items()}

    for metric in TREND_METRIC_REGISTRY:
        trend = compute_trend(db, organization_id=organization_id, metric=metric, as_of=as_of, site_id=site_id)
        report.trend_readiness[metric] = trend.direction

    signals = risk_signal_service.detect_all(db, organization_id=organization_id, as_of=as_of, site_id=site_id)
    report.signals_detected = sorted({s.signal_type for s in signals})

    baseline_buckets = bucketed_counts(
        db, organization_id=organization_id, site_id=site_id, period_end=as_of - timedelta(days=30),
        period_days=30, num_periods=4, event_type=QUALIFYING_EVENT_TYPE,
    )
    current_buckets = bucketed_counts(
        db, organization_id=organization_id, site_id=site_id, period_end=as_of, period_days=30, num_periods=1,
        event_type=QUALIFYING_EVENT_TYPE,
    )
    baseline_counts = [c for _, _, c in baseline_buckets]
    current_count = current_buckets[0][2] if current_buckets else 0
    anomaly = detect_anomaly(float(current_count), [float(c) for c in baseline_counts])
    report.anomaly_status = anomaly.status
    if anomaly.status == "INSUFFICIENT_DATA":
        report.notes.append(
            "Anomaly detection reports INSUFFICIENT_DATA -- fewer baseline periods than "
            "INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS requires. Reported as-is, not forced."
        )

    return report


# --- Item 7: predictive dataset readiness -------------------------------------------------------


@dataclass
class PredictiveReadinessReport:
    eligible_sites: int = 0
    excluded_sites: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    historical_time_coverage_days: dict[str, float] = field(default_factory=dict)  # site_id (str) -> days
    qualifying_incidents: int = 0
    positive_labels: int = 0
    negative_labels: int = 0
    unavailable_labels: int = 0  # horizon not yet elapsed -- see module docstring
    missing_features: int = 0  # feature_vector entries that are None, summed across eligible sites
    incomplete_feature_windows: int = 0  # sites whose data_quality is not SUFFICIENT_DATA
    class_distribution: dict[str, float] | None = None
    notes: list[str] = field(default_factory=list)


def _evaluate_predictive_readiness(
    db: Session, *, organization_id: uuid.UUID, site_ids: list[uuid.UUID], as_of: datetime,
    horizon_days: int | None = None,
) -> PredictiveReadinessReport:
    horizon_days = horizon_days if horizon_days is not None else HORIZON_DAYS
    report = PredictiveReadinessReport()
    reference_now = utcnow()
    horizon_closed = (as_of + timedelta(days=horizon_days)) <= reference_now

    for site_id in site_ids:
        earliest = db.execute(
            select(func.min(SafetyEvent.event_time)).where(
                SafetyEvent.organization_id == organization_id, SafetyEvent.site_id == site_id
            )
        ).scalar_one()
        if earliest is None:
            report.excluded_sites += 1
            report.exclusion_reasons["NO_HISTORICAL_DATA"] = report.exclusion_reasons.get("NO_HISTORICAL_DATA", 0) + 1
            continue

        try:
            example = build_training_example(
                db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days,
                persist_snapshot=False,
            )
        except Exception as exc:  # noqa: BLE001 -- one site's failure must never abort the readiness pass
            report.excluded_sites += 1
            reason = f"FEATURE_OR_LABEL_CONSTRUCTION_ERROR:{type(exc).__name__}"
            report.exclusion_reasons[reason] = report.exclusion_reasons.get(reason, 0) + 1
            continue

        report.eligible_sites += 1
        coverage_days = (as_of.replace(tzinfo=None) - earliest.replace(tzinfo=None)).total_seconds() / 86400
        report.historical_time_coverage_days[str(site_id)] = round(coverage_days, 1)

        qualifying = db.execute(
            select(func.count()).select_from(SafetyEvent).where(
                SafetyEvent.organization_id == organization_id, SafetyEvent.site_id == site_id,
                SafetyEvent.event_type == QUALIFYING_EVENT_TYPE, SafetyEvent.event_time <= as_of,
            )
        ).scalar_one()
        report.qualifying_incidents += qualifying

        if example.label == 1:
            report.positive_labels += 1
        elif horizon_closed:
            report.negative_labels += 1
        else:
            # The horizon window has not fully elapsed yet -- "no
            # qualifying event so far" is not evidence "none will occur,"
            # so this is UNAVAILABLE, never coerced into a negative.
            report.unavailable_labels += 1

        report.missing_features += sum(1 for v in example.feature_vector.values() if v is None)
        if example.data_quality != "SUFFICIENT_DATA":
            report.incomplete_feature_windows += 1

    labeled = report.positive_labels + report.negative_labels
    if labeled > 0:
        report.class_distribution = {
            "positive": round(report.positive_labels / labeled, 4),
            "negative": round(report.negative_labels / labeled, 4),
        }
    if report.unavailable_labels:
        report.notes.append(
            f"{report.unavailable_labels} site(s) have a label that cannot yet be confirmed "
            f"(the {horizon_days}-day prediction horizon has not fully elapsed as of real "
            "\"now\") -- reported as UNAVAILABLE, never coerced into a negative label."
        )
    return report


# --- Top-level entry point -----------------------------------------------------------------------


@dataclass
class ObservedSummary:
    """Item 10's own "OBSERVED — what the dataset actually contains,"
    computed directly from the raw payloads, before any validation
    decision is applied to them."""

    total_records: int = 0
    distinct_source_systems: list[str] = field(default_factory=list)
    distinct_event_type_terms: int = 0
    earliest_event_time: datetime | None = None
    latest_event_time: datetime | None = None


def _summarize_observed(payloads: list[RawSafetyEventPayload]) -> ObservedSummary:
    parsed_times = [t for t in (normalize_datetime(p.event_time) for p in payloads) if t is not None]
    return ObservedSummary(
        total_records=len(payloads),
        distinct_source_systems=sorted({p.source_system for p in payloads if p.source_system}),
        distinct_event_type_terms=len({p.event_type for p in payloads if p.event_type}),
        earliest_event_time=min(parsed_times) if parsed_times else None,
        latest_event_time=max(parsed_times) if parsed_times else None,
    )


@dataclass
class EnterpriseDatasetValidationReport:
    label: str
    organization_id: uuid.UUID
    batch_id: uuid.UUID
    generated_at: datetime
    observed: ObservedSummary
    ingestion: IngestionSummary
    data_quality: DataQualitySummary
    terminology_entries: list[TerminologyReviewEntry]
    terminology_summary: TerminologyReviewSummary
    temporal: TemporalIntegrityReport
    provenance: ProvenanceValidationReport
    intelligence_readiness: IntelligenceReadinessReport
    predictive_readiness: PredictiveReadinessReport


def run_enterprise_dataset_validation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    payloads: list[RawSafetyEventPayload],
    label: str,
    source_id: uuid.UUID | None = None,
    site_ids: list[uuid.UUID] | None = None,
    as_of: datetime | None = None,
    use_terminology_mapping: bool = True,
) -> EnterpriseDatasetValidationReport:
    """The full harness. `label` is mandatory and caller-supplied
    (never defaulted to something that could be mistaken for a real-data
    claim) — pass `SYNTHETIC_VALIDATION_LABEL` for a synthetic fixture, or
    an equally explicit real-dataset label (e.g. "Real, anonymized "
    "dataset supplied by <engagement>, evaluated <date>") once one is
    actually provided. `use_terminology_mapping=True` (default) ingests
    through `TerminologyMappingAdapter` so ambiguous/unknown terminology
    is quarantined during real ingestion, not merely flagged by a
    side analysis -- pass `False` to evaluate a dataset exactly as the
    default, unmapped pipeline would see it.
    """
    reference_now = utcnow()
    adapter = TerminologyMappingAdapter() if use_terminology_mapping else None

    result = enterprise_ingestion_service.ingest_batch(
        db, organization_id=organization_id, source_id=source_id, payloads=payloads, adapter=adapter
    )

    # `analysis_as_of`, captured *after* ingestion completes, is what
    # every post-ingestion check below uses by default -- never
    # `reference_now` (captured before ingestion) and never an explicit
    # caller `as_of` unless the caller genuinely means it. Every
    # temporal/intelligence/predictive check below ultimately goes
    # through events_as_of()'s `ingestion_time <= as_of` guarantee
    # (app/intelligence/temporal.py, UNCHANGED); since
    # SafetyEventIngestionService stamps `ingestion_time` at real
    # wall-clock "now" *during* `ingest_batch()` above, any `as_of`
    # captured or supplied *before* that call would make every
    # just-ingested row invisible to every check below, by design, not
    # by bug -- exactly the lesson documented in
    # tests/evaluation/intelligence_harness.py and
    # tests/evaluation/calibration_harness.py. Passing an explicit,
    # genuinely earlier `as_of` is still supported (it is a legitimate
    # retrospective/point-in-time query, see `TemporalIntegrityReport`'s
    # own retrospective-vs-point-in-time note) -- callers doing that
    # should expect reduced or zero visibility as the correct, intended
    # result, not a bug in this harness.
    analysis_as_of = as_of if as_of is not None else utcnow()

    ingestion, quality = _summarize_ingestion(result, reference_now=reference_now)
    quality.future_timestamps = _count_future_timestamps(payloads, reference_now=reference_now)

    terminology_entries = build_terminology_review(payloads)
    terminology_summary = TerminologyReviewSummary.from_entries(terminology_entries)

    temporal = _validate_temporal_integrity(
        db, organization_id=organization_id, payloads=payloads, result=result, reference_now=reference_now
    )
    provenance = _validate_provenance(
        db, organization_id=organization_id, source_id=source_id, result=result, as_of=analysis_as_of
    )

    intelligence_readiness = _evaluate_intelligence_readiness(db, organization_id=organization_id, as_of=analysis_as_of)

    resolved_site_ids = site_ids if site_ids is not None else _distinct_site_ids(db, organization_id, result)
    predictive_readiness = _evaluate_predictive_readiness(
        db, organization_id=organization_id, site_ids=resolved_site_ids, as_of=analysis_as_of
    )

    return EnterpriseDatasetValidationReport(
        label=label,
        organization_id=organization_id,
        batch_id=result.batch.id,
        generated_at=datetime.now(timezone.utc),
        observed=_summarize_observed(payloads),
        ingestion=ingestion,
        data_quality=quality,
        terminology_entries=terminology_entries,
        terminology_summary=terminology_summary,
        temporal=temporal,
        provenance=provenance,
        intelligence_readiness=intelligence_readiness,
        predictive_readiness=predictive_readiness,
    )


def _distinct_site_ids(db: Session, organization_id: uuid.UUID, result: EnterpriseIngestionResult) -> list[uuid.UUID]:
    event_ids = [r.canonical_event_id for r in result.records if r.canonical_event_id is not None]
    if not event_ids:
        return []
    rows = db.execute(
        select(SafetyEvent.site_id).where(
            SafetyEvent.organization_id == organization_id, SafetyEvent.id.in_(event_ids), SafetyEvent.site_id.is_not(None)
        ).distinct()
    ).scalars().all()
    return list(rows)


# --- Item 8: queuing this harness's own findings for HSE expert review ------------------------


def queue_review_candidates(
    db: Session,
    *,
    organization_id: uuid.UUID,
    report: EnterpriseDatasetValidationReport,
    max_representative_signals: int = 5,
) -> list:
    """Queues (via `app.services.hse_review_service.queue_for_review()`,
    the one write path — never inserted directly) exactly the five kinds
    of finding item 8 names: every terminology entry this harness itself
    flagged `requires_review`, every quarantined canonical record from
    this batch, a representative sample of risk signals/intelligence
    output, and (implicitly, via `TERMINOLOGY_MAPPING`/`QUARANTINED_RECORD`)
    the unexpected classifications those two already cover. An
    **evaluation mechanism only** — this function only ever creates
    pending (`outcome=None`) rows; nothing reads them back and changes
    ingestion, mapping, or intelligence behavior (see
    `app/models/hse_expert_review.py`'s own docstring)."""
    queued = []

    for entry in report.terminology_entries:
        if not entry.requires_review:
            continue
        target_reference = f"{entry.domain}:{entry.context or ''}:{entry.source_term}"
        queued.append(
            queue_for_review(
                db, organization_id=organization_id, target_type="TERMINOLOGY_MAPPING", target_reference=target_reference,
                provenance={
                    "domain": entry.domain, "context": entry.context, "source_term": entry.source_term,
                    "proposed_canonical_term": entry.proposed_canonical_term, "status": entry.status,
                    "reason": entry.reason, "occurrence_count": entry.occurrence_count,
                    "example_source_record_ids": list(entry.example_source_record_ids),
                    "batch_id": str(report.batch_id),
                },
            )
        )

    quarantined_records = db.execute(
        select(EnterpriseIngestionRecord).where(
            EnterpriseIngestionRecord.batch_id == report.batch_id, EnterpriseIngestionRecord.quality_state == "QUARANTINED",
        )
    ).scalars().all()
    for record in quarantined_records:
        queued.append(
            queue_for_review(
                db, organization_id=organization_id, target_type="QUARANTINED_RECORD",
                target_reference=str(record.canonical_event_id or record.id),
                provenance={
                    "external_record_id": record.external_record_id, "batch_id": str(report.batch_id),
                    "issues": record.rejection_reason, "canonical_event_id": str(record.canonical_event_id)
                    if record.canonical_event_id else None,
                },
            )
        )

    signals = risk_signal_service.detect_all(db, organization_id=organization_id, as_of=utcnow())
    for signal in signals[:max_representative_signals]:
        queued.append(
            queue_for_review(
                db, organization_id=organization_id, target_type="RISK_INDICATOR",
                target_reference=f"{signal.signal_type}:{report.batch_id}",
                provenance={
                    "signal_type": signal.signal_type, "organization_id": str(organization_id),
                    "batch_id": str(report.batch_id),
                },
            )
        )

    return queued
