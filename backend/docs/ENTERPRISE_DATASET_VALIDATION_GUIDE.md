# Enterprise Dataset Validation Guide — Real Enterprise Dataset Validation Foundation v0.1

**This is a validation foundation, not a validation result.** Nothing in
this document, in `app/validation/`, or in any report it generates is
evidence about how SIE behaves on a real customer's data — it is the
reusable framework a subsequent step will run *once a real, anonymized
enterprise dataset is actually supplied*. See §12 for the explicit
boundary this document is not allowed to blur.

## 1. How a future enterprise dataset should be supplied

The harness (`app/validation/enterprise_dataset_validation.py::run_enterprise_dataset_validation()`)
takes exactly what `EnterpriseIngestionService.ingest_batch()` already
takes: a `organization_id` and a `list[RawSafetyEventPayload]` (the same
type `POST /api/v1/data/ingestion` accepts — see
`docs/INTEGRATION_GUIDE.md` §16 for the full wire contract). A real
dataset supply means converting whatever export format an organization's
legacy system produces (CSV, an API export, a database dump) into that
same list of records — there is no separate "validation-only" schema to
learn. The harness never talks to a database it doesn't already know
about, never reaches out to the network, and never invokes an LLM.

**Nothing here loads or commits confidential data to this repository.**
Item 13's own instruction, unchanged: a real dataset is supplied to a
running SIE instance's own database, evaluated there, and never checked
into source control — the synthetic fixture
(`tests/fixtures/messy_enterprise_dataset.py`) is the only dataset this
repository itself contains.

## 2. Required fields

Exactly the four identity fields the enterprise ingestion contract
already requires (unchanged by this milestone): `event_type`,
`event_time`, `source_system`, `source_record_id`. A record missing any
of these is `REJECTED_INVALID` — no canonical event is created, and the
harness's `IngestionSummary.rejected` count reflects it.

## 3. Optional fields

Everything else: `event_subtype`, `site_id`, `location`, `project`,
`department`, `contractor`, `activity`, `severity`, `potential_severity`,
`status`, `description`, `attributes`, `source_record_version`,
`correlation_id`, `source_schema_version`, `period_end`, `reported_time`.
A missing optional field is not a validation failure — it is simply an
absent value, and `DataQualitySummary.incomplete_records` reflects
records that are usable but carry a non-critical gap, never a rejection.

## 4. How source terminology is mapped

`app/intelligence/terminology_mapping.py` (unchanged from Milestone 2)
resolves a source system's own label for `event_type`/`event_subtype`/
training status/maintenance status against a deterministic, hand-curated
alias table — **no LLM, no fuzzy matching, no probabilistic guessing**.
Pass `use_terminology_mapping=True` (the harness's own default) to have
this happen during real ingestion via `TerminologyMappingAdapter`, so
ambiguous/unknown terminology is genuinely quarantined, not merely
flagged by a side analysis. See `docs/CALIBRATION_METHODOLOGY.md` §4 for
the mapping methodology itself (unchanged here) and
`app/intelligence/terminology_review.py`'s own docstring for how this
milestone builds a *review structure* on top of it, without touching the
mapping functions themselves.

## 5. How ambiguous terminology is reviewed

Every source term the harness observes (`extract_term_observations()`)
is resolved exactly once per unique `(domain, context, term)` and
reported as a `TerminologyReviewEntry`: `source_term` →
`proposed_canonical_term` → `status` (`MAPPED`/`UNKNOWN`/`AMBIGUOUS`,
plus the actionable `requires_review` flag this module's own docstring
calls `REVIEW_REQUIRED`) → `reason`. An `UNKNOWN`/`AMBIGUOUS` entry's
`proposed_canonical_term` is always `None` — it is never guessed.
`queue_review_candidates()` turns every such entry into a pending
`HseExpertReview` row (§ below) for a future human to actually decide.

## 6. How quarantined records are handled

Exactly the pre-existing `DataQualityStatus.QUARANTINED` rule (unchanged
across every milestone): a quarantined record is stored, keeps its full
provenance, but is excluded from every analytics/feature/signal
calculation via `events_as_of()`'s own default filtering — until a human
reviews it. `queue_review_candidates()` also queues every quarantined
record from a batch as a `QUARANTINED_RECORD` review candidate.
`report.ingestion.quarantined` and the report's own `## QUARANTINED`
section (see `app/validation/report.py`) report the count and every
underlying reason.

## 7. How provenance is validated

`ProvenanceValidationReport` walks the full chain item 5 names: source →
external record → `EnterpriseIngestionRecord` → `EnterpriseIngestionBatch`
→ `DataSource` → canonical `SafetyEvent` → (when the batch carries a
site-scoped record) a real `FeatureSnapshot` → a real `TrainingExample`.
`failures` lists exactly which record's chain broke, and why, rather
than a single pass/fail bit. `feature_stage_reachable`/
`predictive_stage_reachable` are `None` (not `False`) when the dataset
carries no site-scoped record to check — genuinely nothing to verify is
never reported as a broken chain.

## 8. How temporal integrity is tested

`TemporalIntegrityReport` reports out-of-order arrival, duplicate
timestamps, future-dated records, corrections applied, stale versions
skipped, version conflicts detected, "late-arriving" records (real
`ingestion_time` more than 24h after their own `event_time`), and a
concrete point-in-time leakage check (a snapshot from before real
ingestion must never see a just-ingested row, however old its
`event_time` claims to be) — all through `events_as_of()`
(`app/intelligence/temporal.py`), completely unchanged.
`retrospective_vs_point_in_time_note`, included on every report, states
the distinction explicitly: **retrospective** analysis ("what actually
happened historically?") can see every accepted canonical event
regardless of when it was ingested; **point-in-time** intelligence
("what was knowable as of a particular moment?") uses the strict
`ingestion_time <= as_of` filter and will, correctly, exclude backfilled
history from any `as_of` before it was actually ingested. This harness
never weakens that filter to make a backfilled dataset look more
complete — see `docs/CALIBRATION_METHODOLOGY.md` §5 for the full
bulk-backfill finding this reconfirms.

**A subtlety worth calling out explicitly**: `run_enterprise_dataset_validation()`'s
`as_of` parameter defaults to a value captured *after* ingestion
completes, precisely so live "readiness right now" checks aren't
accidentally starved of the data that was just ingested. Passing an
explicit, genuinely earlier `as_of` is still fully supported — it is a
legitimate retrospective/point-in-time query — but it will correctly
show reduced or zero visibility; that is the intended result, not a bug.

## 9. How intelligence readiness is evaluated

`IntelligenceReadinessReport` runs the real, unmodified
`compute_summary()`/`compute_trend()`/`risk_signal_service.detect_all()`/
`detect_anomaly()` and reports exactly what they say: data sufficiency,
event count, per-metric trend direction, which risk signals fired, and
the anomaly status (including a plain `INSUFFICIENT_DATA` when the
baseline period count doesn't support a determination). **No threshold
is ever adjusted to make a dataset look better** — a poor or unexpected
result is reported, with the underlying counts, and left exactly as
computed (item 6's own instruction).

## 10. How predictive dataset readiness is evaluated

`PredictiveReadinessReport` reports, per organization: eligible/excluded
sites and why, historical time coverage per site, qualifying incidents,
positive/negative/**unavailable** labels, missing feature values,
incomplete feature windows, and class distribution (only once at least
one label is actually confirmed). A label is `UNAVAILABLE`, never
coerced to a negative, whenever its prediction horizon (30 days by
default, `app/predictions/spec.py::HORIZON_DAYS`, unchanged) has not yet
fully elapsed as of real "now" — absence of a qualifying event so far is
not evidence none will occur before the window closes. **This measures
whether a dataset is ready for a future train/validation/test
experiment. It never claims predictive accuracy, PR-AUC, ROC-AUC,
precision, recall, or calibration performance** — those require an
actual historical experiment this milestone deliberately does not run.

## 11. What SIE can and cannot conclude from incomplete data

Never conclude that a missing value means an event or risk did not
happen — a `QUARANTINED` record, an `UNAVAILABLE` predictive label, a
`None` feature value, and an excluded site are all reported as exactly
that: information this dataset does not (yet) support a conclusion
about, not a negative finding. `app/validation/report.py`'s own
`## UNAVAILABLE` section exists specifically to keep this distinction
visible in every report this harness produces.

## 12. Synthetic validation vs. real enterprise validation

**Everything in `tests/fixtures/messy_enterprise_dataset.py` is
synthetic, fabricated data — never real customer or enterprise data.**
Every report this harness produces against it carries
`SYNTHETIC_VALIDATION_LABEL` (or an equally explicit caller-supplied
label), restated at the top of every generated report. **Passing this
harness's own test suite against the synthetic fixture does not
constitute validation against real customer data** — it proves the
harness itself, and the pipeline it exercises, behave correctly on
data *shaped like* a real organization's messy history. When a real,
anonymized enterprise dataset is supplied in a future step, the same
harness runs against it unchanged — only the `payloads` and an equally
explicit, non-synthetic `label` (e.g. `"Real, anonymized dataset
supplied by <engagement>, evaluated <date>"`) differ. Until that
happens, every conclusion in this repository about "real enterprise
data" is scoped to this synthetic fixture only.

## How to run the harness

```bash
cd backend
# Requires real PostgreSQL + pgvector -- see tests/postgres_support.py.
.venv/bin/python -m pytest tests/test_enterprise_dataset_validation.py -q
```

Or programmatically:

```python
from app.validation.enterprise_dataset_validation import (
    run_enterprise_dataset_validation, queue_review_candidates,
)
from app.validation.report import to_markdown, to_json

report = run_enterprise_dataset_validation(
    db, organization_id=org_id, payloads=my_payloads,
    label="Real, anonymized dataset supplied by <engagement>, evaluated <date>",
)
print(to_markdown(report))
queue_review_candidates(db, organization_id=org_id, report=report)  # optional
```

## Security / data handling (item 13)

* No confidential enterprise data is committed to this repository — the
  only dataset this repository ships is the synthetic fixture above.
* `HseExpertReview.provenance` stores a small, structured snapshot
  (batch id, source record id, content hash, mapping reason, signal
  type) — never a raw payload dump. The one exception, unchanged from
  Milestone 1, is `EnterpriseIngestionRecord.payload`, which already
  only stores the one outcome (`REJECTED_INVALID`) with no canonical
  event to hold it — this milestone does not change that behavior.
* Every read/write in `app/validation/` and
  `app/services/hse_review_service.py` is tenant-scoped by
  `organization_id`, using the exact same rule every other resource in
  this codebase already follows — no new cross-tenant surface is
  introduced.
* `HseExpertReview` is an **evaluation mechanism only** — no code path
  in this codebase reads `outcome` and changes ingestion, mapping, or
  intelligence behavior; see that model's own docstring.

## Non-goals (item 14, unchanged)

No production ML training, no model retraining, no autonomous agents,
no LLM-based classification, no automated safety decisions, no automated
intervention recommendations, no Kafka, no Redis, no production event
streaming, no unnecessary background workers, no Safelytic-specific
coupling, no customer-specific hard-coded mappings, no production
deployment infrastructure.
