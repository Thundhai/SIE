# SIE Enterprise Risk Assessment Foundation v0.1

**SIE Milestone 25.** Moves SIE from risk *intelligence* (Milestones
22-24: indicators, trend, patterns, anomalies, associations, and the
deterministic `enterprise-risk-v1` score) into a structured risk
*assessment* capability — while leaving every one of those engines
completely untouched.

```
Events -> Indicators -> Trends -> Patterns -> Anomalies -> Associations
    -> enterprise-risk-v1
    ------------------------------------------------------------------
    ENTERPRISE RISK ASSESSMENT
    ------------------------------------------------------------------
    -> Risk areas / hazards -> Findings & evidence -> Likelihood
    -> Consequence -> Inherent risk -> Controls -> Residual risk
    -> Actions
```

## Core architectural rule

`app/intelligence/risk_score.py` (`enterprise-risk-v1`) is **not
modified by this milestone at all**. It remains exactly what it was: a
deterministic, 0-100, event-volume-weighted analytical input. This
milestone's own risk matrix (`risk-assessment-v1`) answers a
structurally different question — see "Risk matrix methodology" below —
and the two scores are never combined, compared, or allowed to
influence each other anywhere in this codebase.

This milestone also draws a hard line the rest of this document keeps
coming back to (the spec's own closing point):

1. **What the data says** — "Vehicle incidents increased."
2. **What SIE's analytical engines detect** — "Vehicle incidents are
   anomalous and strongly associated with incident activity."
3. **What the organization assesses** — "Vehicle safety is currently
   HIGH risk, with existing controls requiring review."

SIE produces (1) and (2) automatically. (3) is always a human or
governed-methodology judgment — see "Candidate findings" below for
exactly where that boundary is enforced.

## Assessment hierarchy and scope

```
Organization
   |
   +-- Location            (scope=LOCATION -- see below)
          |
          +-- Site / Project
                 |
                 +-- Risk Assessment
```

`RiskAssessmentScope` is `ORGANIZATION`/`LOCATION`/`SITE`. SIE's data
model has no first-class `Location` entity today (only `Organization`
-> `Site`, see `app/models/site.py`) — this milestone deliberately does
not invent a parallel location table to fill that gap (per its own
instruction). `LOCATION` scope is accepted at the schema/API level for
forward compatibility with the hierarchy above, but is, today,
structurally identical to `ORGANIZATION` scope: `site_id` stays `NULL`
and `intelligence_context` is computed at organization scope. When a
genuine `Location` model is introduced in a future milestone, this
scope value becomes meaningful without a breaking change to the enum,
the API, or any stored row.

## Assessment lifecycle

```
DRAFT -> IN_REVIEW -> APPROVED -> SUPERSEDED
```

* **DRAFT** — fully editable (`PATCH /risk-assessments/{id}`, finding
  create/update).
* **IN_REVIEW** — still editable (the same permission gates it; "in
  review" does not mean "locked", only "submitted for approval").
* **APPROVED** — not directly editable. `PATCH` and every finding
  mutation return `422`.
* **SUPERSEDED** — historical only, reached automatically (never via a
  direct client call) when a *later* version in the same lineage is
  itself approved.

`is_allowed_assessment_transition()` (`app/models/risk_assessment_enums.py`)
is the one source of truth for the matrix above — mirrors
`app/models/safety_action_enums.py::is_allowed_action_transition()`
exactly.

### Versioning and lineage

`lineage_id` groups every version of "the same assessment" (defaults to
the first version's own id); `version` increments per lineage;
`supersedes_id` points backward to the version being replaced.
`POST /risk-assessments` with a `supersedes_assessment_id` opens a new
`DRAFT` version in that lineage (`app/services/risk_assessment_service.py::
open_new_version()`) — only an `APPROVED` assessment can be superseded.

**The version being replaced stays `APPROVED` — not `SUPERSEDED` —
until the new version is itself approved.** Superseding at *creation*
time would leave a window with zero approved assessments in the
lineage while the replacement is still being drafted or reviewed; the
transition happens inside the approve step instead
(`supersede_previous_version_if_any()`). "What did we assess the risk
to be at that time?" stays answerable forever: a `SUPERSEDED` row is
never edited or deleted, only its `status` changes.

An approved assessment's own rows (its findings, controls, evidence)
are likewise never edited in place once the assessment itself is
`APPROVED` — a substantive change always means opening a new version.

## Risk areas — governed ontology concepts, not a closed enum

> **Corrected by SIE Milestone 25A: Governed Risk-Area &
> Organization-Extensible Risk Taxonomy v0.1.** This milestone originally
> represented risk areas as a closed `RiskArea` Python enum (11 members).
> That enum has been **removed**. `RiskAssessmentFinding.risk_area_concept_id`
> now references a governed `app/models/ontology_concept.py::OntologyConcept`
> row directly — the same architecture Milestone 15 (SIE Enterprise
> Ontology & Data Model Expansion v0.1) already built for the rest of the
> platform's canonical vocabulary, reused here rather than duplicated.
> **Risk Assessment risk areas are governed ontology concepts. SIE's
> initial risk areas are seeded concepts, not the limits of SIE's
> taxonomy — an organization may introduce additional risk concepts
> through the existing ontology governance lifecycle, with no Python
> enum change and no migration. Risk Assessment never accepts an
> arbitrary, uncontrolled risk category.**

### Eligibility: `is_risk_area_eligible`

Not every governed `OntologyConcept` is a risk area — a concept proposed
for an unrelated future purpose should never silently become selectable
here. `is_risk_area_eligible` (a new, additive, governed boolean column
on `OntologyConcept`) is the one flag that answers "may this concept be
used as a Risk Assessment risk area at all" — set explicitly, at
proposal time (`ontology_governance_service.propose_concept(...,
is_risk_area_eligible=True)`), never inferred from a concept's `layer`
and never a second, hard-coded list of "which concept_keys count" living
outside the `ontology_concepts` table itself.

### Global vs. organization-specific concepts

`OntologyConcept.organization_id` is nullable: `NULL` is a **GLOBAL**
concept (platform-wide, available to every organization — Milestone 15's
original, still-default scope, governed by a true `PLATFORM_ADMIN`); a
real organization id is an **organization-specific extension** of the
ontology (visible, and usable as a risk area, only to that one
organization — governed by that organization's own `GOVERNANCE_MANAGE`,
typically its `ORG_ADMIN`). `ontology_governance_service.py`'s existing
`propose_concept()`/`approve_concept()`/`reject_concept()`/
`deprecate_concept()` lifecycle is entirely unchanged in shape — only
the authorization scope (`organization_id`) now varies per concept
instead of always being platform-wide.

### Resolution and validation — never an arbitrary string

A client creating a finding supplies `risk_area_concept_id` (a UUID, not
a free-text category) — `app/risk_assessment/risk_area_resolution.py::
resolve_risk_area_concept()` is the one place this is resolved and
validated, before a finding is ever created:

  * the concept must exist and be either GLOBAL or belong to the
    caller's own organization (tenant isolation — a foreign
    organization's concept is `404`, indistinguishable from one that
    does not exist at all);
  * the concept must be `APPROVED` (`PROPOSED`/`REJECTED`/`DEPRECATED`
    are all rejected with `422`);
  * the concept must be `is_risk_area_eligible`.

### SIE's initial 11 risk areas

`app/risk_assessment/risk_area_ontology_seed.py` declares the 11
original risk areas as GLOBAL, `APPROVED`, `is_risk_area_eligible`
concepts — seeded by migration 0017 itself (not a separate, optional
artifact-application step), so a completely fresh database has all 11
usable immediately after `alembic upgrade head`:

| Original risk area | Ontology scope (`layer` / `parent_domain` / `concept_key`) |
|---|---|
| `WORKING_AT_HEIGHT`, `PPE_COMPLIANCE`, `ELECTRICAL_SAFETY`, `ENVIRONMENTAL`, `LIFTING_OPERATIONS`, `EQUIPMENT_SAFETY`, `FIRE_SAFETY`, `EMERGENCY_PREPAREDNESS` | `observation_topic` / `OBSERVATION` / (same key) — already governed by `config/enterprise_ontology_concepts_v1.json`, now additionally flagged `is_risk_area_eligible` |
| `PROCEDURE_VIOLATION` | `event_subtype` / `OBSERVATION` / `PROCEDURE_VIOLATION` — likewise already governed, now flagged eligible |
| `INCIDENT_SAFETY` | `event_type` / `None` / `INCIDENT` — backfilled: this pre-existing canonical `SafetyEventType` vocabulary predates `OntologyConcept` entirely and had no governed row until this milestone |
| `VEHICLE_SAFETY` | `event_subtype` / `INCIDENT` / `VEHICLE_INCIDENT` — backfilled for the identical reason |

The last two rows are this milestone's own explicit answer to "if any
current value has no valid corresponding governed concept, stop and
report the mismatch rather than silently inventing one": both were
genuinely missing governed rows, documented and backfilled as the
smallest additive extension, never silently reinterpreted.

### Historical integrity

`RiskAssessmentFinding` stores `risk_area_concept_id` (an immutable FK,
never repointed) and `risk_area_ontology_version` (a snapshot of
`OntologyConcept.ontology_version` at the moment the finding was
created). A concept's `ontology_version` is, under the existing
governance lifecycle, set exactly once at approval and never modified
again — so this snapshot is defense in depth, not a workaround for a
value that changes today. What *can* change after a finding is created
is a concept's `status` (`APPROVED -> DEPRECATED`); deprecating a
concept never retroactively touches a finding that already referenced
it while it was `APPROVED` — the historical finding still answers
"which governed concept, at what version, did this refer to at the
time" by simply reading its own `risk_area_concept_id`/
`risk_area_ontology_version`, regardless of the concept's current status.
A **new** finding, however, can no longer reference a `DEPRECATED`
concept (`resolve_risk_area_concept()` rejects it with `422`).

### Terminology integration, unchanged

The existing flow (Milestones 15-16) is fully reused, never duplicated:

```
SOURCE TERMINOLOGY -> TERMINOLOGY MAPPING -> GOVERNED ONTOLOGY CONCEPT -> RISK ASSESSMENT
```

A source term (e.g. "DO", "Dropped Object", "Falling Object") is mapped,
through the existing, unmodified `terminology_calibration_service.py`,
onto a governed `OntologyConcept` — and *that* concept, once `APPROVED`
and `is_risk_area_eligible`, is what a Risk Assessment finding may
reference. This milestone builds no second, risk-assessment-specific
terminology mapping mechanism.

## Findings

A `RiskAssessmentFinding` deliberately separates three kinds of content
into three columns, never one blob, so a client can never present a
human's judgment as if it were system-derived fact:

| Column | Who writes it | Example |
|---|---|---|
| `description` | System (evidence) | "12 vehicle incidents recorded over six periods." |
| `system_analysis_summary` | System (analysis) | "Vehicle incidents show a strong positive association with overall incident activity." |
| `assessor_notes` | Human | "Traffic-management controls require review." |

`likelihood`/`consequence` (and their computed `inherent_risk_score`/
`inherent_risk_classification`) are a fourth, clearly separate
dimension — see "Risk matrix methodology" below.

### Candidate findings — the critical architectural boundary

```
ANOMALY / PATTERN                    (already-computed, Milestone 23/24)
    -> CANDIDATE FINDING              (IDENTIFIED, no rating)
        -> HUMAN REVIEW
            -> ACCEPTED (rated) / REJECTED (never rated)
```

`app/risk_assessment/candidate_generation.py` deterministically surfaces
candidate findings from the existing intelligence engines — v0.1
sources exactly `ANOMALOUS` anomalies and `RECURRING`/`HIGH_RECURRENCE`
patterns, mapped to a governed risk-area concept only where the mapping
is unambiguous (e.g. `vehicle_incident_count` -> the GLOBAL
`VEHICLE_INCIDENT` concept; a metric or subtype with no single clear
mapping, or whose mapped concept is not currently an `APPROVED`,
`is_risk_area_eligible` GLOBAL concept, is skipped, never guessed —
see "Risk areas" above). Associations,
concentrations, indicators, and trend are still fully exposed via
`intelligence_context` — nothing is hidden — but do not yet auto-draft a
candidate in this milestone, a deliberate, documented, narrower initial
scope (see "Limitations").

**A candidate finding is never a rated risk.** `RiskAssessmentFinding.
candidate_status` starts `IDENTIFIED`; `likelihood`/`consequence` are
`NULL` and stay `NULL` until a human explicitly transitions the
candidate to `ACCEPTED` *and separately supplies a rating* — enforced at
the API layer (`PATCH .../findings/{finding_id}` returns `422` if a
rating is supplied while `candidate_status` is `IDENTIFIED`/
`UNDER_REVIEW`/`REJECTED`). A `REJECTED` candidate is never deleted (a
permanent, honest record that it was considered and not accepted) and
never carries a rating either. `candidate_status` is `NULL` (not a
fifth candidate state) on a finding a human authored directly through
`POST .../findings` — it was never a system candidate in the first
place.

No code path in this codebase computes a likelihood or consequence value
from an anomaly's z-score, a pattern's occurrence count, or an
association's correlation coefficient. That computation does not exist.

## Risk matrix methodology

```
likelihood (1-5) x consequence (1-5) = risk score (1-25)
```

**Likelihood:** 1 Rare, 2 Unlikely, 3 Possible, 4 Likely, 5 Almost
Certain.
**Consequence:** 1 Insignificant, 2 Minor, 3 Moderate, 4 Major, 5
Severe.

**Bands** (`settings.RISK_ASSESSMENT_*_MAX`, documented *initial*
defaults, not a claim of universal applicability to every client's own
corporate risk matrix):

```
1-4     LOW
5-9     MODERATE
10-16   HIGH
17-25   CRITICAL
```

Calculation version: `risk-assessment-v1`
(`app/risk_assessment/risk_matrix.py::calculate_risk()`). An invalid
likelihood or consequence (outside 1-5, non-integer) raises
`InvalidRiskScaleValueError` — never silently clamped or coerced.

**Inherent risk is not `enterprise-risk-v1`.** Inherent risk is the risk
*before* considering controls — a human/governed likelihood and
consequence judgment. `enterprise-risk-v1` is a completely different
computation (event-volume-weighted, 0-100, no human judgment involved)
and is never used as, or substituted for, an inherent-risk rating
anywhere in this codebase.

## Controls and effectiveness

A finding may carry zero or more controls
(`RiskAssessmentControl`), each with: `description`, `control_type`
(`ELIMINATION`/`SUBSTITUTION`/`ENGINEERING`/`ADMINISTRATIVE`/`PPE` —
deliberately compact, not a Bow-Tie/HAZOP/LOPA hierarchy-of-controls
engine), `status` (`PROPOSED`/`IN_PLACE`/`NOT_IMPLEMENTED`), `owner`,
`reference`, and `effectiveness`.

**`ControlEffectiveness`** is deliberately simple:
`NOT_ASSESSED`/`INEFFECTIVE`/`PARTIALLY_EFFECTIVE`/`EFFECTIVE`.
`NOT_ASSESSED` (the default) means *no information was provided* — a
genuinely different state from `INEFFECTIVE` ("the control was assessed
and found not to work"). No code path in this codebase ever conflates
the two.

`PATCH .../findings/{finding_id}` with a `controls` list *replaces* the
finding's entire control set atomically — the simplest v0.1 semantics
that fully supports this section without a dedicated controls
sub-resource.

## Residual risk

Residual risk (`residual_likelihood`/`residual_consequence`/
`residual_risk_score`/`residual_risk_classification`) is an
**independently supplied** likelihood/consequence pair, computed by the
identical `calculate_risk()` function used for inherent risk — never a
percentage reduction mathematically derived from inherent risk and a
control-effectiveness value. The milestone's own worked example:

```
inherent:  likelihood=4, consequence=4 -> 16 HIGH
controls:  traffic management, driver competency, vehicle inspection
residual:  likelihood=2, consequence=4 -> 8 MODERATE
```

SIE never claims "the controls reduced risk by 50%" — there is no field
or computation anywhere in this codebase that would produce that claim.

## Evidence model

`RiskAssessmentFindingEvidence` is always a *reference*, never a copy of
the source narrative. `RiskEvidenceType`:

* `EVENT`/`ACTION`/`KNOWLEDGE_DOCUMENT` — carry a real `reference_id`,
  validated at write time to belong to the same organization (or, for
  knowledge, be `GLOBAL`) — mirrors
  `app/services/safety_action_service.py`'s own reference-validation
  precedent (404 whether the id doesn't exist at all or belongs to a
  different organization — never a distinguishing signal).
* `ANOMALY`/`PATTERN`/`ASSOCIATION`/`OTHER` — reference a *computed*,
  non-persisted intelligence result. `reference_id` stays `NULL`;
  `reference_label` carries the exact, already-established
  `evidence_reference` string format `app/intelligence/explanations.py`
  already produces (e.g. `"anomaly:incident_count"`, a recurrence
  `pattern_key`) — reused verbatim, never a second reference format.

Actions are referenced (item 17), never duplicated: an `ACTION`
evidence row points at an existing `SafetyAction` row; this milestone
introduces no second action system.

## Intelligence context — read-only, never recomputed or mutated

Every assessment read (`GET /risk-assessments/{id}`, and the response
of `POST`/`PATCH`/`submit`/`approve`) includes a structured
`intelligence_context`: `deterministic_risk` (`enterprise-risk-v1`),
`anomalies`, `patterns`, `associations`, `trend`, `concentrations`, and
`calculation_versions` (every version string preserved verbatim). This
is computed **fresh, on every read**, from the assessment's own
persisted `organization_id`/`site_id`/`as_of` by calling the *unmodified*
`compute_enterprise_intelligence()` orchestrator (Milestones 22-24) —
never stored as columns, never mutated merely because an assessment was
created. Since every Milestone 22-24 computation is itself
point-in-time-correct and deterministic, an identical `as_of` always
reproduces an identical `intelligence_context` — "what did we assess the
risk to be at that time" stays answerable without persisting a second
copy of data that could drift from what recomputing would show anyway.

## Point-in-time integrity

Every event/action lookup behind `intelligence_context` and candidate
generation goes through `events_as_of()` — the same, single temporal
foundation every Milestone 22-24 computation already uses. No second
temporal implementation exists anywhere in this milestone. `as_of`
(read from the request, or the assessment's own persisted value) is
normalized to UTC-aware before every such call
(`app/services/risk_assessment_service.py::normalize_as_utc()`) —
SQLite (used in this test suite) does not round-trip `tzinfo`, the same
already-established normalization pattern every other Milestone 22-24
module already applies.

## Tenant isolation

Every query is tenant-scoped: `RiskAssessment.organization_id`,
denormalized `organization_id` on every child row
(`RiskAssessmentFinding`/`Control`/`FindingEvidence`, mirroring
`SafetyActionHistory`'s own established "tenant-scoped child of a
tenant-scoped parent" precedent), and every evidence reference
(event/action/knowledge document) explicitly re-validated against the
requesting organization. A valid id belonging to a different
organization is indistinguishable from a nonexistent one — always
`404`, mirroring `app/api/v1/actions.py`'s own "Tenant isolation"
precedent.

## Authorization

Three new permissions (`app/services/permissions.py`) — checked against
the existing vocabulary first, per the milestone's own instruction, and
introduced only because none of `INTELLIGENCE_READ`/`SAFETY_DATA_*`/
`INTERVENTION_*`/`GOVERNANCE_*` genuinely covers "create/edit/approve a
formal risk assessment":

```
risk_assessment:read      -- VIEWER, HSE_USER, HSE_ANALYST, HSE_MANAGER, ORG_ADMIN
risk_assessment:write     -- HSE_ANALYST, HSE_MANAGER, ORG_ADMIN
risk_assessment:approve   -- HSE_MANAGER, ORG_ADMIN
```

Approval is more privileged than writing, which is more privileged than
reading — an `HSE_ANALYST` can draft and submit an assessment but cannot
approve it. `PLATFORM_ADMIN` bypasses per-organization checks entirely,
as it already does everywhere else in this codebase
(`ALL_PERMISSIONS`).

**`risk_assessment:write` never grants ontology governance (SIE
Milestone 25A).** Being able to create/edit a risk assessment is not the
same capability as being able to propose or approve an ontology concept
(`governance:manage`) — an `HSE_ANALYST`/`HSE_MANAGER` can select and
use any existing, `APPROVED`, risk-area-eligible concept, but cannot
create a new organization-specific one. Only that organization's own
`ORG_ADMIN` (or a true `PLATFORM_ADMIN`, for a GLOBAL concept) can govern
the taxonomy itself — see "Risk areas" above.

## Audit trail

Every create/update/submit/approve is written to the existing,
platform-wide `AuditLog` (`app/services/audit_service.py`) — no second
audit-log system. New `AuditAction` members:
`RISK_ASSESSMENT_CREATED`/`_UPDATED`/`_SUBMITTED`/`_APPROVED`/
`_SUPERSEDED`/`_FINDING_CREATED`/`_FINDING_UPDATED`.

## API

```
POST   /api/v1/risk-assessments
GET    /api/v1/risk-assessments
GET    /api/v1/risk-assessments/{id}
PATCH  /api/v1/risk-assessments/{id}
POST   /api/v1/risk-assessments/{id}/submit
POST   /api/v1/risk-assessments/{id}/approve
GET    /api/v1/risk-assessments/{id}/findings
POST   /api/v1/risk-assessments/{id}/findings
PATCH  /api/v1/risk-assessments/{id}/findings/{finding_id}
```

The first eight are the milestone's own named minimum. The ninth
(`PATCH .../findings/{finding_id}`) is one deliberate addition beyond
that list: without it, a system-generated candidate finding would have
no path to ever be reviewed, rated, or given controls — which would
make the "candidate ≠ approved risk" architecture unreachable through
this API. No "create new version"/"supersede" endpoint exists (folded
into `POST /risk-assessments` via `supersedes_assessment_id`); no
dedicated controls sub-resource exists (folded into the finding
`PATCH`).

## Limitations

* Candidate generation (v0.1) sources only `ANOMALOUS` anomalies and
  `RECURRING`/`HIGH_RECURRENCE` patterns, and only where the metric/
  subtype maps unambiguously to one GLOBAL, governed risk-area concept.
  Strong associations,
  notable concentrations, and indicator/trend signals are fully visible
  via `intelligence_context` but do not yet auto-draft a candidate
  finding — a deliberate, narrower initial scope, not an oversight.
* `LOCATION` scope has no first-class entity yet (see "Assessment
  hierarchy and scope" above) — it behaves identically to `ORGANIZATION`
  scope until a genuine `Location` model exists.
* No effectiveness-percentage math, no Bow-Tie/HAZOP/LOPA/FMEA/JSA
  engine, no quantitative risk assessment or Monte Carlo simulation —
  the risk matrix is a transparent, governed lookup, nothing more.
* `intelligence_context` is recomputed on every read (the same
  on-demand, no-snapshot tradeoff Milestone 22 already documented for
  the enterprise intelligence endpoints) — an accepted v0.1 cost, not a
  caching layer waiting to be added silently.

## What a risk assessment does not mean

**An inherent or residual risk rating is a human or governed-methodology
judgment, expressed using a transparent, versioned matrix. It is not
derived from, and must never be confused with, `enterprise-risk-v1`'s
own deterministic activity score, an anomaly's statistical significance,
or an association's correlation coefficient.** Those are separate,
clearly-labeled analytical inputs a human assessor may consult — never
an automatic substitute for the assessment itself.
