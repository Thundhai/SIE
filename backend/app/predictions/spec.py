"""SIE Predictive Risk Modeling Specification v0.1.

This module is the specification itself — every other module in
`app/predictions/` implements what is decided here. It exists so the
thirteen questions the milestone poses have one, explicit, versioned
answer, not an implicit convention scattered across the codebase.

=====================================================================
1. WHAT EXACTLY IS SIE PREDICTING?
=====================================================================

**Elevated Safety Event Risk**: whether an entity is likely to
experience at least one *qualifying* safety event within a defined
future horizon, based only on information available at prediction time.

This is the milestone's own preferred initial target, and it survives
evaluation against the existing data model: `SafetyEvent` (see
`app/models/safety_event.py`, built in the Intelligence & Predictive
Analytics Foundation milestone) already carries `event_type`,
`event_time`, `site_id`, and `organization_id` on every row, with
temporal-integrity guarantees (`app/intelligence/temporal.py`) already
proven correct by regression test. No other candidate target
(`predict incident severity`, `predict which contractor is involved`,
`predict time-to-next-incident`) is better supported by what exists
today, and each would need data this codebase does not yet reliably
capture (a validated severity scale across all sources, contractor-level
volume sufficient for a per-contractor model, or explicit next-event
timestamps). Elevated Safety Event Risk is therefore the one predictive
target this milestone implements — see item 4 below for exactly which
events qualify.

=====================================================================
2. PREDICTION UNIT
=====================================================================

    Prediction Unit: Site

`SafetyEvent.site_id` is a real, populated foreign key (see
`app/models/safety_event.py`), and a site is the natural granularity at
which "elevated risk" is operationally actionable (a site manager can
act on it; an organization-wide score is too coarse to be useful, and
project/department/contractor/activity are all free-text strings on
`SafetyEvent` today, not first-class entities with their own identity —
see that model's own docstring). Every function in this package accepts
exactly one prediction unit — `entity_type="site"`, `entity_id=<Site.id>`
— and models/features/predictions are never mixed across prediction
units in the same model.

=====================================================================
3. PREDICTION HORIZON
=====================================================================

    As-of:              2026-06-01T00:00:00Z
    Prediction horizon:  2026-06-02T00:00:00Z -> 2026-07-01T00:00:00Z
                         (exclusive of as_of, inclusive of the end date)

Precisely: `horizon_start = as_of` (exclusive — `event_time > as_of`),
`horizon_end = as_of + timedelta(days=HORIZON_DAYS)` (inclusive —
`event_time <= horizon_end`). Every feature in the corresponding
snapshot uses only information with `event_time <= as_of` **and**
`ingestion_time <= as_of` (see `app/intelligence/temporal.py::events_as_of()`,
reused unchanged) — the target is determined *exclusively* by what
happens strictly after that same instant.

=====================================================================
4. TARGET DEFINITION
=====================================================================

    y = 1  if at least one SafetyEvent with event_type == "INCIDENT"
             and data_quality_status in (VALID, PARTIAL)
             has horizon_start < event_time <= horizon_end
             at this site
    y = 0  otherwise

**Why `INCIDENT` only, not near misses or observations.** The milestone
is explicit that these must not be casually equated. An `INCIDENT` (see
`app/models/safety_event.py`'s domain list: injury, property damage,
environmental incident, process incident, vehicle incident) is a
realized safety event — the thing this milestone is actually trying to
anticipate. A `NEAR_MISS` or `OBSERVATION` is evidence *about* risk (and
is exactly what the feature set below uses as a leading indicator, see
item 6) — using it as the target itself would conflate "did an incident
happen" with "was something reported," which is a different question
with a different, and more contested, meaning (see item 5, reporting
bias). `QUARANTINED`/`INVALID` future records never create a label
either way — a data-quality-rejected record occurring during the horizon
must not spuriously flip `y` to 1.

**Not severity-filtered in v1** — any recorded `INCIDENT`, of any
severity, qualifies. A high-potential/severe-only variant is a
defensible, documented future refinement (`incident-target-v2`), not
implemented here, to keep v1's definition simple and auditable.

Versioned as `LABEL_DEFINITION_VERSION` below — never silently redefined;
a changed definition is a new version, and every trained model records
which version it was trained against (`ModelRegistryEntry.label_definition_version`).

=====================================================================
5. REPORTING BIAS — READ BEFORE INTERPRETING ANY RESULT
=====================================================================

**Safety-event datasets are not direct measurements of true safety
risk.** An increase in near-miss/observation reporting can mean
conditions worsened, or it can mean a site's reporting culture improved
(more people report, or reporting was recently encouraged) — the data
alone cannot distinguish these. This codebase never assumes "more
reports = more danger." Concretely:

  * Leading-indicator features (near-miss/observation counts, see item
    9) are used as *predictors*, on the documented hypothesis that
    reporting activity correlates with underlying risk — never
    presented as a direct risk measurement themselves.
  * The target itself (item 4) uses recorded `INCIDENT`s, which are
    somewhat less subject to this ambiguity than near-misses (an
    incident is harder to under-report than a near miss, though
    under-reporting of incidents is also a documented real-world
    phenomenon this codebase does not attempt to correct for).
  * A model trained on this data learns *associations* in whatever data
    it was given, including any reporting-culture effects baked into
    it. Nothing in `app/predictions/explain.py` claims a contributing
    feature *causes* elevated risk — see that module's own docstring.

=====================================================================
6-13: see the sibling modules this specification governs
=====================================================================

  * Historical information / feature/label separation -> `app/predictions/labels.py`,
    `app/predictions/dataset.py` (item 6-7).
  * Feature snapshot -> `app/predictions/feature_snapshot_service.py` (item 8).
  * Allowed features -> `FEATURE_SET_V1` below (item 9), computed via
    the already-existing, already-temporally-safe
    `app/intelligence/features.py`.
  * Feature quality / missingness -> `app/intelligence/features.py`'s
    existing `FeatureValue.data_quality`/`unavailable_reason` (item 10),
    reused unchanged.
  * Exposure -> `app/intelligence/exposure.py`, reused unchanged (item 11).
  * Data sufficiency / cold start -> `app/predictions/predictor.py` (items 12-13).
"""

from __future__ import annotations

# --- Versioning (milestone items 22-23) ---------------------------------------------
PREDICTION_TARGET_VERSION = "elevated-safety-event-risk-v1"
LABEL_DEFINITION_VERSION = "incident-target-v1"
FEATURE_SET_VERSION = "predictive-features-v1"
TRAINING_DATA_VERSION = "safety-risk-v1"

# --- Prediction unit (item 2) --------------------------------------------------------
PREDICTION_ENTITY_TYPE = "site"

# --- Horizon (item 3) -----------------------------------------------------------------
HORIZON_DAYS = 30

# --- Target definition (item 4) -------------------------------------------------------
QUALIFYING_EVENT_TYPE = "INCIDENT"
QUALIFYING_DATA_QUALITY_STATUSES = ("VALID", "PARTIAL")

# --- Data sufficiency / cold start (items 12-13) --------------------------------------
# A site needs at least this many days of *any* recorded safety-event
# history before a prediction is attempted at all -- fewer than this is
# COLD_START, not a fabricated low-risk score (a brand-new site with zero
# incidents is not equivalent to a long-established site with zero
# incidents -- milestone item 13's own example).
MIN_HISTORICAL_DAYS = 30
# Independent of history *length*, a site also needs at least this many
# recorded safety events (any type) in that history for a feature
# snapshot to be considered usable -- fewer is INSUFFICIENT_HISTORICAL_DATA.
MIN_HISTORICAL_EVENT_COUNT = 5

# --- Risk categorization (item 19) -----------------------------------------------------
# Thresholds on the model's raw [0, 1] score -- used for `risk_category`
# regardless of whether the score is also exposed as a calibrated
# `probability` (see Prediction.probability's own docstring). Versioned
# alongside everything else in this module; changing a threshold is a
# deliberate, reviewed change, not a runtime tuning knob.
RISK_CATEGORY_VERSION = "risk-category-thresholds-v1"
ELEVATED_RISK_THRESHOLD = 0.66
MODERATE_RISK_THRESHOLD = 0.33

# --- Staleness (item 30) ---------------------------------------------------------------
# A site with no recorded safety-event activity at all within this many
# days of `as_of` has source data too stale to trust a feature snapshot
# built from it -- STALE_SOURCE_DATA abstention, not a prediction from
# old information presented as current.
MAX_SOURCE_DATA_STALENESS_DAYS = 90

REPORTING_BIAS_NOTE = (
    "Safety-event datasets are not direct measurements of true safety risk. "
    "An increase in near-miss/observation reporting can reflect worsening "
    "conditions or an improved reporting culture -- this system never "
    "assumes 'more reports = more danger' without qualification. See "
    "app/predictions/spec.py, item 5."
)

SAFETY_LANGUAGE_NOTE = (
    "This is a model estimate, not a certainty. The model identifies "
    "elevated risk of a qualifying safety event within the horizon based "
    "on available historical data -- it does not predict that an accident "
    "will occur."
)
