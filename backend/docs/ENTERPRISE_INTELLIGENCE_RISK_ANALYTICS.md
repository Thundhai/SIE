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

An event landing exactly on the shared boundary (`event_time == T - N
days`) is included in *both* windows' underlying event lists at the raw
query level — documented, tested
(`tests/test_enterprise_intelligence_service.py`), and treated as
"which side of midnight" ambiguity inherent to any inclusive-both-ends
boundary, not a bug.

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

`actions_context` reports purely factual counts from `SafetyAction`:
`open_action_count`, `overdue_action_count` (not terminal, past its
`due_date`), `high_priority_action_count` (not terminal,
`HIGH`/`CRITICAL` priority). Never a claim like "these actions will
reduce risk by X%"; this endpoint creates no action of its own.

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
