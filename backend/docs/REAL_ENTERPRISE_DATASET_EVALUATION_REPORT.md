# SIE Real Enterprise Dataset Evaluation Report v0.1

**This is the first evaluation of SIE against a real (non-synthetic) enterprise HSE dataset.**
It is an evaluation milestone, not an intelligence redesign: no predictive ML, autonomous
agents, LLM classification, automated recommendations, new thresholds, or new intelligence
algorithms were added to produce it. Every ingestion, validation, terminology-mapping,
temporal-integrity, provenance, intelligence, and predictive-readiness result below comes from
the existing, unmodified SIE pipeline (`EnterpriseIngestionService`, `terminology_mapping.py`,
`terminology_review.py`, `events_as_of()`, `analytics.py`, `signals.py`,
`feature_snapshot_service.py`, `app/predictions/dataset.py`, `hse_review_service.py`) run
through two new, thin orchestration modules:
`app/validation/real_dataset_loader.py` (workbook → `RawSafetyEventPayload`) and
`app/validation/real_dataset_evaluation.py` (loader → ingestion → existing validation harness →
observation-vs-incident temporal analysis → HSE review queuing).

**Dataset.** Two workbooks supplied outside version control: the primary data workbook
(`Observation & Incident Records Jan - July 2026.xlsx` — 45 Incident-sheet rows, 1,000
Observation-sheet rows, 13 distinct projects) and a secondary reconciliation workbook
(`Incident vS Observation.xlsx`, used only as a cross-check — its own pivot counts were
confirmed to match the primary workbook's own raw-data aggregates). **Neither workbook, nor any
raw record derived from them, is committed to this repository or reproduced verbatim in this
report.** Personal names appearing in the source workbook's free-text narrative fields
(`Description`, `WitnessStatement`, `Root Cause Analysis`, `PeopleInvolved`, `Reported By`,
`Finding`, `Comment`, ...) are preserved on the ingested `SafetyEvent` rows in the application's
own database exactly like any other enterprise ingestion payload always has been — never in
source control, never in this report, and never read by feature engineering or predictive
readiness (verified directly — see "PII handling" below).

**A note on scope.** This task referenced a "Real Enterprise Dataset Evaluation Specification"
containing "the fixed intelligence questions" this evaluation was meant to answer. **That
document was not supplied to this session.** Rather than fabricate intelligence questions to
answer, this evaluation instead reports what the existing, unmodified SIE pipeline actually
produces when given this real dataset — descriptive summaries, terminology results, temporal/
provenance integrity, and predictive-readiness — and flags this omission explicitly as a
limitation, not something to be silently worked around.

---

## 1. Components exercised (of the 15 requested)

| # | Component | Status |
|---|---|---|
| 1 | Load the supplied workbook | Done — `load_real_dataset()` |
| 2 | Validate its structure | Done — 0 structural issues on the real workbook |
| 3 | Map observations into the ingestion contract | Done — 1,000/1,000 rows mapped |
| 4 | Map incidents into the ingestion contract | Done — 45/45 rows mapped |
| 5 | Preserve source-system/source-record provenance | Done — `source_system="alm-hse-xlsx"`, `source_record_id` = the workbook's own `Document No` on every payload |
| 6 | Deterministic terminology review | Done — reused, unmodified `terminology_review.py` |
| 7 | Data-quality evaluation | Done — reused, unmodified `enterprise_dataset_validation.py` |
| 8 | Temporal-integrity checks | Done |
| 9 | Provenance validation | Done — 1,045/1,045 chains checked, all intact |
| 10 | Descriptive intelligence | Done — reused `compute_summary()`/`compute_trend()`/`risk_signal_service` |
| 11 | Observation-vs-incident temporal analysis | Done — new orchestration, item 11 below |
| 12 | Predictive-readiness assessment | Done — `INSUFFICIENT_DATA`-shaped result, see §7 |
| 13 | Machine-readable evaluation report | This document's companion `REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.json` |
| 14 | Human-readable evaluation report | This document |
| 15 | HSE expert-review candidates | Done — 469 candidates queued (reused `queue_review_candidates()`) |

---

## 2. OBSERVED — what the dataset actually contains

- Total records: **1,045** (45 incident + 1,000 observation)
- Distinct source systems: 1 (`alm-hse-xlsx` — a single workbook export, both sheets)
- Distinct raw `event_type` terms: 9 (8 raw `Incident Type` values + the literal `OBSERVATION`)
- Event time range: **2025-05-02 to 2026-08-17** — wider than the "Jan – July 2026" label on the
  primary workbook's own filename; the earliest incidents predate that window by ~8 months, and
  observation dates extend slightly past July into mid-August. Reported as-is, not corrected.
- Projects: 13 distinct project names across both sheets. The Incident sheet's own 6 projects
  (ZILCO, SECRETARIAT, ARTEE AGRO WAREHOUSE, KADARS GATE, MISSOURI, LEKKI FREE-ZONE) are a strict
  subset of the Observation sheet's 13 — 7 projects (AGBASO WATER, ARTEE AGRO WAREHOUSE\*,
  ATLANTIS PERIWINKLE, AYLOR, BANANA VILLA-1, PADAH LNG, PARK-AVENUE, BLUE SQUARE) have
  observations recorded but no incident on record at all. **This is reported as an observed fact,
  not interpreted as "these projects are safe"** — see the Important Data Rules explicitly
  carried into this evaluation.
- Zero duplicate `Document No` values within either sheet, and zero cross-sheet ID collisions.

## 3. MAPPED / QUARANTINED / REJECTED — what SIE did with it

| Outcome | Count | % of total |
|---|---:|---:|
| VALID (mapped, usable) | 595 | 56.9% |
| PARTIAL | 0 | 0% |
| QUARANTINED | 450 | 43.1% |
| REJECTED | 0 | 0% |
| Missing identifiers | 0 | |
| Missing timestamps | 0 | |
| Future timestamps | 0 | |
| Invalid classifications (= quarantined) | 450 | |

No record was rejected outright: every row had both a `Document No` and a `Date`. **43.1% of the
dataset (450/1,045 records) was quarantined** — entirely because of terminology this evaluation
was instructed not to guess (see §4). Quarantined records are stored (full provenance intact) but
held out of every analytics/feature/signal/predictive calculation until a human reviews them.

## 4. UNKNOWN / AMBIGUOUS — terminology review (item 6)

`app/intelligence/terminology_mapping.py`'s existing, curated alias table was **not modified** for
this evaluation (see rationale below). Every raw term from the workbook was passed through
unresolved and evaluated against that unchanged table:

**event_type (Incident sheet's own `Incident Type` column, 8 distinct raw terms, 45 records):**

| Raw term | Occurrences | Result |
|---|---:|---|
| `Injury` | 22 | **MAPPED** → `INCIDENT` (alias `"injury"`) |
| `NearMiss` | 6 | UNKNOWN (no alias match — `"near miss"`, with a space, exists; the workbook's camelCase `NearMiss` does not) |
| `PropertyDamage` | 5 | UNKNOWN |
| `FireIncident` | 4 | UNKNOWN |
| `Others` | 3 | UNKNOWN |
| `SecurityBreach` | 2 | UNKNOWN |
| `VehicleAccident` | 2 | UNKNOWN |
| `HazardObservation` | 1 | UNKNOWN |

Only **Injury (49% of incident records)** cleanly matched the existing alias table. The other 51%
(23/45 records) resolved UNKNOWN and were quarantined — a genuine finding: this real dataset's own
vocabulary is largely disjoint from the table prior milestones built against synthetic scenarios.

**event_subtype (Observation sheet's own `Category` column, 15 distinct raw terms, 1,000 records):**

| Result | Terms | Records |
|---|---:|---:|
| MAPPED | 4 (`Unsafe Condition`→`UNSAFE_CONDITION`, `Housekeeping`→`HOUSEKEEPING_DEFICIENCY`, `Unsafe Act`→`UNSAFE_ACT`, `Positive Observation`→`POSITIVE_OBSERVATION`) | 573 |
| UNKNOWN | 11 (`Working At Height`, `PPE Compliance`, `Electrical Safety`, `Environmental`, `Lifting Operations`, `Procedure Violation`, `Equipment Safety`, `Others`, `Documentation`, `Fire Safety`, `Emergency Preparedness`) | 427 |

`event_type` for every Observation-sheet row is the literal, unambiguous string `"OBSERVATION"`
(a structural fact — the sheet has no competing top-level classification column — never a guess);
that term maps cleanly (1,000/1,000 records).

**No ambiguous terms** were found in this dataset (0 in either domain) — every term was either a
clean alias match or had no match at all.

**Why the alias table was not extended mid-evaluation:** this task is explicitly an evaluation
milestone, not an intelligence redesign, and its own instruction is "do not guess unknown
terminology." Extending the table to make this dataset look more mapped would silently patch over
exactly the finding this milestone exists to surface. See §9 for a recommended, reviewed next step.

## 5. Temporal integrity (item 8)

- Out-of-order arrival detected: **True** (expected — a bulk historical export, not a live feed)
- Duplicate timestamp groups: 181 (many rows share a `Date` with day-level, not
  timestamp-level, precision in the source workbook)
- Future-dated records (relative to real "now"): **0**
- Corrections / stale versions / version conflicts: 0 / 0 / 0 (no `source_record_version` field
  in this dataset; every `Document No` is unique per sheet)
- Late-arriving records (`ingestion_time` > 24h after `event_time`): 1,045/1,045 — expected: this
  is a one-time bulk backfill of historical data, ingested in a single batch "today."
- **Point-in-time leakage check: PASSED.** A snapshot taken long before this evaluation ran
  correctly sees none of these just-ingested rows, regardless of how old their `event_time`
  claims to be — `events_as_of()`'s `ingestion_time <= as_of` guarantee holds.

## 6. Provenance (item 9)

- Chains checked: **1,045 / 1,045** — **all intact**, zero failures.
- Every canonical event traces back to its ingestion batch, its source system/record id, and its
  (where applicable) content hash.
- Feature-indicator stage reachable: **True** — at least one canonical event from this batch
  appears in a real feature snapshot's own `source_event_ids`.
- Predictive-dataset stage reachable: **True**.

## 7. Descriptive intelligence (item 10)

- Data sufficiency (org-wide, 365-day window): **SUFFICIENT_DATA** (587 usable events)
- Trend readiness: `observation_count` and `unsafe_observation_count` — **INCREASING**; every
  other tracked metric (`incident_count`, `near_miss_count`, `audit_count`, `inspection_count`,
  `overdue_action_count`, `equipment_failure_count`) — **STABLE**
- Signals detected: `UNSAFE_OBSERVATION_SURGE`
- Anomaly status: **NORMAL**

**SUPPORTED CONCLUSION:** the volume of observation reporting (all categories, and specifically
unsafe-observation reporting) increased over the analysis window, and this increase is large
enough that the existing, unmodified `UNSAFE_OBSERVATION_SURGE` signal fired.

**UNSUPPORTED CONCLUSION (explicitly not claimed):** that this increase in observation volume
reflects a change in underlying site safety, that it is caused by any specific project or event,
or that it predicts a future incident. An increase in *reported* observations is equally
consistent with improved reporting culture, a new observation program, or seasonal site activity
— this evaluation has no basis to distinguish between those explanations and does not attempt to.

### 7a. Observation-vs-incident temporal analysis (item 11)

A new, purely descriptive orchestration (`_analyze_observation_incident_temporal()`) bucketing
OBSERVATION events against incident-sheet events into the same 30-day windows per project, using
only the existing `events_as_of()` query builder (queried retrospectively — by `event_time` alone,
not gated by `ingestion_time` — since the question here is "what did this dataset's own history
contain," not a live point-in-time feature computation; see the module's own docstring for why a
strict point-in-time reading of a just-bulk-ingested dataset would show ~zero events in every
bucket but the most recent).

| Project | Total observations | Total incidents |
|---|---:|---:|
| ATLANTIS PERIWINKLE | 184 | 0 |
| SECRETARIAT | 107 | 4 |
| ZILCO | 75 | 2 |
| ARTEE AGRO WAREHOUSE | 49 | 2 |
| MISSOURI | 38 | 0 |
| PADAH LNG | 32 | 0 |
| AYLOR | 30 | 0 |
| KADARS GATE | 28 | 0 |
| AGBASO WATER | 12 | 0 |
| LEKKI FREE-ZONE | 5 | 1 |
| BANANA VILLA-1 | 9 | 0 |
| PARK-AVENUE | 2 | 0 |
| BLUE SQUARE | 2 | 0 |

**SUPPORTED CONCLUSION:** most projects with a large observation volume in this window recorded
zero incidents (e.g. ATLANTIS PERIWINKLE, 184 observations / 0 incidents); the four projects with
any recorded incident at all (SECRETARIAT, ZILCO, ARTEE AGRO WAREHOUSE, LEKKI FREE-ZONE) also have
substantial observation activity in the same window.

**UNSUPPORTED CONCLUSION (explicitly not claimed):** that observation activity caused, prevented,
or is correlated in any statistically meaningful sense with incident occurrence. No correlation
coefficient or statistical test was computed — the task's own instruction ("same-project
observation + incident = causal relationship" must not be assumed) is treated as binding, and a
project with zero recorded incidents is reported as exactly that — zero recorded incidents in this
window — never as "this project is safe."

## 8. Predictive-readiness assessment (item 12)

| Metric | Value |
|---|---|
| Eligible sites | 13 / 13 |
| Excluded sites | 0 |
| Qualifying incidents (within the analysis window) | 22 |
| Positive labels (confirmed) | **0** |
| Negative labels (confirmed) | **0** |
| Unavailable labels | **13** (every site) |
| Class distribution | not computed — no confirmed label exists |
| Incomplete feature windows | 13 / 13 |
| Missing feature values (summed) | 65 |

**No model was trained. No predictive accuracy, PR-AUC, ROC-AUC, precision, or recall is claimed
anywhere in this report.**

**INSUFFICIENT_DATA finding, and why:** every one of the 13 sites reports its label as
`UNAVAILABLE`, not positive or negative. This is not a data-volume problem — it is a structural
property of evaluating **"as of right now"** against data that was **just bulk-ingested**: the
prediction horizon (30 days, `HORIZON_DAYS`) by definition has not elapsed yet for *any* `as_of`
at or near real "now," so no label can be confirmed either way. This is the existing,
unmodified `PredictiveReadinessReport` correctly refusing to fabricate a label — see §9's
architecture-limitation note for what this means for real deployments.

## 9. Architecture limitations discovered

1. **A live "as_of = now" evaluation of bulk-backfilled historical data cannot produce a single
   confirmed predictive label**, no matter how much history it contains, because the horizon
   window is inherently unelapsed relative to real "now." Genuine label confirmation requires
   `as_of` to be set to a **historical** cutoff (e.g., 30+ days before the dataset's own latest
   date) rather than defaulting to live "now" — this is a legitimate use of the existing
   `as_of` parameter, not a code change, but it was not obvious until this real-data run
   surfaced it, and is worth calling out explicitly for whoever runs the next predictive
   evaluation against this or a similar backfilled dataset.
2. **Strict point-in-time bucketed trend analysis (`bucketed_counts()`, `ingestion_time <= as_of`)
   is unusable for describing a bulk-backfilled dataset's own history** — every historical bucket
   legitimately shows zero, because `ingestion_time` for every row is "now," which postdates every
   bucket but the most recent. This is correct, already-documented behavior (the same "bulk
   backfill collapses into the most recent bucket" finding from Milestone 2), but it meant item
   11's own analysis had to be built as an explicit RETROSPECTIVE query
   (`events_as_of(..., strict_point_in_time=False)`) rather than reusing `bucketed_counts()`
   as-is, since that helper does not expose the `strict_point_in_time` flag. A small, optional
   extension to `bucketed_counts()` to accept `strict_point_in_time` would let a future caller
   choose either mode without reimplementing its bucketing loop, as this evaluation had to.
3. **The dataset's own second `Status` column is empirically an internal data-quality/review
   flag, not a duplicate of the business open/closed lifecycle** — confirmed with an exact,
   nearly-inverse correspondence: `Closed` ↔ `REVIEW REQUIRED` (959/959) and `Open` ↔ `OK`
   (41/41), and independently confirmed by the reconciliation workbook's own "Observation
   Executive Summary" sheet, which labels these same two counts as "Records passing data-quality
   checks: 41" / "Records requiring review: 959." This is real, concrete confirmation of the
   task's own explicit warning not to assume `Status.1` is authoritative — treating it as a
   restated business status would have been actively wrong, not merely redundant.
4. **The existing terminology alias table, built entirely from synthetic scenario data in prior
   milestones, resolves only 49% of this real dataset's `Incident Type` vocabulary and 57% of its
   `Category` vocabulary.** This is not a code defect — it is the correct, conservative behavior
   ("never guess") doing exactly what it should — but it does mean a real deployment against
   HSE workbooks shaped like this one would quarantine a substantial fraction of records until a
   human curates the missing aliases. See §10 for the specific terms worth reviewing.
5. **The Real Enterprise Dataset Evaluation Specification referenced by this task's own
   instructions (the document meant to supply "the fixed intelligence questions" this evaluation
   should answer) was never supplied to this session.** This report answers what the existing
   pipeline actually produces against real data instead of inventing questions to fit; a future
   milestone should supply that specification if it exists, so this evaluation can be re-run
   against it directly.

## 10. Recommendations for the next milestone

1. **Human-reviewed terminology alias additions**, evaluated deliberately and separately from any
   evaluation run — candidates directly confirmed by this dataset:
   `NearMiss` → likely `NEAR_MISS`, `PropertyDamage` → likely `PROPERTY_DAMAGE`,
   `FireIncident` → likely `FIRE`, `VehicleAccident` → likely `VEHICLE_ACCIDENT`,
   `SecurityBreach` → likely `SECURITY`, plus a `Category` alias sweep for `PPE Compliance`,
   `Working At Height`, `Electrical Safety`, `Lifting Operations`, `Fire Safety`,
   `Emergency Preparedness`, `Environmental`, `Procedure Violation`, `Equipment Safety`,
   `Documentation`. These are proposals for human review, not applied here.
2. **Re-run predictive readiness with an explicit historical `as_of`** (e.g. 30+ days before the
   dataset's own latest observation date) once the terminology gaps above are addressed, to get a
   genuine reading of positive/negative label availability rather than the structurally-forced
   `UNAVAILABLE` result this live run produced.
3. **Obtain and evaluate against the Real Enterprise Dataset Evaluation Specification** referenced
   by this task, if one exists, so the "fixed intelligence questions" it describes can be answered
   directly rather than inferred.
4. **Extend `bucketed_counts()` with an optional `strict_point_in_time` passthrough** so a
   retrospective analysis like item 11 does not need to duplicate its bucketing loop.
5. Do not proceed to advanced ML, autonomous agents, automated interventions/retraining, external
   web intelligence, production deployment, or new intelligence algorithms without a separate,
   explicit approval — per this task's own stop condition.

## 11. PII handling — verified, not assumed

- Free-text narrative fields (containing real personal names, confirmed by direct inspection of
  the source workbook during the design phase of this evaluation) are preserved on each ingested
  `SafetyEvent` row exactly as any other enterprise payload always has been — in the application's
  own database only.
- **Verified by regression test** (`tests/test_real_dataset_evaluation.py::test_pii_is_never_read_by_feature_engineering`)
  that `compute_feature_set()` never reads a narrative/attributes field — every `FeatureValue` it
  produces is a plain number, never free text.
- **Verified directly against this real run**: neither `REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.md`
  nor `.json`, nor any file in this repository, contains any name from the source workbook's
  narrative fields — confirmed by an explicit string-absence check against the real generated
  report before this document was written.
- No PII field was used as a predictive feature — predictive readiness reads only structured
  `event_type`/`event_subtype`/`severity`/`status`/`site_id`/`event_time` fields, the same
  guarantee `app/intelligence/features.py`'s own docstring already documents.

---

*Generated against real PostgreSQL from the real, uploaded workbook, processed only from a local,
non-repository scratch directory and never committed. See the companion
`REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.json` for the full machine-readable detail (including
per-project, per-30-day-window observation/incident counts and the complete terminology review),
and `app/validation/real_dataset_loader.py` / `app/validation/real_dataset_evaluation.py` for the
reusable evaluation pipeline itself.*
