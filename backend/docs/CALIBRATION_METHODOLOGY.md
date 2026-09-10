# SIE Calibration Methodology — Real-World Data Validation & Intelligence Calibration v0.1

**Prototype / controlled-scenario calibration only — not a production
benchmark.** Nothing in this document, in
`tests/evaluation/calibration_harness.py`, or in the reports it
generates (`docs/CALIBRATION_EVALUATION_REPORT.md`/`.json`) establishes
production accuracy, precision, recall, or predictive performance on any
real organization's data. It establishes something narrower and more
useful at this stage: that SIE's existing, unmodified
ingestion/validation/analytics/predictive code behaves correctly and
meaningfully on data shaped like a real organization's safety and
operational history, using controlled scenarios with a *known* correct
answer.

## 1. Purpose and governing principle

Every prior SIE milestone tested its own code in isolation, against
narrow synthetic fixtures built to exercise one code path at a time. This
milestone asks a different question: **does the whole pipeline — real
ingestion, real validation, real normalization, real data-quality
classification, real trend/signal/anomaly analytics, real predictive
dataset construction, real tenant isolation — behave correctly end to
end on data shaped like an actual organization's month-to-month
history?**

The governing rule this milestone was held to: **do not redesign the
existing SIE intelligence architecture.** Every module this methodology
exercises — `EnterpriseIngestionService`, `SafetyEventIngestionService`,
`app/intelligence/validation.py`/`normalization.py`,
`app/intelligence/temporal.py`'s `events_as_of()`/`bucketed_counts()`,
`app/intelligence/analytics.py`/`features.py`/`indicators.py`/`trends.py`/
`anomaly.py`/`signals.py`, and `app/predictions/dataset.py` — is the
exact, unchanged code prior milestones already built and unit-tested.
This is a validation and calibration exercise, not a feature milestone;
the one genuinely new production module
(`app/intelligence/terminology_mapping.py`, §4 below) is additive and
opt-in, never a change to any existing pipeline.

## 2. Controlled scenarios

`tests/fixtures/enterprise_scenarios.py` is a generic (no
Safelytic-specific schema) realistic-data fixture framework, built with
deterministic, seeded (`random.Random(seed)`) relative-day-offset
timing — the same convention `tests/fixtures/intelligence/synthetic_dataset.py`
already established. It covers the milestone's own required domain
vocabulary:

* **Incidents** — first aid case, medical treatment case, lost-time
  incident, vehicle incident, property damage, environmental event.
* **Near misses** — dropped object, vehicle near miss, fall-from-height
  near miss, process deviation.
* **Observations** — unsafe act, unsafe condition, positive observation,
  housekeeping deficiency, PPE issue.
* **Inspections** — equipment inspection, site inspection, safety
  inspection, environmental inspection.
* **Audits** — compliance finding, management-system finding, repeat
  finding.
* **Permits** — hot work, confined space, work at height, lifting
  operation.
* **Training** — completed, overdue, competency gap, expired
  certification.
* **Maintenance/operational signals** — overdue preventive maintenance,
  equipment failure, maintenance backlog.

Five scenarios (`tests/evaluation/calibration_harness.py`'s
`_SCENARIO_EVALUATORS`), each with an explicit, known-correct expected
direction, deliberately non-causal language, and a fixed default seed for
reproducibility:

| Key | Name | Seed | Records | Shape | Expected intelligence |
|---|---|---|---|---|---|
| A | Stable / Low Concern | 1001 | 72 | Flat activity across four consecutive 30-day periods | Stable trends, no risk signals |
| B | Emerging Risk | 1002 | 77 | Near misses/unsafe observations/overdue training/maintenance sharply up in the current 30 days vs. a quiet 90-day baseline; incidents stay flat | Leading indicators deteriorate (trend increasing, `UNSAFE_OBSERVATION_SURGE`/`TRAINING_COMPLIANCE_DROP` fire); **no claim these factors caused an incident**, since none occurs |
| C | Lagging Event Increase | 1003 | 65 | Leading indicators identical to a stable 4-period baseline; a sudden high-potential incident cluster in the current window | Incident trend increasing, `HIGH_POTENTIAL_EVENT_CLUSTER` fires, anomaly detected where statistically justified (≥4 baseline periods) |
| D | Data Quality Degradation | 1004 | 16 | Missing event dates, an invalid classification, an exact-duplicate resend, a same-version content conflict, missing identifiers, mixed with valid records | Degraded quality metrics reflect the mix; quarantined/rejected records excluded from analytics, never silently trusted |
| E | Recovery | 1005 | 53 | An elevated period improving into a recovered current 30 days | Leading/risk indicators improve; **improvement in indicators is never asserted as proof of actual safety improvement** |

## 3. Data-quality benchmarking

`DataQualityBenchmark.from_ingestion_result()` computes, directly from a
real `EnterpriseIngestionResult`: total, valid, partial, quarantined,
rejected, duplicate, stale (`SKIPPED_STALE_VERSION`), and version-conflict
(`REJECTED_VERSION_CONFLICT`) record counts, plus missing-timestamp,
invalid-classification, and missing-identifier counts derived from each
record's own validation issue codes. From these it derives completeness,
acceptance, rejection, quarantine, duplicate, and temporal-validity
rates.

**These are schema-validity metrics only.** A record classified `VALID`
passed SIE's structural and referential checks — it is never asserted to
be factually correct about what actually happened at the site. This
distinction is restated everywhere these numbers are reported.

One genuine subtlety, confirmed while building scenario D: `EnterpriseIngestionBatch.accepted_records`
counts *ingestion record outcomes* whose own `quality_state` resolved to
`VALID` — including a duplicate resend or a version conflict that
resolved *against* an already-valid existing row without creating a new
canonical event. This is deliberately different from "how many distinct
canonical `SafetyEvent` rows carry `VALID`/`PARTIAL` quality" (what
`compute_summary()`'s `event_count` actually reflects via
`events_as_of()`). The calibration harness's own "quarantined records
never silently become trusted intelligence" check queries the canonical
rows directly for this reason, rather than comparing against the batch's
own per-record-outcome counters.

## 4. Terminology mapping methodology

`app/intelligence/terminology_mapping.py` is a small, deterministic (no
LLM), table-driven mapping layer for real-world terminology variance —
e.g. `"Near Miss"`/`"Near-Miss"`/`"NM"`/`"Potential Incident"` all
mapping to the canonical `NEAR_MISS` incident type — covering incident
types, observation types, inspection types, audit findings, training
status, and maintenance status.

**Ambiguous or unrecognized terminology is never guessed.** Each mapping
function returns an explicit `MappingOutcome` (`MAPPED`/`AMBIGUOUS`/
`UNKNOWN`); `TerminologyMappingAdapter.validate()` turns an
`AMBIGUOUS`/`UNKNOWN` outcome into a blocking `ValidationIssue`, reusing
the existing `validate_and_normalize()` blocking-issue → `QUARANTINED`
rule rather than inventing a second quarantine path. The adapter
integrates through the pre-existing `DataSourceAdapter` Protocol
(`app/intelligence/adapters.py`) as a second, opt-in implementation —
the default `GenericJSONAdapter` and the core pipeline are unchanged.
`source_value` — the payload exactly as received — is always preserved
even when the canonical fields carry the mapped, not the original,
terminology; `tests/test_terminology_mapping.py` covers this explicitly.

## 5. Temporal validation methodology

`tests/test_enterprise_temporal_calibration.py` is additive to the
pre-existing, mandatory 6-case `tests/test_temporal_leakage.py`. Every
case there hand-seeds `SafetyEvent` rows to test `events_as_of()`'s query
contract directly; every case here goes through the real
`EnterpriseIngestionService` end to end, proving the same guarantee holds
for actually-ingested data, including:

* The milestone's own worked example: an incident dated 2026-01-10 but
  only ingested 2026-02-05 must not appear in a 2026-01-31 snapshot.
* A late-arriving batch of historical records, invisible to any `as_of`
  before real ingestion completed.
* A version correction (`source_record_version` bump) re-stamping
  `ingestion_time` at the correction's own real ingestion moment — a
  documented, asserted characteristic of a single-physical-row upsert:
  a point-in-time snapshot *between* the original ingestion and a later
  correction can no longer, after that correction has happened, be
  reconstructed from that row.
* A stale, out-of-order version arriving after a newer one, never
  disturbing already-applied content.
* A plausible future `event_time` (accepted, not rejected — only an
  implausibly-far-future date is), correctly excluded until that future
  time arrives.
* Duplicate timestamps on genuinely distinct records (identity is never
  conflated with a shared timestamp).
* Out-of-order batch arrival (arrival order never assumed to match
  `event_time` order).

### A real calibration finding: bulk backfills and per-bucket point-in-time correctness

Calibrating trend/signal/anomaly analytics against these scenarios
surfaced a genuine, previously unexercised interaction. `bucketed_counts()`
(`app/intelligence/temporal.py`) checks `ingestion_time <= as_of`
**per bucket**, using that bucket's own historical end date as `as_of`
— exactly what point-in-time correctness demands. A one-shot bulk
historical backfill stamps every row's `ingestion_time` at the same real
"now," so every bucket whose own boundary predates that real ingestion
moment correctly excludes all of it: none of that history was actually
knowable to the system at any of those earlier boundaries. The visible
consequence is that **retrospective trend reconstruction over a bulk
backfill collapses into the single most recent bucket** unless the data
was ingested with a realistic, near-real-time cadence.

This is not a bug, and this milestone did not change
`app/intelligence/temporal.py` to work around it (that would be
redesigning the guarantee this milestone was told to preserve). The
calibration harness instead simulates the realistic case these scenarios
actually describe — an organization operating day to day, not migrating
history in one sitting — by directly backdating `ingestion_time` to
track shortly after each event's own `event_time`
(`_backdate_ingestion_time_near_event_time()` in
`tests/evaluation/calibration_harness.py`, never through the ingestion
service itself, mirroring the pre-existing `stale_data_org` backdating
pattern in `tests/evaluation/intelligence_harness.py`).

**Real-world implication for a genuine bulk-migration integration**: an
organization migrating years of history from a legacy EHS platform in
one ingestion run should expect retrospective trend/anomaly analytics
over that backfilled period to be unreliable until either (a) the
integration backdates `ingestion_time` to a realistic per-record value
reflecting when each record actually became known (not built into any
shipped connector today), or (b) a caller with a legitimate reason to
reconstruct history explicitly queries with `strict_point_in_time=False`
(supported by `events_as_of()` today, but not exposed by
`compute_trend()`/`bucketed_counts()`, which always use the strict
default — extending that is out of this milestone's scope). *Live,
day-to-day* ingestion, which is the normal operating mode a
production deployment expects, is unaffected: each record's own
`ingestion_time` naturally tracks close to its `event_time`.

## 6. Intelligence calibration methodology

For each scenario, the harness runs real ingestion, then real
`compute_trend`/`compute_summary`/`risk_signal_service.detect_all`/
`detect_anomaly` calls, and compares the result against that scenario's
own known-correct expected direction. Each individual check is
classified:

* **`EXPECTED`** — the real result matches the scenario's known-correct
  direction.
* **`UNEXPECTED`** — it does not.
* **`INDETERMINATE`** — the method genuinely cannot support a
  determination (e.g. a boolean condition this harness cannot evaluate)
  — never forced to a binary pass/fail.

`ScenarioCalibrationResult.all_expected()` requires every check for that
scenario to be `EXPECTED`. `tests/evaluation/test_calibration_evaluation.py`
asserts this for all five scenarios as of this milestone's own
completion — an `UNEXPECTED` result found during development (e.g.
scenario trends appearing flat/empty before the bulk-backfill cadence
fix in §5, or the accepted-records accounting subtlety in §3) was treated
as a real finding to fix or explain, never as a check to loosen.

## 7. Provenance validation methodology

`_validate_provenance()` walks the full chain for every accepted record
in a real ingested batch: external record → `EnterpriseIngestionRecord`
→ `EnterpriseIngestionBatch` → `DataSource` → canonical `SafetyEvent`,
confirming the external record id, source system, content hash,
normalization status, and schema version all survive intact through
real ingestion, never re-derived or approximated.

## 8. Predictive dataset-readiness methodology

**Goal, in the milestone's own words: "Can we reliably construct a
defensible dataset for real model validation?"** Never "is the model
good." `tests/test_predictive_dataset_readiness.py` and the harness's own
`_validate_predictive_readiness()` validate
`app/predictions/dataset.py::build_training_examples()` against
realistic, site-scoped data:

* **Correct `(site, as_of)` construction** — one example per pair, no
  fewer, no cross-contamination.
* **Feature availability** — a feature vector genuinely reflects real
  ingested activity (a non-`None`, correctly elevated value after a
  realistic escalation, a materially lower one before it).
* **No future leakage** — proven concretely: a snapshot built before a
  realistic escalation shows the quiet baseline; one built after shows
  the real, elevated count.
* **Label construction** — uses only events strictly after `as_of`,
  within the horizon; a same-day-before incident never contributes.
* **Missing-data handling** — a site with zero events still produces a
  defensible (never crashing) example with an honest data-quality
  classification.
* **Tenant isolation** — one organization's examples never reflect
  another's ingested activity.
* **Reproducibility** — building the same `(site, as_of)` set twice
  produces byte-for-byte identical `TrainingExample`s, not merely
  matching feature vectors.

**This validates dataset construction correctness only.** No model is
trained, tuned, or evaluated for accuracy anywhere in this milestone;
feature/label separation itself remains
`tests/test_feature_label_separation.py`'s own, unmodified regression
test, not re-proven here.

## 9. Multi-tenant validation

Every scenario, the provenance check, and the predictive-readiness check
run against a fresh, dedicated `Organization`. `_validate_tenant_isolation()`
additionally ingests two *different* scenarios into two organizations in
the same evaluation run and confirms neither organization's canonical
events, quality metrics, or predictive datasets are visible to the
other. GLOBAL-scoped knowledge access is unaffected by this milestone;
its own tenant-isolation tests (from prior milestones) are unchanged.

## 10. Repeatability

Every scenario, fixture, and mapping table uses only deterministic,
seeded (`random.Random(seed)`) randomness and relative time offsets from
a caller-supplied `base_time` — never the global `random` module,
wall-clock-derived randomness, or an external API/network/LLM call.
`tests/evaluation/test_calibration_evaluation.py` asserts exact,
seed-derived record counts per scenario (72/77/65/16/53) directly. The
full calibration run was confirmed to produce identical scenario record
counts and calibration outcomes across repeated executions.

## 11. How to run the evaluation

```bash
cd backend
# Requires real PostgreSQL + pgvector -- see tests/postgres_support.py.
# PG_TEST_DATABASE_URL defaults to postgresql+psycopg://sie:sie@localhost:5432/sie_test
.venv/bin/python -m pytest tests/evaluation/test_calibration_evaluation.py -s
```

This regenerates `docs/CALIBRATION_EVALUATION_REPORT.md` and
`docs/CALIBRATION_EVALUATION_REPORT.json`. The additive temporal and
predictive-readiness suites can be run the same way:

```bash
.venv/bin/python -m pytest tests/test_enterprise_temporal_calibration.py           # SQLite, no Postgres needed
.venv/bin/python -m pytest tests/test_predictive_dataset_readiness.py               # requires real PostgreSQL
.venv/bin/python -m pytest tests/test_terminology_mapping.py                        # SQLite, no Postgres needed
```

## 12. Interpreting the results

* A scenario with every check `EXPECTED` means the real, unmodified
  ingestion/analytics/predictive pipeline behaved exactly as designed on
  that one controlled, synthetic scenario. It is evidence the pipeline
  is internally consistent and correctly wired end to end — it is not
  evidence about how SIE will behave on any real organization's actual
  data, whose distribution, noise, and edge cases this framework does
  not and cannot represent.
* `INDETERMINATE` is a legitimate, intentional outcome, not a failure —
  it means the underlying method (e.g. anomaly detection below its
  minimum baseline period count) genuinely cannot support a
  determination for that check, and the harness says so rather than
  forcing one.
* Data-quality rates describe schema validity, never factual accuracy of
  what a record claims happened.
* None of the calibration outcomes, rates, or provenance/readiness
  results in `docs/CALIBRATION_EVALUATION_REPORT.md` may be cited as a
  production accuracy, precision, recall, or performance claim. The
  report itself restates this next to every number it prints.

## 13. What this methodology deliberately does not cover

No advanced ML, no deep learning, no model retraining, no autonomous
agents or interventions, no worker-level scoring, no LLM-based
normalization or mapping, no web crawling, no external intelligence
feeds, no event streaming, no Redis queues, no distributed workers, no
production alerting, no automated safety decisions — none of this was
built, and none of it is validated here. See this repository's own
`README.md`, ["Real-World Data Validation & Intelligence Calibration
Architecture"](../README.md#real-world-data-validation--intelligence-calibration-architecture)
section, for the full architecture writeup and this milestone's own
"Known gaps / next phase" entry.
