# Enterprise Intelligence & Risk Analytics

**SIE Milestone 22: Enterprise Intelligence & Risk Analytics Foundation
v0.1.**

## Purpose

This milestone converts SIE's existing normalized enterprise safety data
(`SafetyEvent`), temporal features, indicators, risk signals, predictive
interfaces, ontology, and provenance foundations into a coherent
enterprise intelligence layer that can answer, for one organization or
one site, as of a chosen moment: **what is happening, what is changing,
where is risk concentrated, what patterns are recurring, and what
evidence supports those conclusions.**

It is deliberately **not** a redesign of retrieval, RAG, the predictive
model, or the existing `GET /api/v1/intelligence/analytics/*` endpoints —
every one of those stays exactly as it was. This milestone adds one new,
additive computation on top of the same primitives
(`app/intelligence/temporal.py::events_as_of()`/`window_bounds()`) those
endpoints already use.

**The deterministic risk score this milestone produces is an analytical
prioritization mechanism. It is not a validated probability of an
incident occurring.** See "What the score does not mean" at the end of
this document — this distinction is load-bearing throughout.

## Architecture

```
Safety Events
    -> point-in-time filtering        (app/intelligence/temporal.py::events_as_of() -- reused, unchanged)
    -> aggregation                    (current window + immediately preceding equal-length window)
    -> indicators                     (app/intelligence/enterprise_indicators.py)
    -> trend analysis                 (app/intelligence/enterprise_trend.py)
    -> pattern / recurrence analysis  (app/intelligence/recurrence.py)
    -> risk concentration             (app/intelligence/concentration.py)
    -> deterministic risk scoring     (app/intelligence/risk_score.py)
    -> explanation + provenance       (app/intelligence/explanations.py)
    -> Enterprise Intelligence API    (app/api/v1/intelligence.py)
```

`app/intelligence/enterprise_intelligence_service.py::compute_enterprise_intelligence()`
is the one orchestrator that touches the database — every sibling module
above is a **pure function** over an already-fetched, already-point-in-
time-correct, tenant-scoped `SafetyEvent` list. This mirrors
`app/intelligence/features.py`'s own `compute_feature_set()` /
`FeatureEngineeringService` split exactly: the only place a temporal-
leakage or tenant-isolation bug could be introduced is the query
construction in the orchestrator, not scattered across five
independently un-auditable modules.

**Query strategy (avoiding N+1).** Exactly four-to-five queries per
request, regardless of how many indicators/patterns/contributors are
computed: current-window events, previous-window events, one
organization-wide site id→name lookup, one actions lookup, and (site
scope only) one latest-prediction lookup. Every downstream computation
is a pure function over these already-fetched lists.

## Intelligence scope

Two levels, per milestone item 2:

* **organization** — `GET /api/v1/intelligence/enterprise`
* **site** — `GET /api/v1/intelligence/sites/{site_id}`

Project-level intelligence was considered and deliberately **not**
added: `SafetyEvent.project` is a free-text operational-context field
(see `app/models/safety_event.py`'s own docstring), not a governed
entity with its own id/organization scoping the way `Site` is — adding a
third intelligence level on top of free text would invent structure the
canonical data model does not actually have.

## Point-in-time semantics

Unchanged, reused directly: `events_as_of()` filters every query on both
`event_time <= as_of` **and** `ingestion_time <= as_of` — an event that
occurred before `as_of` but was only ingested afterward (a backdated
report) is excluded, exactly as it already is for every other
`app/intelligence/*.py` computation. See
`tests/test_enterprise_intelligence_service.py`'s point-in-time tests for
the exact assertion (an event ingested one day after `as_of`, despite
having occurred five days before it, contributes `0` to every
indicator).

**Actions (SIE Milestone 22A item 3).** `_actions_context()` applies the
same discipline to `SafetyAction`: `created_at <= as_of` excludes any
action that did not yet exist as of the requested `as_of` from every one
of `actions_context`'s three counts — a historical
`GET .../enterprise?as_of=<a past date>` call must never surface an
action created afterward. See "Actions integration" below for
`overdue_action_count`'s own additional correction.

## Analysis windows

`settings.ENTERPRISE_INTELLIGENCE_ALLOWED_WINDOW_DAYS` (default `[7, 30,
90, 180]`) is the closed set `window_days` must be one of — a request
with any other value is a `400`, not silently rounded or ignored.
`settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS` (`30`) is used
when the caller omits `window_days`.

**Boundary semantics.** For `as_of=T` and `window_days=N`:

```
current window:  (T - N days, T]
previous window: (T - 2N days, T - N days]
```

Both computed by calling `window_bounds()` twice (`window_bounds(T, N)`
then `window_bounds(window_start, N)`) — the same function, never a
second, independently-hand-written boundary calculation. The previous
window is fetched via `events_as_of(as_of=window_start, ...)`, mirroring
`app/intelligence/temporal.py::bucketed_counts()`'s own established
convention: an event that happened in the previous period but was only
ingested *after* the previous period ended (and before `T`) would not
have been knowable "as of the previous period's own end" either, so it
is correctly excluded from the previous-period baseline too — the
stricter, already-established interpretation of point-in-time
correctness this codebase uses everywhere, not a new rule invented for
this milestone.

**The two windows are strictly non-overlapping (corrected in Milestone
22A).** `events_as_of()`'s own `window_start` filter is `>=` — shared,
unchanged, and relied on by every other caller in this codebase — so an
event landing exactly on the shared boundary (`event_time == T - N
days`) would satisfy both the current window's `>= window_start` and
the previous window's `<= window_start` if each were fetched with no
further adjustment. `compute_enterprise_intelligence()` applies one
additional, scoped filter after fetching the current window's events
(`event_time > window_start`) to exclude that shared instant from the
current period; the previous period's own inclusive upper bound
(`event_time <= window_start`) is its single source of truth. This is a
filter local to this one current/previous comparison — `events_as_of()`
itself is never modified. See
`tests/test_enterprise_intelligence_service.py`'s exact-boundary test
for the assertion.

## Indicators

`app/intelligence/enterprise_indicators.py`. Every indicator is a plain
count over canonical `SafetyEvent` fields (`event_type`, `event_subtype`,
`severity`, `status`) — never a fabricated metric. `event_subtype`
matching is a case-insensitive substring check against the
already-observed subtype vocabulary this codebase's own fixtures and
ingestion adapters actually produce (`VEHICLE_INCIDENT`,
`PROPERTY_DAMAGE`, `FIRST_AID_CASE`/injury, `COMPLIANCE_FINDING`, unsafe
observations) — the same pattern
`app/intelligence/signals.py::is_unsafe_observation()` already
establishes. **"Fires" (the milestone's own example list) is
deliberately not included** — nothing in this codebase's existing
event-subtype vocabulary genuinely represents it, and fabricating an
indicator with no underlying data is exactly what the milestone
prohibits.

| Category | Key | What it counts |
|---|---|---|
| LAGGING | `incident_count` | All `INCIDENT` events |
| LAGGING | `vehicle_incident_count` | `INCIDENT` with subtype containing "vehicle" |
| LAGGING | `property_damage_event_count` | `INCIDENT` with subtype containing "property_damage" |
| LAGGING | `injury_event_count` | `INCIDENT` with subtype containing "injury" or "first_aid" |
| LAGGING | `severity_low/medium/high/critical_count` | `INCIDENT`+`NEAR_MISS` by severity band (same pool `features.py::avg_severity` uses) |
| LEADING | `near_miss_count` | All `NEAR_MISS` events |
| LEADING | `observation_count` | All `OBSERVATION` events |
| LEADING | `unsafe_observation_count` | `OBSERVATION` with subtype containing "unsafe" |
| LEADING | `inspection_count` | All `INSPECTION` events |
| LEADING | `audit_finding_count` | `AUDIT` with subtype containing "finding" |
| LEADING | `overdue_action_count` | `CORRECTIVE_ACTION` events with `status=OVERDUE` |

Each indicator carries `key`/`label`/`value`/`category` (this
indicator's milestone-item-5 "classification")/`period_start`/
`period_end`/`window_days`, plus `previous_value`/`absolute_change`/
`percentage_change`/`trend_direction`. **A count is always a determinate
integer, never `None`** — zero is a real, meaningful answer. Only
`percentage_change` can be undefined (division by a zero previous-period
count): reported explicitly as `value=None`,
`unavailable_reason="PREVIOUS_PERIOD_ZERO"`, never as a misleading `0%`
or `inf%`. `trend_direction` (`INCREASING`/`DECREASING`/`STABLE`) is a
plain, threshold-free comparison of the two raw counts — purely
descriptive, distinct from the risk-relevant, threshold-gated
classification the next section describes.

## Trend methodology

`app/intelligence/enterprise_trend.py`. Distinct from the pre-existing
`app/intelligence/trends.py` (a multi-period least-squares regression,
still used unchanged by `GET .../analytics/trends`) — this is a simpler,
two-point, **semantic** (good/bad, not merely directional) comparison the
milestone spec itself asks for.

**Primary metric:** total `INCIDENT` count — the one lagging indicator
every organization/site in this codebase can report, regardless of which
of the eleven data domains it actually uses.

**Deterministic rule:**

1. `current_value + previous_value < settings.ENTERPRISE_TREND_MIN_COMBINED_EVENTS`
   (default `5`) → `INSUFFICIENT_DATA`. Never build a trend claim on a
   handful of events.
2. Otherwise:
   * `previous_value == 0`: a ratio is undefined. `DETERIORATING` if
     `current_value > 0`; `STABLE` if both are `0`.
   * `previous_value > 0`: `percentage_change = (current - previous) /
     previous`. `>= settings.ENTERPRISE_TREND_CHANGE_THRESHOLD` (default
     `20%`) → `DETERIORATING`; `<= -threshold` → `IMPROVING`; otherwise
     `STABLE`.

**No causal claim, ever.** "Incident count changed from 2 to 5" is
reported; "poor supervision caused the increase" is a sentence this
module has no vocabulary to produce (mirrors
`app/intelligence/association.py`'s own hard causal boundary).

## Recurrence methodology

`app/intelligence/recurrence.py`. A deterministic count-and-bucket
detector — no clustering, no ML (explicitly out of scope). Two pattern
shapes, both requiring a known `site_id`:

* `(site, event_type)`
* `(site, event_subtype)` — only when `event_subtype` is present

**Population:** `INCIDENT` and `NEAR_MISS` events only — recurrence
detection is about *adverse* signal repeating, not routine activity
(e.g. "3 audits this quarter" is not a risk pattern).

**Classification thresholds** (`settings.ENTERPRISE_RECURRENCE_*`,
documented initial defaults):

```
count == 1                     -> NONE            (not a pattern -- never returned)
count >= WATCH_MIN (2)          -> WATCH
count >= RECURRING_MIN (3)      -> RECURRING
count >= HIGH_MIN (5)           -> HIGH_RECURRENCE
```

Separate sites never combine — `site_id` is part of every pattern key by
construction. `supporting_event_ids` is bounded to 20 entries; `count`
is always the real, unbounded total.

## Concentration analysis

`app/intelligence/concentration.py`. Four dimensions, each a ranked list
of `(key, count, total, percentage, classification)`:

* **`site`** (organization scope only) — share of `INCIDENT` events per
  site.
* **`event_subtype`** — share of `INCIDENT` events per subtype.
* **`severity`** — share of the same severity pool (`INCIDENT` +
  `NEAR_MISS`) `features.py` uses, per severity band.
* **`event_type`** — share of *all* recorded activity (any of the eleven
  domains) per event type — a data-composition signal distinct in kind
  from the other three.

**Minimum-data safeguard.** A dimension is only ranked once its total
population reaches `settings.ENTERPRISE_CONCENTRATION_MIN_POPULATION`
(default `5`) — a "100% concentration" computed from one or two events
is never presented as statistically meaningful; the dimension is simply
omitted below that floor. Above it, a contributor's share is banded:
`< 20%` → `LOW`, `20-49%` → `MODERATE`, `>= 50%` → `HIGH`
(`settings.ENTERPRISE_CONCENTRATION_MODERATE_THRESHOLD`/
`_HIGH_THRESHOLD`).

## Risk formula

`app/intelligence/risk_score.py`, version `enterprise-risk-v1`. A
**transparent, rule-based prioritization score, not a black-box ML
model.** Every input is a count or classification already computed by a
sibling module; every weight/reference constant below is a plain
module-level constant in that file, inspectable by reading it, never
learned from data.

**Five documented components**, each independently bounded to `[0, 100]`
before weighting:

| Component | Weight | How it's scored |
|---|---|---|
| `incident_severity` | 30 | `min((severity_high + severity_critical) / 5, 1.0) * 100` |
| `incident_frequency` | 25 | `min(incident_count / 10, 1.0) * 100` |
| `deteriorating_trend` | 20 | `STABLE` → `0`; `DETERIORATING` → `50 + clamp(pct, 0, 100)/2` (60-100); `IMPROVING` → `max(0, 50 + clamp(pct, -100, 0)/2)` (0-40); undefined-ratio `DETERIORATING` (previous period was zero) → fixed `75` |
| `recurring_patterns` | 15 | `min(sum(points per pattern), 100)` — `WATCH`=10, `RECURRING`=25, `HIGH_RECURRENCE`=50 points each |
| `leading_lagging_imbalance` | 10 | `min((incidents / (leading_activity + 1)) * 50, 100)` |

The reference counts (`5`, `10`), points-per-pattern, and the `50`
imbalance scale are documented *provisional* defaults — the same
standing "not scientifically validated" caveat every other threshold in
this codebase carries (see `app/intelligence/sufficiency.py`,
`trends.py`, `signals.py` for the precedent).

**A component that cannot be computed is omitted, not fabricated as a
neutral value.** `deteriorating_trend` is omitted when the trend itself
is `INSUFFICIENT_DATA`; `leading_lagging_imbalance` is omitted only when
*both* lagging and leading activity are genuinely zero (nothing to form
a ratio from at all). The remaining, genuinely-computed components'
documented weights are re-normalized to still sum to 100, so the final
score always stays on the same `[0, 100]` scale regardless of how many
components were computable.

**Why `STABLE` contributes `0`, not a "neutral" `50`.** An earlier
design centered the trend component at `50` for "no signal" — but that
meant a window with zero incidents in both periods still contributed
~11 points toward the final score purely from "nothing changed," which
is not a real risk signal. `STABLE` now contributes `0`; only a
genuinely `DETERIORATING` trend adds points.

**The overall gate.** No score is computed at all
(`score=None`, `classification=None`) when the window's total event
count is below `settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS` (reused
from `app/intelligence/sufficiency.py`, not duplicated) — "one event
technically permits an arithmetic result" is exactly the case this gate
refuses.

## Classifications

**Risk score bands** (fixed, milestone item 10):

```
0-24    LOW
25-49   MODERATE
50-74   HIGH
75-100  CRITICAL
```

**Concentration bands:** `< 20%` LOW, `20-49%` MODERATE, `>= 50%` HIGH —
a deliberately distinct vocabulary from the risk-score bands above, so a
"35% site concentration" reading is never confused with, or numerically
compared against, the unrelated 0-100 risk score.

**Recurrence bands:** `NONE`/`WATCH`/`RECURRING`/`HIGH_RECURRENCE` — see
"Recurrence methodology" above.

**Trend bands:** `IMPROVING`/`STABLE`/`DETERIORATING`/`INSUFFICIENT_DATA`
— see "Trend methodology" above.

## Sufficiency thresholds

| Threshold | Setting | Default | Governs |
|---|---|---|---|
| Trend minimum combined events | `ENTERPRISE_TREND_MIN_COMBINED_EVENTS` | 5 | Trend classification vs. `INSUFFICIENT_DATA` |
| Recurrence WATCH/RECURRING/HIGH minimums | `ENTERPRISE_RECURRENCE_*_MIN` | 2 / 3 / 5 | Pattern classification |
| Concentration minimum population | `ENTERPRISE_CONCENTRATION_MIN_POPULATION` | 5 | Whether a dimension is ranked at all |
| Risk score minimum event count | `INTELLIGENCE_LIMITED_DATA_MIN_EVENTS` (reused) | 3 | Whether a score is computed at all |
| Data sufficiency status | `INTELLIGENCE_SUFFICIENT_DATA_MIN_EVENTS` / `INTELLIGENCE_LIMITED_DATA_MIN_EVENTS` (reused) | 10 / 3 | `data_sufficiency.status`: `SUFFICIENT_DATA` / `LIMITED_DATA` / `INSUFFICIENT_DATA` |

## Explanation layer

`app/intelligence/explanations.py`. **Not LLM-generated narrative** —
every `ExplanationItem` is produced by substituting already-computed
numbers into a fixed Python string template. Each item's
`evidence_reference` points back to the exact computed object (a
risk-score component key, `trend:incident_count`, a recurrence
`pattern_key`, a `dimension:key` concentration pair) that produced it.
Order: risk-score component drivers first (each maps 1:1 to a component
that actually contributed points), then the trend explanation, then
recurrence patterns, then notable (`MODERATE`/`HIGH`) concentration
contributors.

## Provenance

Every result's `provenance` object carries: `organization_id`, `scope`,
`entity_id`, `as_of`, `window_start`/`window_end`/`window_days`,
`generated_at`, `event_count`, a bounded `evidence_sample_event_ids`
(≤25) plus the real `total_supporting_events`, and
`calculation_versions` (one version string per sub-computation:
indicators, trend, recurrence, concentration, risk score). Tenant
isolation is structural, not a separate check: every event id anywhere
in the response comes from `events_as_of(organization_id=...)`, which
never returns another organization's rows.

## Predictive integration

`predictive_context` (site scope only — `Prediction.entity_type` is
`"site"` for the entire predictive-model milestone, never fabricated for
organization scope) is populated **only from an already-recorded**
`Prediction` row — this endpoint never triggers a new prediction, never
retrains. `deterministic_risk` (this milestone's own score) and
`predictive_risk` (`predictive_context.risk_score`/`.probability`, the
ML model's own calibrated output) are always two separate,
separately-labeled fields — never combined into one opaque number.

## Actions integration

`actions_context` reports purely factual counts from `SafetyAction`,
all point-in-time filtered by `created_at <= as_of` (see "Point-in-time
semantics" above): `open_action_count` (current `status == OPEN`),
`overdue_action_count` (past its `due_date`, not yet closed as of
`as_of`), `high_priority_action_count` (current status not terminal,
`HIGH`/`CRITICAL` priority). Never a claim like "these actions will
reduce risk by X%"; this endpoint creates no action of its own.

**`overdue_action_count`'s "not yet closed" check (corrected in
Milestone 22A item 5).** The original implementation checked the
action's *current* `status` column to decide whether it was still open
— wrong for a historical `as_of`, because `status` only ever holds the
action's state right now and has no memory of what it was at any
earlier point in time. An action that is *currently* `COMPLETED` but was
only completed a week after the requested `as_of` was genuinely still
overdue as of that historical moment, and the original check silently
excluded it. The fix (`_terminal_as_of()` in
`app/intelligence/enterprise_intelligence_service.py`) instead compares
`as_of` against the action's own `completed_at`/`cancelled_at`
transition timestamp — each set exactly once, at the moment of that
specific transition (see `app/models/safety_action.py`'s own "Closure
semantics" docstring) — so "was this action still open as of `as_of`"
is answered correctly using only fields already on the row.
`open_action_count`/`high_priority_action_count` were not found to have
this same defect (their definitions never depended on comparing a date
against `as_of`) and keep their original "current `status`" meaning,
now also point-in-time filtered by `created_at`. Full historical-status
reconstruction via `SafetyActionHistory` replay was considered and
deliberately not built — that would be a genuine redesign of this
computation, not the focused correction this milestone is; it remains
available future work if a stricter guarantee is ever needed for
`open_action_count`/`high_priority_action_count` too. See
`tests/test_enterprise_intelligence_service.py`'s
`test_overdue_action_count_uses_completed_at_not_current_status` for the
exact regression this closes.

## API

```
GET /api/v1/intelligence/enterprise?organization_id=...&as_of=...&window_days=...
GET /api/v1/intelligence/sites/{site_id}?organization_id=...&as_of=...&window_days=...
```

Reuses `Permission.INTELLIGENCE_READ` (no new permission — a genuine fit
already existed). `organization_id` is the same authorize-then-trust
query parameter every other endpoint in this router already uses (see
`app/api/deps_context.py`) — never overridable beyond what
`require_context_permission()` authorized. The site endpoint 404s (never
403s) for a nonexistent or cross-tenant site, mirroring
`app/api/v1/predictions.py`'s own established pattern. An unsupported
`window_days` is a `400`; a malformed `as_of` is FastAPI's own `422`.
Both responses now also carry an `anomalies` array (Milestone 23 — see
"Anomaly detection methodology" above) — an additive field on the same
existing endpoints, never a new endpoint. Milestone 24 adds one more:
`associations` (see "Pattern & association methodology" below) —
again additive, again the same two endpoints, no new API surface.

## Anomaly detection methodology

**SIE Milestone 23: Enterprise Intelligence Explainability & Anomaly
Foundation v0.1.** Extends the "what happened / how much / is the trend
improving / what is the deterministic risk level" chain above with two
more questions:

```
What happened?  -> What is changing?  -> What is unusual?  -> How unusual is it?  -> What evidence produced that conclusion?
(indicators)       (trend)               (this section)       (z-score)              (bounded supporting_event_ids)
```

An anomaly answers *is this statistically unusual relative to this
entity's own recent history* — nothing more. It is a separate,
additive `anomalies` array on the existing enterprise/site responses
(item 13), never a new endpoint and never folded into the deterministic
risk score (see "Relationship with the risk score" below).

**Reuses the existing anomaly foundation, does not replace it.** Every
anomaly here is produced by `app/intelligence/anomaly.py::detect_anomaly()`
— the same z-score-against-baseline function already used by
`app/predictions/feature_snapshot_service.py` and
`app/validation/enterprise_dataset_validation.py`. This milestone extends
that function additively (a new `direction` field, described below);
there is no second, competing anomaly-scoring implementation anywhere in
this codebase.

**Supported metrics — a closed, genuinely-supported vocabulary (item
1).** Exactly seven: `incident_count`, `near_miss_count`,
`observation_count`, `unsafe_observation_count`,
`vehicle_incident_count`, `injury_event_count`,
`property_damage_event_count`. Each reuses the identical
event-type/subtype predicates Milestone 22's own indicators already use
(`app/intelligence/enterprise_indicators.py`'s `_vehicle`/`_injury`/
`_property_damage`, `app/intelligence/signals.py`'s
`is_unsafe_observation`) — no metric here is manufactured; every one has
a genuine underlying data representation already relied on elsewhere in
this codebase.

**Baseline methodology.** The baseline for a metric is the sequence of
per-period counts for that same metric over the most recent complete
`window_days`-length periods immediately preceding the current window —
the identical bucketing primitive (`app/intelligence/temporal.py::
bucketed_counts()`) `app/intelligence/signals.py` already uses for its
own baseline comparisons, which itself delegates every bucket's query to
`events_as_of()`. Baseline depth is data-driven, not assumed: before
scanning any metric, one shared query (not one per metric) finds this
organization's (or site's) own earliest point-in-time-correct event and
derives how many complete periods actually precede the current window,
capped at `settings.ENTERPRISE_ANOMALY_BASELINE_PERIODS_MAX` (default
`6`) — "recent history", not "the organization's entire history".

**Point-in-time integrity (item 3).** Every event contributing to a
current value, a baseline count, or a supporting-evidence id satisfies
`event_time <= as_of AND ingestion_time <= as_of`, inherited entirely
from `events_as_of()` — no second, hand-written temporal filter exists
in the anomaly module. The current period's counts come from
`current_events`, the same already-fetched, already point-in-time- and
Milestone-22A-boundary-corrected event list the orchestrator builds for
indicators/trend, so the current-period side of every metric costs zero
additional queries. Baseline buckets end exactly at `window_start`
(mirroring `app/intelligence/signals.py::_baseline_bucket_counts()`'s
own established convention), so the shared boundary instant belongs to
the baseline's own last bucket only, never double-counted against the
current period.

**Z-score methodology.** For a metric's current value `x` and baseline
values `[b_1, ..., b_n]`:

```
mean  = fmean(baseline values)
stdev = population standard deviation of baseline values
z     = (x - mean) / stdev
|z| >= threshold -> ANOMALOUS, else NORMAL
```

Population (not sample) standard deviation is used deliberately — the
baseline periods are treated as the entire relevant population of recent
history, not a sample drawn from a larger one.

**Minimum baseline (item 7).** Fewer than
`settings.INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS` (default `4`)
available baseline periods (reused unchanged from the pre-existing
anomaly foundation) makes every metric `INSUFFICIENT_DATA` immediately —
`bucketed_counts()` is never even called in that case, so this costs no
extra queries either. One metric being `INSUFFICIENT_DATA` never
invalidates any other metric's own result; each of the seven metrics is
evaluated and reported independently.

**Zero-standard-deviation behavior.** A perfectly constant baseline
(`stdev == 0`) never divides by zero: `z_score` is reported as `None`
(undefined — never fabricated as `0` or `∞`), and the classification is
decided directly — `ANOMALOUS` if the current value differs at all from
that constant baseline, `NORMAL` if it exactly matches it. `direction`
is still computed in this case (see below).

**Anomaly threshold.** `settings.INTELLIGENCE_ANOMALY_Z_SCORE_THRESHOLD`
(default `2.0`, reused unchanged from the pre-existing anomaly
foundation) — `|z| >= 2.0` is `ANOMALOUS`. Both this threshold and the
minimum-baseline setting above are versioned, explicit settings-module
values, never scattered magic numbers, and are exercised at their exact
boundary by `tests/test_intelligence_anomaly.py`'s threshold-boundary
tests (`z = 1.95` NORMAL, `z = 2.0` and `z = 2.05` ANOMALOUS, and the
symmetric negative-`z` cases).

**Direction (item 5).** `AnomalyDirection` —
`ABOVE_BASELINE`/`BELOW_BASELINE`/`NONE` — is a vocabulary deliberately
kept separate from `AnomalyStatus` (`NORMAL`/`ANOMALOUS`/
`INSUFFICIENT_DATA`, reused unchanged): "unusually high" and "unusually
low" are both `ANOMALOUS`, but operationally very different findings, so
they are never collapsed into one undifferentiated signal. `direction`
answers "which way" and is reported whenever the current value differs
from the baseline mean at all — independent of whether that difference
clears the anomaly threshold (a value slightly above the mean is still
meaningfully `ABOVE_BASELINE` even while classified `NORMAL`). An
increase is never automatically treated as "bad" by this module — it has
no severity vocabulary at all, only direction and magnitude.

**Evidence (item 9).** Each anomalous metric's result carries: the
current period's value and window, the baseline periods' start/end and
count, `baseline_mean`/`baseline_stdev`/`z_score`, `direction`, the exact
`supporting_event_count` for the current period, and a bounded (≤20)
sample of `supporting_event_ids` drawn only from the already tenant-
scoped `current_events` list. This is factual evidence only — *what* is
unusual and *how* unusual — never a causal claim. Permitted: "Incident
count was 8 this period versus a historical baseline mean of 2.4."
Never produced by this module: "poor supervision caused the spike" —
there is no vocabulary here capable of generating the latter (mirrors
`app/intelligence/association.py`'s own hard causal boundary).

**Explanation service (item 10).** `app/intelligence/explanations.py::
_anomaly_explanations()` generates one deterministic `ExplanationItem`
per `ANOMALOUS` metric — the same "substitute already-computed numbers
into a fixed string template" mechanism the rest of this document's
explanation layer already uses (see "Explanation layer" above). No LLM,
no free-form prose, nothing generated beyond string substitution of
already-computed values; `evidence_reference` is `anomaly:<metric>` for
every item, tracing straight back to that metric's own `EnterpriseAnomalyResult`.

**Relationship with the risk score (item 11).** `enterprise-risk-v1`
(`app/intelligence/risk_score.py`) is **not modified by this milestone at
all** — anomaly findings are exposed as a wholly separate dimension
(`deterministic_risk` / `anomalies` / `predictive_context` all stay
distinct fields on the same response), and no anomaly ever contributes
points to the risk score. **Anomaly ≠ Risk**: an anomalous metric is a
statistically unusual pattern, not automatically a dangerous one (an
unusually *high* observation count, for instance, is often a leading-
indicator success story, not a hazard) — see "What an anomaly does not
mean" below.

**Organization and site scope (item 12).** Identical scope architecture
to Milestone 22's own indicators/trend/recurrence/concentration: a site
scan is verified to belong to the requesting organization before any
query runs (404, never a raw lookup, for a foreign or nonexistent site),
and every event id anywhere in an anomaly result comes from the same
tenant-scoped `events_as_of()` call already used for the rest of the
response — no cross-tenant aggregation is possible.

**Performance (item 16).** A naive implementation would issue N metrics
× N baseline periods × N queries. This module instead issues at most
one shared baseline-depth query plus one `bucketed_counts()` call per
metric (skipped entirely for every metric when baseline depth is
insufficient) — reusing the existing bucketing/period infrastructure
rather than a new one, and reusing `current_events` for the entire
current-period side at zero additional queries. No Redis, no background
workers, no new caching layer.

**Configuration.** All three thresholds live in `app/core/config.py`,
none scattered as inline magic numbers:

| Setting | Default | Governs |
|---|---|---|
| `INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS` (reused) | 4 | Minimum baseline periods before a metric can be scored at all |
| `INTELLIGENCE_ANOMALY_Z_SCORE_THRESHOLD` (reused) | 2.0 | `|z|` threshold for `ANOMALOUS` |
| `ENTERPRISE_ANOMALY_BASELINE_PERIODS_MAX` (new) | 6 | Upper bound on how many recent periods are used as baseline |

**What an anomaly does not mean.** An anomaly identifies statistical
unusualness relative to the defined baseline. It does not establish
causation, severity, probability of an incident, or operational root
cause.

## Pattern & association methodology

**SIE Milestone 24: Enterprise Intelligence Pattern & Correlation
Foundation v0.1.** Extends the chain once more:

```
What happened?  ->  What is changing?  ->  What is unusual?  ->  How unusual is it?
    ->  What patterns repeatedly occur?  ->  What safety dimensions appear associated?
        ->  What evidence supports that observation?
```

Two distinct, separate findings — never combined into one score, and
neither ever folded into `enterprise-risk-v1` (see "Relationship with
the risk score" below, mirroring Milestone 23's identical rule for
anomalies).

### Pattern methodology

**Built entirely on the pre-existing recurrence infrastructure — nothing
new was written for pattern detection itself (item 1's own instruction:
"use the existing recurrence infrastructure as the foundation rather
than replacing it").** `app/intelligence/recurrence.py`
(see "Recurrence methodology" above) already detects exactly two of this
milestone's named pattern shapes — `(site, event_type)` and `(site,
event_subtype)` — and each `RecurrencePattern` is, by construction,
already "a repeated event category within a defined period" (item 1's
third example): every pattern carries `window_start`/`window_end`/
`window_days` alongside its `count`. The `patterns` array on both
endpoints (already present since Milestone 22) *is* this milestone's
pattern-detection deliverable; Milestone 24 adds no second, competing
implementation.

**Recurrence definition & temporal rules — unchanged from Milestone
22/22A.** A pattern is `count >= 2` occurrences of the same `(site,
event_type)` or `(site, event_subtype)` combination within the current
window; every contributing event already satisfies `events_as_of()`'s
`event_time <= as_of AND ingestion_time <= as_of` guarantee and the
Milestone 22A non-overlapping current/previous window-boundary rule,
because `detect_recurrence()` is a pure function over the same
already-fetched, already-corrected `current_events` list every other
sibling computation in this document uses — see "Point-in-time
semantics" above.

**Pattern evidence.** `occurrence count` (`count`), `first occurrence`
(`first_seen`), `last occurrence` (`last_seen`), and `period coverage`
(the window itself, `window_start`/`window_end`/`window_days`) are all
already exposed on every `RecurrencePattern` — enough structured
information for a caller to tell "8 times over 30 days" apart from "8
times on one day" without this codebase ever needing a separate,
opaque "pattern score" (item 3's own instruction): compare
`last_seen - first_seen` yourself. `supporting_event_ids` is bounded to
20 entries; `count` is always the real, unbounded total.

**One combination this milestone deliberately does not add: "event type
+ observation topic."** The ontology has no field distinct from
`event_subtype` that represents an "observation topic" (see
`app/models/safety_event.py`'s own documented, deliberately free-form
`event_subtype`) — and `recurrence.py`'s population is, by Milestone 22's
own explicit, tested design decision, restricted to `INCIDENT`/
`NEAR_MISS` only (adverse signal repeating, not routine activity;
`OBSERVATION` is excluded). Expanding that population to cover
`OBSERVATION` topics would be a genuine change to `recurrence.py`'s
existing, tested scope, not the "build on top of, don't replace" this
milestone's own item 1 calls for — documented here as a known,
deliberate limitation (see "Limitations" below), not silently glossed
over.

### Association methodology

**Reuses the existing association foundation.** `app/intelligence/
association.py`'s `detect_association()` (a Pearson correlation over two
aligned period series, pre-existing from an earlier milestone) is the
*only* correlation formula in this codebase — `app/intelligence/
enterprise_association.py` (new) calls it once per supported metric
pair, never reimplements it.

**Supported metrics — the identical, closed seven-metric vocabulary
anomaly detection already established (item 16):** `incident_count`,
`near_miss_count`, `observation_count`, `unsafe_observation_count`,
`vehicle_incident_count`, `injury_event_count`,
`property_damage_event_count`. Exactly `C(7, 2) = 21` unordered pairs,
always — a fixed constant, never scaling with event volume or
organization size, and never accepting an arbitrary caller-supplied
metric name (there is no `metric_a=<anything>` parameter anywhere in
this API).

**Aligned periods.** For each pair, both metrics' counts are read from
the *same* set of consecutive, non-overlapping `window_days`-length
periods ending at `as_of` — up to
`settings.ENTERPRISE_ASSOCIATION_MAX_PERIODS` (6) of them, computed
data-driven from this organization's (or site's) own earliest
point-in-time-correct event (built from `events_as_of()` itself, exactly
mirroring `app/intelligence/enterprise_anomaly.py::
_available_baseline_periods()`'s established pattern — see that
module's own docstring). Unlike the anomaly baseline (which deliberately
*excludes* the current window, since a baseline must stay independent of
the value being compared against it), association periods *include* the
most recent period ending at `as_of` — there is no separate "current
value" to keep apart from the series here; co-movement is about recent
history as a whole, current period included.

**Query strategy (item 15).** One shared earliest-event query, plus (only
when enough history exists) exactly one query *per period* — never one
per metric and never one per pair. Every one of the 21 pairs' two series
are derived from that same already-fetched, per-period event list in
memory (each metric's predicate applied in Python), and every pairwise
correlation is pure in-memory arithmetic afterward. No Redis, no
background workers, no distributed processing.

**Pearson correlation.** For aligned series `A`/`B` of length `n`:

```
r = Pearson correlation coefficient of A and B    (population statistics, statistics.correlation())
```

**Minimum periods.** `settings.ENTERPRISE_ASSOCIATION_MIN_PERIODS`
(default `4`, matching `INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS` for
consistency) — fewer aligned periods than this and every pair is reported
`INSUFFICIENT_DATA` immediately, with `period_count` reflecting the real
(possibly zero) count, never a fabricated correlation from two or three
observations (item 7).

**Classification thresholds (item 5).**
`settings.ENTERPRISE_ASSOCIATION_STRONG_THRESHOLD` (`0.7`) and
`settings.ENTERPRISE_ASSOCIATION_MODERATE_THRESHOLD` (`0.4`), documented
*initial* defaults:

```
r >= 0.7                    -> STRONG_POSITIVE
0.4 <= r < 0.7              -> MODERATE_POSITIVE
-0.4 < r < 0.4              -> WEAK
-0.7 < r <= -0.4            -> MODERATE_NEGATIVE
r <= -0.7                   -> STRONG_NEGATIVE
(insufficient periods /
 undefined correlation)     -> INSUFFICIENT_DATA
```

**Zero-variance behavior (item 6).** A constant series (every period has
the identical count) makes the Pearson correlation coefficient
mathematically undefined — `statistics.correlation()` raises, and this
codebase converts that directly into the explicit, governed
`INSUFFICIENT_DATA` state (`correlation_coefficient: null`), never a
fabricated `0`, `NaN`, or `Infinity` reaching an API consumer. The exact
same rule covers two identical series (perfectly, trivially correlated —
reported `STRONG_POSITIVE`, `r = 1.0`) and two exactly inverse series
(reported `STRONG_NEGATIVE`, `r = -1.0`) — both are well-defined,
non-constant cases, computed normally.

**Interpretation.** `r` measures *co-movement* over the aligned periods
above — nothing more. A `STRONG_POSITIVE` classification between two
metrics means they tended to rise and fall together across those
periods; it says nothing about which (if either) drove the other, and
nothing about a third, unmeasured factor driving both. See "Relationship
with the risk score" below and the "association vs. causation" statement
that closes this section.

### Relationship with the risk score (item 8)

`enterprise-risk-v1` (`app/intelligence/risk_score.py`) is **not modified
by this milestone at all** — associations are exposed as a wholly
separate dimension (`deterministic_risk` / `anomalies` / `patterns` /
`associations` / `predictive_context` all stay distinct fields on the
same response), and no association ever contributes points to the risk
score. **Association ≠ risk**, the same way anomaly ≠ risk: a strong
positive association between, say, unsafe observations and incidents is
a statistical observation about co-movement — often actually good news
(more leading-indicator reporting activity happening alongside incident
activity), never an automatic "+20" to the risk score.

### Evidence & provenance (items 9, 14)

Every association result exposes: `metric_a`/`metric_b` (and their human
labels), `classification`, `correlation_coefficient`, `period_count`,
the aligned `period_start`/`period_end`/`window_days` (so the periods are
fully reconstructable from the response alone), the underlying
`values_a`/`values_b` period series, `calculation_version`
(`"association-v1"`, also recorded in `provenance.calculation_versions`
as `"association"`), and a bounded (≤20), de-duplicated sample of
`supporting_event_ids` drawn only from events that satisfy either
metric's predicate in the aligned periods — factual only, no PII beyond
the event id itself.

### Deterministic explanation (item 10)

`app/intelligence/explanations.py::_association_explanations()` — the
same "substitute already-computed numbers into a fixed string template"
mechanism this document's explanation layer already uses for every other
finding (see "Explanation layer" above). Only non-`WEAK`,
non-`INSUFFICIENT_DATA` pairs get a sentence, e.g. *"Incident count and
near-miss count showed a strong positive association across 6 historical
periods (r=0.91)."* No LLM, no free-form prose, and never a causal claim
— *"near misses caused the increase in incidents"* is not a sentence this
function's vocabulary can produce.

**Association measures statistical co-movement between supported safety
metrics over aligned periods. It does not establish causation,
mechanism, probability, or root cause.**

## Limitations

* The default weights, reference counts, and thresholds throughout this
  document are documented *initial* defaults — not scientifically
  validated, not tuned against real incident-outcome data. Treat the
  risk score as a starting point for prioritization discussion, not a
  regulatory or safety-critical determination.
* Recurrence and concentration analysis operate on `INCIDENT`/`NEAR_MISS`
  events only — a real pattern expressed purely through, say, repeated
  `EQUIPMENT` failures at one site is not captured by this milestone's
  recurrence detector (though `equipment_failure_count`-style analysis
  already exists via `app/intelligence/signals.py`'s
  `EQUIPMENT_FAILURE_CLUSTER` signal, unchanged and untouched by this
  milestone).
* No ML clustering, no causal inference, no autonomous action creation —
  all explicitly out of scope for this milestone (see the completion
  report's "out-of-scope confirmation").
* Persistence: everything in this document is computed on demand from
  `SafetyEvent`/`SafetyAction`/`Prediction` rows already in the
  database — there is no snapshot table, no background recomputation, no
  cache. A large organization's `GET .../enterprise` call re-scans its
  own current+previous window events on every request; this is an
  accepted, documented tradeoff for v0.1 (see the completion report's
  "database changes" section) — background jobs, scheduled
  recomputation, and historical snapshot storage are explicitly future
  work, not silently implied by anything in this document.
* `open_action_count`/`high_priority_action_count` use each action's
  *current* `status`/`priority` (point-in-time filtered only by
  `created_at <= as_of`, not fully historically reconstructed) —
  unlike `overdue_action_count` (corrected in Milestone 22A, see
  "Actions integration"), a historical `as_of` query against either of
  these two counts reflects today's status/priority for any action that
  already existed by `as_of`, not necessarily what that status/priority
  actually was at that historical moment. Full correctness would require
  replaying `SafetyActionHistory`, deliberately out of scope for this
  focused correction.
* Anomaly detection (Milestone 23) scores each of the seven supported
  metrics independently against its own recent history — it does not
  detect anomalies in combinations of metrics, seasonal/cyclical
  patterns (e.g. a metric that is always higher on a particular weekday),
  or anomalies at a granularity finer than `window_days`. A metric can be
  `ANOMALOUS` in isolation while remaining unremarkable in the context
  other metrics would provide; correlating across metrics is deliberately
  left to the reviewer, not automated here (see "Explicitly out of
  scope" in the completion report for the full list of what this
  milestone does not build, including LLM-generated explanations, causal
  inference, and anomaly alerts/notifications).
* Pattern detection (Milestone 24, reusing Milestone 22's `recurrence.py`
  unchanged) covers `(site, event_type)` and `(site, event_subtype)`
  recurrence only, over `INCIDENT`/`NEAR_MISS` events — an "event type +
  observation topic" pattern (one of the milestone's own named examples)
  is not built: the ontology has no field distinct from `event_subtype`
  representing an observation topic, and `recurrence.py`'s population is
  a deliberate, tested Milestone 22 scope decision this milestone does
  not expand (see "Pattern methodology" above).
* Association analysis (Milestone 24) is pairwise and linear (Pearson
  correlation) only — it does not detect non-linear relationships, lagged
  relationships (metric A this period predicting metric B next period),
  or associations among three or more metrics at once. A pair reported
  `WEAK` may still share a real, non-linear or lagged relationship this
  method cannot see; a genuinely strong association between two metrics
  never implies anything about a third, unmeasured factor driving both.
  Correlating across more than two metrics, and any causal
  interpretation whatsoever, is deliberately left to the human reviewer
  (see "Association methodology" above and the completion report's
  "out-of-scope confirmation").

## What the score does not mean

**The deterministic enterprise risk score is an analytical
prioritization mechanism. It is not a validated probability of an
incident occurring, it does not establish causation, and it must not be
treated as a substitute for professional HSE judgment or as a
regulatory compliance determination.** It exists to help a reviewer
quickly answer "where should I look first," using only rule-based
arithmetic over this organization's own recorded data — nothing here was
learned from data, calibrated against real outcomes, or generated by an
LLM.
