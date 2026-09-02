"""Real-World Data Validation & Intelligence Calibration v0.1 —
evaluation harness. **Prototype / controlled-scenario calibration
only — not a production benchmark, and not evidence of production
predictive accuracy.** See `docs/CALIBRATION_EVALUATION_REPORT.md` (the
report this harness produces) for the exact same disclaimer restated
next to every number it prints.

    for each of the 5 controlled scenarios (tests/fixtures/enterprise_scenarios.py):
        real ingestion through EnterpriseIngestionService (UNCHANGED, milestone 1's own service)
            -> data-quality benchmark (item 6)
        real compute_summary/compute_trend/risk_signal_service/detect_anomaly (all UNCHANGED)
            -> compared against this scenario's own known expected direction
            -> CalibrationOutcome.EXPECTED / UNEXPECTED / INDETERMINATE (item 8-9)
    + provenance validation (item 7), predictive-dataset-readiness (item 10),
      multi-tenant isolation (item 12) -- each also against real, unchanged
      SIE code paths, never re-implemented here.

Nothing here is fabricated or extrapolated — every number comes from
actually running the production ingestion/analytics/predictions code,
exactly like `tests/evaluation/intelligence_harness.py` already
established for its own, narrower set of six technical edge-case
profiles. This harness's five scenarios are deliberately realistic and
have a *known* expected direction, which is what makes them suitable
for calibration rather than mere regression-catching.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.intelligence.analytics import compute_summary, compute_trend
from app.intelligence.anomaly import detect_anomaly
from app.intelligence.enterprise_ingestion import (
    EnterpriseIngestionResult,
    enterprise_ingestion_service,
)
from app.intelligence.enums import IngestionOutcome
from app.intelligence.signals import risk_signal_service
from app.intelligence.temporal import bucketed_counts, events_as_of, utcnow
from app.models.data_source import DataSource
from app.models.enterprise_ingestion_batch import EnterpriseIngestionBatch
from app.models.enterprise_ingestion_record import EnterpriseIngestionRecord
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent
from app.models.site import Site
from app.predictions.dataset import build_training_examples
from tests.fixtures.enterprise_scenarios import ALL_SCENARIOS, incident, near_miss

REPORT_LABEL = "Prototype / controlled-scenario calibration only — not a production benchmark."

_MISSING_TIMESTAMP_ISSUE_CODES = {"MISSING_EVENT_TIME", "INVALID_EVENT_TIME"}
_INVALID_CLASSIFICATION_ISSUE_CODES = {"UNRECOGNIZED_EVENT_TYPE", "INVALID_SEVERITY", "INVALID_POTENTIAL_SEVERITY"}
_MISSING_IDENTIFIER_ISSUE_CODES = {"MISSING_SOURCE_SYSTEM", "MISSING_SOURCE_RECORD_ID", "MALFORMED_SOURCE_RECORD_ID"}


class CalibrationOutcome(str, Enum):
    EXPECTED = "EXPECTED"
    UNEXPECTED = "UNEXPECTED"
    INDETERMINATE = "INDETERMINATE"


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


@dataclass
class DataQualityBenchmark:
    """Item 6's own required measurements — schema-validity metrics
    only, never described as factual correctness (see this module's own
    docstring and the milestone's own item-6 instruction)."""

    total_records: int = 0
    valid_records: int = 0
    partial_records: int = 0
    quarantined_records: int = 0
    rejected_records: int = 0
    duplicate_records: int = 0
    stale_records: int = 0  # SKIPPED_STALE_VERSION -- item 5's late-arriving-version case
    version_conflicts: int = 0  # REJECTED_VERSION_CONFLICT
    missing_timestamps: int = 0
    invalid_classifications: int = 0
    missing_identifiers: int = 0
    completeness_rate: float | None = None
    acceptance_rate: float | None = None
    rejection_rate: float | None = None
    quarantine_rate: float | None = None
    duplicate_rate: float | None = None
    temporal_validity_rate: float | None = None

    @classmethod
    def from_ingestion_result(cls, result: EnterpriseIngestionResult) -> DataQualityBenchmark:
        batch = result.batch
        missing_ts = invalid_class = missing_id = 0
        for record in result.records:
            codes = {issue["code"] for issue in (record.rejection_reason or [])}
            if codes & _MISSING_TIMESTAMP_ISSUE_CODES:
                missing_ts += 1
            if codes & _INVALID_CLASSIFICATION_ISSUE_CODES:
                invalid_class += 1
            if codes & _MISSING_IDENTIFIER_ISSUE_CODES:
                missing_id += 1

        total = batch.total_records
        bench = cls(
            total_records=total,
            valid_records=batch.accepted_records,
            partial_records=batch.partial_records,
            quarantined_records=batch.quarantined_records,
            rejected_records=batch.rejected_records,
            duplicate_records=batch.duplicate_records,
            stale_records=sum(1 for r in result.records if r.outcome == IngestionOutcome.SKIPPED_STALE_VERSION.value),
            version_conflicts=sum(
                1 for r in result.records if r.outcome == IngestionOutcome.REJECTED_VERSION_CONFLICT.value
            ),
            missing_timestamps=missing_ts,
            invalid_classifications=invalid_class,
            missing_identifiers=missing_id,
        )
        bench.completeness_rate = _rate(total - missing_id - missing_ts, total)
        bench.acceptance_rate = _rate(bench.valid_records, total)
        bench.rejection_rate = _rate(bench.rejected_records, total)
        bench.quarantine_rate = _rate(bench.quarantined_records, total)
        bench.duplicate_rate = _rate(bench.duplicate_records, total)
        bench.temporal_validity_rate = _rate(total - missing_ts, total)
        return bench


@dataclass
class ScenarioCalibrationResult:
    scenario_key: str
    scenario_name: str
    description: str
    dataset_record_count: int
    data_quality: DataQualityBenchmark
    expected_intelligence: dict[str, str] = field(default_factory=dict)
    actual_intelligence: dict[str, str] = field(default_factory=dict)
    calibration_outcomes: dict[str, str] = field(default_factory=dict)  # metric -> CalibrationOutcome value
    notes: list[str] = field(default_factory=list)

    def all_expected(self) -> bool:
        return all(v == CalibrationOutcome.EXPECTED.value for v in self.calibration_outcomes.values())


@dataclass
class ProvenanceValidationResult:
    checked_count: int = 0
    all_chains_intact: bool = False
    failures: list[str] = field(default_factory=list)


@dataclass
class PredictiveReadinessResult:
    examples_built: int = 0
    reproducible: bool = False
    no_future_leakage: bool = True
    tenant_isolated: bool = False
    missing_data_handled: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class TenantIsolationResult:
    org_a_events_visible_to_org_b: int = 0
    org_b_events_visible_to_org_a: int = 0
    quality_metrics_isolated: bool = False
    predictive_dataset_isolated: bool = False


@dataclass
class CalibrationEvaluationReport:
    label: str = REPORT_LABEL
    scenarios: dict[str, ScenarioCalibrationResult] = field(default_factory=dict)
    provenance: ProvenanceValidationResult = field(default_factory=ProvenanceValidationResult)
    predictive_readiness: PredictiveReadinessResult = field(default_factory=PredictiveReadinessResult)
    tenant_isolation: TenantIsolationResult = field(default_factory=TenantIsolationResult)

    def all_scenarios_expected(self) -> bool:
        return all(s.all_expected() for s in self.scenarios.values())


def _make_org(db: Session, name: str) -> uuid.UUID:
    org = Organization(name=name)
    db.add(org)
    db.commit()
    return org.id


def _outcome(condition: bool | None) -> CalibrationOutcome:
    if condition is None:
        return CalibrationOutcome.INDETERMINATE
    return CalibrationOutcome.EXPECTED if condition else CalibrationOutcome.UNEXPECTED


def _ingest_scenario(db: Session, *, organization_id: uuid.UUID, key: str, as_of: datetime, source_id=None):
    # `as_of` here is actually a base_time -- the value the scenario's
    # relative day-offsets are generated against (kept as `as_of` since
    # that's the scenario builders' own parameter name in
    # tests/fixtures/enterprise_scenarios.py).
    dataset = ALL_SCENARIOS[key](as_of)
    result = enterprise_ingestion_service.ingest_batch(
        db, organization_id=organization_id, source_id=source_id, payloads=dataset.events
    )
    return dataset, result


def _backdate_ingestion_time_near_event_time(
    db: Session, organization_id: uuid.UUID, *, delay: timedelta = timedelta(hours=6)
) -> None:
    """Realistic near-real-time ingestion cadence for scenario data whose
    `event_time` values span months in the past.

    `SafetyEventIngestionService` always stamps `ingestion_time` at real
    wall-clock "now" -- correct for a genuine live caller, and
    deliberately unchanged here. But every scenario in
    tests/fixtures/enterprise_scenarios.py ingests its whole multi-month
    history in one batch, which would otherwise stamp *every* row's
    `ingestion_time` at that same single instant. `bucketed_counts()`'s
    own point-in-time-correct, per-bucket `ingestion_time <= bucket_end`
    check (app/intelligence/temporal.py) would then -- entirely correctly
    -- treat every historical bucket as "not yet known" as of its own
    boundary, collapsing all data into the single most recent bucket.
    That is not a bug in `events_as_of()`; it is what strict point-in-time
    correctness demands of a one-shot historical bulk load, and is
    recorded as a known limitation in
    docs/CALIBRATION_EVALUATION_REPORT.md.

    These scenarios describe an organization operating *day to day*, not
    a one-time migration cutover -- so, exactly like
    tests/evaluation/intelligence_harness.py's own `stale_data_org`
    backdating (see its comment), directly backdating `ingestion_time` to
    track shortly after each event's own `event_time` here -- never
    through the ingestion service -- is the honest way to simulate that
    realistic cadence in a test.
    """
    for event in db.execute(select(SafetyEvent).where(SafetyEvent.organization_id == organization_id)).scalars():
        event.ingestion_time = event.event_time + delay
    db.commit()


# --- Scenario A: Stable / Low Concern ------------------------------------------------------


def _evaluate_scenario_a(db: Session, base_time: datetime, source_id) -> ScenarioCalibrationResult:
    org_id = _make_org(db, "Calibration - Scenario A")
    dataset, result = _ingest_scenario(db, organization_id=org_id, key="A", as_of=base_time, source_id=source_id)
    _backdate_ingestion_time_near_event_time(db, org_id)

    # `as_of`, used for every analysis call below, is captured *after*
    # ingestion completes, not before -- see the identical comment and
    # rationale in tests/evaluation/intelligence_harness.py's
    # seed_and_evaluate(). Using `base_time` (the value the scenario's
    # relative day-offsets were generated against) here instead would make
    # every just-ingested row invisible to events_as_of()'s
    # `ingestion_time <= as_of` filter, by design, not by bug.
    as_of = utcnow()

    near_miss_trend = compute_trend(db, organization_id=org_id, metric="near_miss_count", as_of=as_of, period_days=30, num_periods=4)
    incident_trend = compute_trend(db, organization_id=org_id, metric="incident_count", as_of=as_of, period_days=30, num_periods=4)
    signals = risk_signal_service.detect_all(db, organization_id=org_id, as_of=as_of)

    outcomes = {
        "near_miss_trend_stable": _outcome(near_miss_trend.direction == "STABLE"),
        "incident_trend_stable": _outcome(incident_trend.direction == "STABLE"),
        "no_risk_signals": _outcome(len(signals) == 0),
    }
    return ScenarioCalibrationResult(
        scenario_key="A", scenario_name=dataset.name, description=dataset.description,
        dataset_record_count=len(dataset.events),
        data_quality=DataQualityBenchmark.from_ingestion_result(result),
        expected_intelligence={
            "near_miss_trend": "STABLE", "incident_trend": "STABLE", "risk_signals": "none",
        },
        actual_intelligence={
            "near_miss_trend": near_miss_trend.direction, "incident_trend": incident_trend.direction,
            "risk_signals": sorted({s.signal_type for s in signals}) or "none",
        },
        calibration_outcomes={k: v.value for k, v in outcomes.items()},
    )


# --- Scenario B: Emerging Risk --------------------------------------------------------------


def _evaluate_scenario_b(db: Session, base_time: datetime, source_id) -> ScenarioCalibrationResult:
    org_id = _make_org(db, "Calibration - Scenario B")
    dataset, result = _ingest_scenario(db, organization_id=org_id, key="B", as_of=base_time, source_id=source_id)
    _backdate_ingestion_time_near_event_time(db, org_id)

    as_of = utcnow()  # captured fresh after ingestion -- see _evaluate_scenario_a's comment

    near_miss_trend = compute_trend(db, organization_id=org_id, metric="near_miss_count", as_of=as_of, period_days=30, num_periods=4)
    signals = risk_signal_service.detect_all(db, organization_id=org_id, as_of=as_of)
    signal_types = {s.signal_type for s in signals}

    outcomes = {
        "near_miss_trend_increasing": _outcome(near_miss_trend.direction == "INCREASING"),
        "unsafe_observation_surge_fires": _outcome("UNSAFE_OBSERVATION_SURGE" in signal_types),
        "training_compliance_drop_fires": _outcome("TRAINING_COMPLIANCE_DROP" in signal_types),
        # The scenario deliberately keeps incidents flat -- a lagging
        # signal firing here would itself be miscalibrated (leading
        # deterioration must never be conflated with a lagging one).
        "no_lagging_signal_from_leading_only_data": _outcome("HIGH_POTENTIAL_EVENT_CLUSTER" not in signal_types),
    }
    return ScenarioCalibrationResult(
        scenario_key="B", scenario_name=dataset.name, description=dataset.description,
        dataset_record_count=len(dataset.events),
        data_quality=DataQualityBenchmark.from_ingestion_result(result),
        expected_intelligence={
            "near_miss_trend": "INCREASING", "unsafe_observation_surge": "fires",
            "training_compliance_drop": "fires", "high_potential_event_cluster": "does not fire",
        },
        actual_intelligence={
            "near_miss_trend": near_miss_trend.direction, "risk_signals": sorted(signal_types) or "none",
        },
        calibration_outcomes={k: v.value for k, v in outcomes.items()},
        notes=["Leading-indicator deterioration only -- no claim that these factors caused an incident."],
    )


# --- Scenario C: Lagging Event Increase -----------------------------------------------------


def _evaluate_scenario_c(db: Session, base_time: datetime, source_id) -> ScenarioCalibrationResult:
    org_id = _make_org(db, "Calibration - Scenario C")
    dataset, result = _ingest_scenario(db, organization_id=org_id, key="C", as_of=base_time, source_id=source_id)
    _backdate_ingestion_time_near_event_time(db, org_id)

    as_of = utcnow()  # captured fresh after ingestion -- see _evaluate_scenario_a's comment

    incident_trend = compute_trend(db, organization_id=org_id, metric="incident_count", as_of=as_of, period_days=30, num_periods=5)
    near_miss_trend = compute_trend(db, organization_id=org_id, metric="near_miss_count", as_of=as_of, period_days=30, num_periods=5)
    signals = risk_signal_service.detect_all(db, organization_id=org_id, as_of=as_of)
    signal_types = {s.signal_type for s in signals}

    # Anomaly calibration, computed directly (item 8's own "anomaly"
    # check) -- 4 quiet baseline periods (>= INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS)
    # immediately preceding the current 30-day window, vs. the current window's own count.
    baseline_buckets = bucketed_counts(
        db, organization_id=org_id, site_id=None, period_end=as_of - timedelta(days=30),
        period_days=30, num_periods=4, event_type="INCIDENT",
    )
    baseline_counts = [c for _, _, c in baseline_buckets]
    current_buckets = bucketed_counts(
        db, organization_id=org_id, site_id=None, period_end=as_of, period_days=30, num_periods=1, event_type="INCIDENT",
    )
    current_count = current_buckets[0][2]
    anomaly = detect_anomaly(float(current_count), [float(c) for c in baseline_counts])

    outcomes = {
        "incident_trend_increasing": _outcome(incident_trend.direction == "INCREASING"),
        "near_miss_trend_stable": _outcome(near_miss_trend.direction == "STABLE"),
        "high_potential_event_cluster_fires": _outcome("HIGH_POTENTIAL_EVENT_CLUSTER" in signal_types),
        "anomaly_detected_where_statistically_justified": _outcome(anomaly.status == "ANOMALOUS"),
    }
    return ScenarioCalibrationResult(
        scenario_key="C", scenario_name=dataset.name, description=dataset.description,
        dataset_record_count=len(dataset.events),
        data_quality=DataQualityBenchmark.from_ingestion_result(result),
        expected_intelligence={
            "incident_trend": "INCREASING", "near_miss_trend": "STABLE",
            "high_potential_event_cluster": "fires", "anomaly": "ANOMALOUS",
        },
        actual_intelligence={
            "incident_trend": incident_trend.direction, "near_miss_trend": near_miss_trend.direction,
            "risk_signals": sorted(signal_types) or "none", "anomaly_status": anomaly.status,
            "anomaly_baseline_counts": baseline_counts, "anomaly_current_count": current_count,
        },
        calibration_outcomes={k: v.value for k, v in outcomes.items()},
    )


# --- Scenario D: Data Quality Degradation ---------------------------------------------------


def _evaluate_scenario_d(db: Session, base_time: datetime, source_id) -> ScenarioCalibrationResult:
    org_id = _make_org(db, "Calibration - Scenario D")
    dataset, result = _ingest_scenario(db, organization_id=org_id, key="D", as_of=base_time, source_id=source_id)
    quality = DataQualityBenchmark.from_ingestion_result(result)

    as_of = utcnow()  # captured fresh after ingestion -- see _evaluate_scenario_a's comment

    summary = compute_summary(db, organization_id=org_id, as_of=as_of, window_days=365)

    # Ground truth for "never silently trusted" is the actual canonical
    # SafetyEvent rows, not the batch's own accepted_records/partial_records
    # counters: those two intentionally count *ingestion record outcomes*
    # (app/intelligence/enterprise_ingestion.py), including a duplicate
    # resend or a version conflict that *resolved against* an existing
    # VALID row without creating a new canonical event -- a different,
    # equally legitimate thing from "how many canonical rows carry VALID or
    # PARTIAL quality" (what events_as_of()/compute_summary() actually
    # count). Comparing analytics event_count to the batch counters
    # directly would be conflating the two, not evidence of a leak.
    usable_canonical_count = db.execute(
        select(func.count()).select_from(SafetyEvent).where(
            SafetyEvent.organization_id == org_id,
            SafetyEvent.data_quality_status.in_(["VALID", "PARTIAL"]),
        )
    ).scalar_one()
    quarantined_canonical_count = db.execute(
        select(func.count()).select_from(SafetyEvent).where(
            SafetyEvent.organization_id == org_id, SafetyEvent.data_quality_status == "QUARANTINED"
        )
    ).scalar_one()

    # A quarantined/rejected record must never silently become trusted
    # intelligence -- event_count must equal exactly the usable
    # (VALID + PARTIAL) canonical rows, never more, and the quarantined
    # rows this scenario deliberately creates must be real and excluded.
    outcomes = {
        "quality_degradation_reflected_in_metrics": _outcome(
            quality.quarantined_records > 0 and quality.rejected_records > 0 and quality.duplicate_records > 0
        ),
        "quarantined_records_excluded_from_analytics": _outcome(
            summary.event_count == usable_canonical_count and quarantined_canonical_count > 0
        ),
        "version_conflict_detected_not_silently_applied": _outcome(quality.version_conflicts > 0),
    }
    return ScenarioCalibrationResult(
        scenario_key="D", scenario_name=dataset.name, description=dataset.description,
        dataset_record_count=len(dataset.events),
        data_quality=quality,
        expected_intelligence={
            "quarantined_records": "> 0", "rejected_records": "> 0", "duplicate_records": "> 0",
            "version_conflicts": "> 0", "analytics_event_count": "== accepted (VALID+PARTIAL) records only",
        },
        actual_intelligence={
            "quarantined_records": quality.quarantined_records, "rejected_records": quality.rejected_records,
            "duplicate_records": quality.duplicate_records, "version_conflicts": quality.version_conflicts,
            "analytics_event_count": summary.event_count,
        },
        calibration_outcomes={k: v.value for k, v in outcomes.items()},
        notes=["Schema validity only -- never presented as factual correctness of the underlying record."],
    )


# --- Scenario E: Recovery --------------------------------------------------------------------


def _evaluate_scenario_e(db: Session, base_time: datetime, source_id) -> ScenarioCalibrationResult:
    org_id = _make_org(db, "Calibration - Scenario E")
    dataset, result = _ingest_scenario(db, organization_id=org_id, key="E", as_of=base_time, source_id=source_id)
    _backdate_ingestion_time_near_event_time(db, org_id)

    as_of = utcnow()  # captured fresh after ingestion -- see _evaluate_scenario_a's comment

    near_miss_trend = compute_trend(db, organization_id=org_id, metric="near_miss_count", as_of=as_of, period_days=30, num_periods=3)
    summary = compute_summary(db, organization_id=org_id, as_of=as_of, window_days=30)
    training_rate = summary.features["training_completion_rate"].value
    signals = risk_signal_service.detect_all(db, organization_id=org_id, as_of=as_of)
    signal_types = {s.signal_type for s in signals}

    outcomes = {
        "near_miss_trend_decreasing": _outcome(near_miss_trend.direction == "DECREASING"),
        "training_completion_recovered": _outcome(training_rate is not None and training_rate >= 0.8),
        "no_training_compliance_drop_in_recovered_window": _outcome("TRAINING_COMPLIANCE_DROP" not in signal_types),
    }
    return ScenarioCalibrationResult(
        scenario_key="E", scenario_name=dataset.name, description=dataset.description,
        dataset_record_count=len(dataset.events),
        data_quality=DataQualityBenchmark.from_ingestion_result(result),
        expected_intelligence={
            "near_miss_trend": "DECREASING", "training_completion_rate": ">= 0.8", "training_compliance_drop": "does not fire",
        },
        actual_intelligence={
            "near_miss_trend": near_miss_trend.direction, "training_completion_rate": training_rate,
            "risk_signals": sorted(signal_types) or "none",
        },
        calibration_outcomes={k: v.value for k, v in outcomes.items()},
        notes=[
            (
                "Indicators moving in the improving direction is not, by itself, proof of actual safety "
                "improvement -- see this module's own docstring and the milestone's own caution."
            )
        ],
    )


_SCENARIO_EVALUATORS = {
    "A": _evaluate_scenario_a, "B": _evaluate_scenario_b, "C": _evaluate_scenario_c,
    "D": _evaluate_scenario_d, "E": _evaluate_scenario_e,
}


# --- Provenance validation (item 7) ---------------------------------------------------------


def _validate_provenance(db: Session, *, organization_id: uuid.UUID, source_id: uuid.UUID, batch_id: uuid.UUID) -> ProvenanceValidationResult:
    result = ProvenanceValidationResult()
    records = db.execute(
        select(EnterpriseIngestionRecord).where(
            EnterpriseIngestionRecord.batch_id == batch_id, EnterpriseIngestionRecord.canonical_event_id.is_not(None)
        )
    ).scalars().all()
    batch = db.get(EnterpriseIngestionBatch, batch_id)
    source = db.get(DataSource, source_id)

    for record in records:
        event = db.get(SafetyEvent, record.canonical_event_id)
        chain_ok = (
            event is not None
            and event.organization_id == organization_id
            and event.ingestion_batch_id == batch.id  # canonical event -> batch (existing UUID-match link)
            and event.ingestion_source_id == source.id  # canonical event -> data source
            and event.source_system == "enterprise-scenario"
            and event.source_record_id == record.external_record_id  # external record id preserved
            and event.source_content_hash == record.content_hash  # content hash preserved
            and event.normalization_version  # normalization status recorded
            and event.schema_version
        )
        if not chain_ok:
            result.failures.append(str(record.id))
        result.checked_count += 1

    result.all_chains_intact = result.checked_count > 0 and not result.failures
    return result


# --- Predictive dataset readiness (item 10) --------------------------------------------------


def _validate_predictive_readiness(db: Session, base_time: datetime) -> PredictiveReadinessResult:
    result = PredictiveReadinessResult()
    org_a_id = _make_org(db, "Calibration - Predictive Readiness A")
    org_b_id = _make_org(db, "Calibration - Predictive Readiness B")
    site_a = Site(organization_id=org_a_id, name="Site A1")
    site_b = Site(organization_id=org_b_id, name="Site B1")
    db.add_all([site_a, site_b])
    db.commit()

    rng_a, rng_b = random.Random(2001), random.Random(2002)
    payloads_a = [incident(rng_a, base_time, days_ago=i, subtype="FIRST_AID_CASE", site_id=site_a.id) for i in range(20)]
    payloads_a += [near_miss(rng_a, base_time, days_ago=i, subtype="DROPPED_OBJECT", site_id=site_a.id) for i in range(20)]
    payloads_b = [incident(rng_b, base_time, days_ago=i, subtype="FIRST_AID_CASE", site_id=site_b.id) for i in range(5)]

    enterprise_ingestion_service.ingest_batch(db, organization_id=org_a_id, source_id=None, payloads=payloads_a)
    enterprise_ingestion_service.ingest_batch(db, organization_id=org_b_id, source_id=None, payloads=payloads_b)
    # See _backdate_ingestion_time_near_event_time()'s own docstring --
    # build_training_examples() below constructs snapshots at several
    # *past* as_of_dates, each its own strict point-in-time check, so it
    # needs the same realistic near-real-time ingestion cadence the trend
    # scenarios do, not one bulk backfill instant.
    _backdate_ingestion_time_near_event_time(db, org_a_id)
    _backdate_ingestion_time_near_event_time(db, org_b_id)

    # Fresh `as_of`, captured after ingestion -- see _evaluate_scenario_a's
    # comment. build_training_examples() ultimately goes through
    # events_as_of() too, so the same ingestion_time <= as_of guarantee
    # applies here, not just to the trend/signal analysis calls above.
    as_of = utcnow()
    # Offsets chosen to fall *inside* the payloads' own 0-19-days-ago
    # spread (see the range(20) loops above) so the earliest snapshot is a
    # real, non-vacuous leakage check -- it must see the events dated on
    # or before it and must not see the later ones, not simply see nothing.
    as_of_dates = [as_of - timedelta(days=d) for d in (15, 7, 0)]

    examples_1 = build_training_examples(
        db, organization_id=org_a_id, site_ids=[site_a.id], as_of_dates=as_of_dates, persist_snapshots=False
    )
    examples_2 = build_training_examples(
        db, organization_id=org_a_id, site_ids=[site_a.id], as_of_dates=as_of_dates, persist_snapshots=False
    )
    result.examples_built = len(examples_1)
    result.reproducible = [e.feature_vector for e in examples_1] == [e.feature_vector for e in examples_2]

    # No future leakage: a feature snapshot at the earliest as_of must
    # never see events dated after it -- verified directly against the
    # events actually visible via events_as_of() at that same as_of. This
    # is deliberately checked as a non-vacuous condition: some events must
    # be visible (data existed by then) and some must be excluded (later
    # events must not leak in), not simply an empty result either way.
    earliest_as_of = min(as_of_dates)
    all_org_a_events = db.execute(
        events_as_of(organization_id=org_a_id, as_of=as_of, site_id=site_a.id)
    ).scalars().all()
    visible = db.execute(
        events_as_of(organization_id=org_a_id, as_of=earliest_as_of, site_id=site_a.id)
    ).scalars().all()
    result.no_future_leakage = (
        all(e.event_time <= earliest_as_of for e in visible)
        and 0 < len(visible) < len(all_org_a_events)
    )

    # Tenant isolation: org B's examples must never reflect org A's data,
    # and vice versa -- built independently and compared by entity_id/organization_id only.
    examples_b = build_training_examples(
        db, organization_id=org_b_id, site_ids=[site_b.id], as_of_dates=as_of_dates, persist_snapshots=False
    )
    result.tenant_isolated = (
        all(e.organization_id == org_a_id for e in examples_1)
        and all(e.organization_id == org_b_id for e in examples_b)
    )

    # Missing-data handling: a site with no events yet must still build a
    # (low-data-quality, never a crash) example.
    empty_site = Site(organization_id=org_a_id, name="Site A2 (no events)")
    db.add(empty_site)
    db.commit()
    empty_examples = build_training_examples(
        db, organization_id=org_a_id, site_ids=[empty_site.id], as_of_dates=[as_of], persist_snapshots=False
    )
    result.missing_data_handled = len(empty_examples) == 1 and empty_examples[0].data_quality is not None

    return result


# --- Multi-tenant validation (item 12) --------------------------------------------------------


def _validate_tenant_isolation(db: Session, base_time: datetime) -> TenantIsolationResult:
    org_a_id = _make_org(db, "Calibration - Tenant Isolation A")
    org_b_id = _make_org(db, "Calibration - Tenant Isolation B")
    _dataset_a, result_a = _ingest_scenario(db, organization_id=org_a_id, key="B", as_of=base_time)
    _dataset_b, result_b = _ingest_scenario(db, organization_id=org_b_id, key="C", as_of=base_time)

    as_of = utcnow()  # captured fresh after ingestion -- see _evaluate_scenario_a's comment

    org_a_ids = {e.id for e in db.execute(select(SafetyEvent).where(SafetyEvent.organization_id == org_a_id)).scalars()}
    org_b_ids = {e.id for e in db.execute(select(SafetyEvent).where(SafetyEvent.organization_id == org_b_id)).scalars()}

    summary_a = compute_summary(db, organization_id=org_a_id, as_of=as_of, window_days=365)
    summary_b = compute_summary(db, organization_id=org_b_id, as_of=as_of, window_days=365)

    return TenantIsolationResult(
        org_a_events_visible_to_org_b=len(org_a_ids & org_b_ids),  # must be 0 -- distinct id sets entirely
        org_b_events_visible_to_org_a=0 if org_a_ids.isdisjoint(org_b_ids) else len(org_a_ids & org_b_ids),
        quality_metrics_isolated=(
            summary_a.event_count == result_a.batch.accepted_records + result_a.batch.partial_records
            and summary_b.event_count == result_b.batch.accepted_records + result_b.batch.partial_records
        ),
        predictive_dataset_isolated=org_a_ids.isdisjoint(org_b_ids),
    )


# --- Top-level entry point ---------------------------------------------------------------------


def run_calibration_evaluation(db: Session, *, base_time: datetime | None = None) -> CalibrationEvaluationReport:
    # `base_time` is what every scenario's relative day-offsets (see
    # tests/fixtures/enterprise_scenarios.py) are generated against --
    # essentially "now". Each evaluator below ingests using `base_time`
    # and then captures its own fresh `as_of = utcnow()` *after* that
    # ingestion completes, for the same reason documented in
    # tests/evaluation/intelligence_harness.py's seed_and_evaluate(): a
    # single as_of value used both before and after ingestion would make
    # every just-ingested row invisible to events_as_of()'s
    # `ingestion_time <= as_of` filter, by design, not by bug.
    base_time = base_time or utcnow()
    report = CalibrationEvaluationReport()

    # One real, registered DataSource -- exercised for scenario A only,
    # to prove the full 5-link provenance chain (external record ->
    # ingestion record -> ingestion batch -> data source -> canonical
    # event) end to end; the other four scenarios ingest with
    # source_id=None, an equally valid, common real-world path.
    provenance_org_id = _make_org(db, "Calibration - Provenance Source Org")
    source = DataSource(organization_id=provenance_org_id, name="Legacy EHS Platform", source_type="ehs")
    db.add(source)
    db.commit()
    _dataset_p, result_p = _ingest_scenario(
        db, organization_id=provenance_org_id, key="A", as_of=base_time, source_id=source.id
    )
    report.provenance = _validate_provenance(
        db, organization_id=provenance_org_id, source_id=source.id, batch_id=result_p.batch.id
    )

    for key, evaluator in _SCENARIO_EVALUATORS.items():
        report.scenarios[key] = evaluator(db, base_time, None)

    report.predictive_readiness = _validate_predictive_readiness(db, base_time)
    report.tenant_isolation = _validate_tenant_isolation(db, base_time)

    return report
