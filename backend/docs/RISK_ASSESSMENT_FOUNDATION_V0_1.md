# SIE Enterprise Risk Assessment Foundation v0.1

> **Extended by SIE Milestone 26: Formal Enterprise Risk Assessment
> Engine v0.2.** Layers the specific pieces a *formal* assessment record
> needs on top of the architecture below, without redesigning any of it:
> `assessment_type`/`reference` fields, a fourth, manual `ARCHIVED`
> lifecycle state, `linked_action_id` (a finding's response, distinct
> from an `ACTION` evidence reference — see "Findings"), inherent/
> residual risk methodology-version snapshots (see "Risk matrix
> methodology"), and a new, immutable `RiskAssessmentHistory` audit
> trail dedicated to this domain. See each section's own "Milestone 26"
> callout below for the specific change; `enterprise-risk-v1` is, again,
> completely untouched.

> **Extended by SIE Milestone 27: Risk Assessment & Action Management
> Integration v0.1.** Closes the loop between identified risk → assessed
> risk → corrective action → action status → finding closure, while
> keeping `SafetyAction` (SIE Milestone 17) the single source of truth
> for actions — never a second action system. A finding may now require
> *multiple* actions, via a new `RiskAssessmentFindingAction` relationship
> table that supplements (never replaces) Milestone 26's own
> `linked_action_id`; a new, explicit `POST .../findings/{finding_id}/close`
> route is the one governed path to closing a finding, deliberately never
> triggered by a linked action's own status. See "Linking a finding to
> its response action(s)" and "Closure governance" below for the full
> detail.

> **Extended by SIE Milestone 28: Enterprise Risk Assessment Reporting &
> Decision Intelligence v0.1.** A read-only reporting/decision-readiness
> layer on top of everything above — `GET .../{id}/report` and
> `GET .../{id}/readiness`. It computes no new risk rating, invents no new
> risk-area taxonomy, and mutates nothing; it only aggregates and explains
> what the existing assessment/finding/action/evidence/ontology domains
> already contain. See "Reporting & decision readiness" below for the
> full detail.

> **Extended by SIE Milestone 29: Enterprise Risk Assessment Evidence &
> Control Effectiveness Foundation v0.1.** A dedicated control-management
> sub-resource layered onto the finding-level controls this document
> already described — per-control create/read/update, an attributed
> effectiveness-assessment action distinct from generic metadata edits,
> and evidence linking to existing finding evidence. It computes no new
> risk rating (a control's effectiveness never automatically changes
> residual risk) and adds no new deletion path. See "Control
> effectiveness assessment & evidence" below for the full detail.

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
  |          |            |
  +----------+------------+--> ARCHIVED
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
* **ARCHIVED** *(SIE Milestone 26)* — historical only, terminal, reached
  only via the one new, manually-invoked `POST .../{id}/archive`. Retires
  an assessment that turned out not to be needed (from `DRAFT`/
  `IN_REVIEW`) or one that was never superseded by a later version (from
  `APPROVED`) — distinct from `SUPERSEDED`, which always means "a newer
  version now exists in this lineage." A `SUPERSEDED` assessment can
  never itself be archived (there is nothing left to retire — the
  lineage already moved on). Gated on `risk_assessment:approve`, the
  same, more-privileged permission `submit`/`approve` require, since
  archiving is at least as consequential — it can retire an
  already-`APPROVED` assessment.

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

## Assessment identity fields

*(SIE Milestone 26.)* Two additional `RiskAssessment` fields, both
required at the API layer to state upfront why an assessment exists,
never inferred after the fact:

* `assessment_type` — a governed, native-enum classification of *why*
  this assessment was performed: `BASELINE`/`PERIODIC`/
  `INCIDENT_TRIGGERED`/`CHANGE_TRIGGERED`/`TARGETED`. Required on
  create (existing pre-Milestone-26 rows are backfilled to `BASELINE`,
  since no row could have declared a type that didn't yet exist). Not
  automatically carried forward on supersession — like `title`, a
  superseding version states its own `assessment_type` explicitly (a
  `PERIODIC` baseline superseded by an `INCIDENT_TRIGGERED`
  reassessment is a real, expected case).
* `reference` — an optional, free-text external reference (e.g. an
  organization's own `"RA-2026-0042"` numbering scheme). A pass-through
  provenance field, exactly like `SafetyAction.external_reference` —
  never interpreted or validated by SIE itself.

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

### Linking a finding to its response action(s)

*(SIE Milestone 26; extended to a real relationship by Milestone 27.)*
"What is the organization's actual response to this finding" —
architecturally distinct from an `ACTION`-type
`RiskAssessmentFindingEvidence` row, which answers a different question,
"why does this finding exist" (an already-existing corrective action
that evidences the hazard). The two are never conflated: a finding may
cite an existing action as evidence *and separately* link to the
action(s) raised in response to it, and either, neither, or both may
exist at once.

**SIE Milestone 27: Risk Assessment & Action Management Integration
v0.1** replaces the single-action limitation with a real relationship —
a serious finding may need several controls/actions, not just one:

```
RiskAssessmentFinding
        |
        +-- SafetyAction A
        +-- SafetyAction B
        +-- SafetyAction C
```

**The smallest backward-compatible change, not a redesign.**
`RiskAssessmentFinding.linked_action_id` (SIE Milestone 26's own
nullable FK, `ondelete='SET NULL'`) is **kept exactly as it was** — same
column, same migration, same `PATCH .../findings/{finding_id}` behavior,
every Milestone 26 test still passing unmodified. A new table,
`RiskAssessmentFindingAction` (`app/models/risk_assessment_finding_action.py`
— tenant-scoped, `ON DELETE CASCADE` on both `finding_id` and
`action_id`, unique on `(finding_id, action_id)`), *supplements* it as
the canonical multi-action relationship: `update_finding()`'s existing
`linked_action_id` branch now also writes/removes the matching
relationship row, so a finding linked only through the legacy field and
one linked through the new endpoints are both visible through the one
same query (`GET .../findings/{finding_id}/actions`) — there is exactly
one underlying source of truth for "which actions does this finding
currently have." Migration 0019 backfills one relationship row per
pre-existing non-`NULL` `linked_action_id`, so this is true immediately
upon upgrade too, not just for rows created afterward — no Milestone 26
data is lost or reinterpreted.

**API** (all under `/api/v1/risk-assessments`, all tenant-scoped and
gated on `require_editable()` exactly like every other finding
mutation — see "Immutability after approval" below):

```
POST   /{assessment_id}/findings/{finding_id}/actions        create a new SafetyAction, linked in one operation
POST   /{assessment_id}/findings/{finding_id}/actions/link    link an existing SafetyAction
DELETE /{assessment_id}/findings/{finding_id}/actions/{action_id}   unlink
GET    /{assessment_id}/findings/{finding_id}/actions         every action currently linked to this finding
GET    /actions/{action_id}/findings                          every finding currently linked to this action
```

Creating a new action (`POST .../actions`) requires `RISK_ASSESSMENT_WRITE`
*and* `INTERVENTION_MANAGE` (`+INTERVENTION_ASSIGN` if `owner_user_id` is
supplied) — creating a `SafetyAction` is an Actions-domain capability
`risk_assessment:write` alone never grants, mirroring the "risk_assessment:
write != governance:manage" precedent (SIE Milestone 25A) one boundary
over. Linking/unlinking an *existing* action requires only
`RISK_ASSESSMENT_WRITE` (it never mutates the action itself). Both
link and unlink are idempotent by construction — linking an
already-linked action, or unlinking one that isn't linked, returns the
current state rather than erroring or duplicating (item 10's own
"safely retryable" requirement); creating a genuinely new action instead
supports `Idempotency-Key`, the identical mechanism `POST
/risk-assessments` already uses.

**The action's own origin, without a new `SafetyAction` column.** A
`SafetyAction` created via `POST .../actions` records which
assessment/finding it came from inside its own, already-existing
`attributes` JSON column (`{"risk_assessment_origin": {"assessment_id":
..., "finding_id": ...}}`) — the exact "bounded, domain-specific
structured data... don't force a migration for every new field"
extension point `app/models/safety_action.py`'s own docstring already
documents, never a new FK column on `SafetyAction` itself, which this
milestone leaves completely unmodified. An action merely *linked* (not
created from a finding) carries no such origin — the distinction between
"created from" and "linked to" is real and preserved.

**The action's own domain trail is written too, not duplicated.**
`POST .../actions` also calls `app/services/safety_action_service.py`'s
own `record_history()`/`audit_action_event()` (`SafetyActionHistory`
`CREATED`, `AuditLog` `SAFETY_ACTION_CREATED`) — the identical calls
`app/api/v1/actions.py::create_action()` itself makes — so that action's
own history looks the same regardless of which endpoint created it.

## Closure governance (SIE Milestone 27)

```
OPEN <-> ADDRESSED -> CLOSED (terminal)
```

**A completed action never automatically closes a finding.** The
milestone's own explicit unsafe example —
`if action.status == COMPLETED: finding.status = CLOSED` — is never
implemented anywhere in this codebase. Nothing in the Risk Assessment
domain reads a linked action's `status` at all; a `SafetyAction`
transitioning to `COMPLETED` has zero side effect on any finding it
happens to be linked to (see
`tests/test_risk_assessment_m27.py::test_completed_action_does_not_automatically_close_finding`).
Finding status and action status are, and remain, two independent facts
— an assessor may reasonably judge that residual risk remains
unacceptable even after the linked action is done.

**`CLOSED` has exactly one path: `POST .../findings/{finding_id}/close`.**
The generic `PATCH .../findings/{finding_id}` `status` field still moves
a finding between `OPEN`/`ADDRESSED` freely (unchanged from before this
milestone), but explicitly rejects a target of `CLOSED` with a `422`
pointing at the dedicated route — there is no back door. `close_finding()`
is gated on `RISK_ASSESSMENT_APPROVE` (the same, more-privileged
permission `submit`/`approve`/`archive` already require — closure is a
consequential enough decision to hold to it) and requires, in its
request body, an explicit, non-blank `closure_reason` (item 6's own
"human-controlled and explicitly recorded"; there is no inferred or
default reason). `require_finding_closable()`
(`app/services/risk_assessment_service.py`) additionally refuses to
close a finding that was never actually rated (`likelihood is None`) —
closing an un-rated candidate or an untouched finding is never a
legitimate "we decided this is resolved," only nothing having happened
yet. `CLOSED` is terminal (mirrors `RiskAssessmentStatus.ARCHIVED`'s own
reasoning) — reassessing a closed finding means a new finding (or a new
assessment version), never reopening this one.

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

### Methodology-version snapshots (historical integrity)

*(SIE Milestone 26.)* Alongside the score/classification pair, rating a
finding also snapshots `RiskRating.calculation_version` (today,
`risk-assessment-v1`) onto the finding itself —
`inherent_risk_methodology_version` when `likelihood`/`consequence` is
set, `residual_risk_methodology_version` when
`residual_likelihood`/`residual_consequence` is set. Both stay `NULL` on
an unrated finding — never backfilled to a version that was never
actually used to compute anything. This is the same "what did we
actually calculate, and with which version of the methodology" guarantee
`risk_area_ontology_version` already provides for the risk-area
reference (see "Historical integrity" above): if `risk-assessment-v1` is
ever superseded by a `risk-assessment-v2` (a changed band, a changed
scale), an already-rated finding's own snapshot still answers "this was
computed under v1" — regardless of what the *current* default
calculation version is by the time anyone reads it back.

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
sub-resource. **SIE Milestone 29** (below) supplements this, never
replaces it: a dedicated `.../controls` sub-resource now also exists,
for the finer-grained per-control workflow (create one control without
resending the whole array, assess its effectiveness with an attributed
rationale, link it to specific evidence) the bulk-replace path was never
designed for.

## Control effectiveness assessment & evidence (SIE Milestone 29)

> **SIE Milestone 29: Enterprise Risk Assessment Evidence & Control
> Effectiveness Foundation v0.1.** Turns "a finding may carry controls"
> (above) into a governed workflow an HSE professional can actually use
> to answer *"what controls exist, how effective are they, what
> evidence supports that, and how does that relate to residual risk and
> corrective actions?"* — without collapsing any of those into one
> record:

```
Finding (identified risk)
   |
   +-- Existing Controls (RiskAssessmentControl)
   |      |
   |      +-- Control Evidence (RiskAssessmentControlEvidence
   |      |     -> an existing RiskAssessmentFindingEvidence row,
   |      |     never a duplicated payload)
   |      |
   |      +-- Effectiveness Assessment (effectiveness +
   |            effectiveness_rationale + assessed_at +
   |            assessed_by_user_id -- set only together, only by
   |            POST .../assess-effectiveness)
   |
   +-- Residual Risk (RiskAssessmentFinding.residual_*  -- completely
   |     independent; see "Residual risk" below -- never derived from
   |     control existence or effectiveness)
   |
   +-- Corrective Actions (SafetyAction, via RiskAssessmentFindingAction
         -- SIE Milestone 27; related to controls only in that both
         concern this finding, never the same record)
```

**A dedicated control sub-resource, additive to the bulk-replace path.**
`GET`/`POST .../findings/{finding_id}/controls`,
`GET`/`PATCH .../controls/{control_id}` — the generic `PATCH` carries
only non-effectiveness metadata (`description`/`control_type`/`status`/
`owner_user_id`/`reference`); it has no `effectiveness` field at all, so
an effectiveness rating can never be set silently through it.

**Effectiveness assessment is its own, attributed, dedicated action.**
`POST .../controls/{control_id}/assess-effectiveness` is the *one* path
that ever sets `effectiveness` together with `effectiveness_rationale`
(required, non-blank), `assessed_at` (server time by default — a
client-supplied `assessed_at` is accepted for backdating a
paper-record assessment, but the *actor* is always the authenticated
caller, never client-supplied), and `assessed_by_user_id` (the
authenticated caller). `effectiveness_rating` may never be
`NOT_ASSESSED` — that value means "no assessment happened," so an
assessment call can never conclude it; `NOT_ASSESSED` must never
masquerade as an assessed conclusion. Gated on `RISK_ASSESSMENT_WRITE`
— the same permission finding risk-rating already requires, since both
are an assessor's own expert judgment, not the more privileged
`RISK_ASSESSMENT_APPROVE` closure/archival already requires elsewhere.

**Control existence is not proof of effectiveness — and this milestone
never blurs the two.** A brand-new control (via either the dedicated
`POST .../controls` or the legacy bulk-replace path) is always
`NOT_ASSESSED` until a human explicitly assesses it. Nothing in this
codebase ever infers effectiveness from a linked `SafetyAction`'s status
— a `COMPLETED` action that was raised to implement a control does not
mark that control `EFFECTIVE` (mirrors SIE Milestone 27's own
"a completed action never automatically closes a finding" principle one
level down, at the control instead of the finding).

**`RiskAssessmentControlEvidence`** links a control to an *existing*
`RiskAssessmentFindingEvidence` row belonging to the same finding —
never a duplicated evidence payload, and provenance stays exactly as
traceable as the finding evidence's own (`POST`/`DELETE
.../controls/{control_id}/evidence/{evidence_id}`, both idempotent by
construction — linking already-linked evidence or unlinking
never-linked evidence is a safe no-op, never an error).

**Two additive `ControlType`/`ControlStatus` values.** `ControlType`
gains `OTHER` (a real control that doesn't fit the hierarchy-of-controls
categories still needs to be recordable). `ControlStatus` gains
`PARTIALLY_IMPLEMENTED` and `NOT_VERIFIED` — two real, distinct states
an HSE audit needs: a control only partly rolled out is not the same as
`PROPOSED`, and "installed but nobody has confirmed it works" is not the
same as `NOT_IMPLEMENTED`. `ControlEffectiveness` is unchanged — its
existing four values already matched the spec exactly.

**Historical integrity is free, not engineered — the identical SIE
Milestone 28 insight, one level down.** Every control-mutating route
(`create_control`/`update_control`/`assess_control_effectiveness`/
`link_control_evidence`/`unlink_control_evidence`) calls the same
`require_editable()` every finding-mutating route already calls: once
an assessment is `APPROVED`/`SUPERSEDED`/`ARCHIVED`, controls (and their
evidence links) can no longer be mutated at all. No new snapshot table
or copy-on-approve mechanism was needed — reading `finding.controls`
fresh from the database already *is* the historical snapshot.

**No deletion or retirement route exists in this milestone.** The spec's
own guidance — "prefer soft retirement / status transition over
destructive deletion" — is satisfied here by building neither: a
control's `status` can already represent "no longer relevant" via the
existing values well enough for v0.1, and adding an irreversible
deletion path was explicitly out of scope. `CONTROL_DELETED`/
`CONTROL_RETIRED` history event types therefore do not exist yet either
— a future milestone that adds either route adds its own change type
alongside it.

**History and audit.** `RiskAssessmentHistory` gains a `control_id`
column (nullable, `ON DELETE SET NULL`, always paired with the owning
finding's own `finding_id`) and five new `change_type` values:
`CONTROL_CREATED`, `CONTROL_UPDATED`, `CONTROL_EVIDENCE_LINKED`,
`CONTROL_EVIDENCE_UNLINKED`, `CONTROL_EFFECTIVENESS_ASSESSED` — written
in the same `assessment_mutation_transaction()` as every other mutation
in this domain, alongside a matching `AuditLog` entry
(`RISK_ASSESSMENT_CONTROL_CREATED`/`_UPDATED`/
`_EFFECTIVENESS_ASSESSED`/`_EVIDENCE_LINKED`/`_EVIDENCE_UNLINKED`).

**Reporting integration (extends SIE Milestone 28, additively).** `GET
.../{assessment_id}/report` gains a `control_effectiveness` section:
total controls, implementation-status distribution, effectiveness-rating
distribution, findings with no controls, findings with controls but no
effectiveness assessment, findings with ineffective/partially-effective
controls, and evidence coverage for *assessed* controls specifically.
Entirely deterministic counts — no invented "control effectiveness
score," no management recommendation. Because controls (like findings)
are immutable once the assessment is no longer editable, this section
carries no `computed_at` of its own — it is part of the same historical
snapshot as everything else in the report except `action_response_summary`.

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
audit-log system. `AuditAction` members:
`RISK_ASSESSMENT_CREATED`/`_UPDATED`/`_SUBMITTED`/`_APPROVED`/
`_SUPERSEDED`/`_ARCHIVED` *(Milestone 26)*/`_FINDING_CREATED`/
`_FINDING_UPDATED`/`_FINDING_RISK_RATED` *(Milestone 26; covers both an
inherent and a residual rating change)*/`_FINDING_ACTION_LINKED`/
`_FINDING_ACTION_UNLINKED` *(Milestone 26; reused unchanged by Milestone
27's own new relationship endpoints — see "Linking a finding to its
response action(s)" above)*/`_FINDING_ACTION_CREATED`/`_FINDING_CLOSED`
*(Milestone 27)*. Creating a new action from a finding also writes the
Actions domain's own, pre-existing `SAFETY_ACTION_CREATED` — reused, not
duplicated (see above).

### `RiskAssessmentHistory` — a domain-scoped record, not a second `AuditLog`

*(SIE Milestone 26, item 9.)* A new, append-only,
`OrganizationScopedMixin` table (`app/models/risk_assessment_history.py`)
mirrors `SafetyActionHistory`'s own established Milestone 17 precedent
exactly: one row per assessment- or finding-level change
(`ASSESSMENT_CREATED`/`_UPDATED`/`_SUBMITTED`/`_APPROVED`/`_SUPERSEDED`/
`_ARCHIVED`, `FINDING_CREATED`/`_UPDATED`/`_RISK_RATED`/
`_RESIDUAL_RATED`/`_ACTION_LINKED`/`_ACTION_UNLINKED`/`_ACTION_CREATED`/
`_CLOSED` *(the last two, Milestone 27)*, and `CONTROL_CREATED`/
`_UPDATED`/`_EVIDENCE_LINKED`/`_EVIDENCE_UNLINKED`/
`_EFFECTIVENESS_ASSESSED` *(Milestone 29 — each also carries the new,
nullable `control_id` column alongside its owning `finding_id`)*),
carrying `assessment_id`, an optional `finding_id`, `from_status`/`to_status`,
`changed_by_user_id`/`changed_by_api_client_id`, `request_id`, and an
optional free-text `comment`. `change_type` is a plain string (via the
typo-guard `RiskAssessmentHistoryChangeType` convenience class), not a
native enum — identical to `SafetyActionHistory.change_type`'s own
reasoning: a fixed, closed vocabulary of change *kinds* internal to this
codebase, never a client-facing governed value, so a native enum's
migration overhead buys nothing here.

**This is deliberately not a second `AuditLog`.** `AuditLog` is the
platform-wide, cross-domain "what happened, who did it, from where"
record every resource type already writes to; `RiskAssessmentHistory` is
this domain's own, queryable "what changed on *this specific
assessment/finding*, and in what order" timeline — the same relationship
`SafetyActionHistory` already has with `AuditLog`. Every mutation in this
domain writes to *both*, in the same transaction, never one without the
other (see "Transaction integrity" below).

## API

```
POST   /api/v1/risk-assessments
GET    /api/v1/risk-assessments
GET    /api/v1/risk-assessments/{id}
PATCH  /api/v1/risk-assessments/{id}
POST   /api/v1/risk-assessments/{id}/submit
POST   /api/v1/risk-assessments/{id}/approve
POST   /api/v1/risk-assessments/{id}/archive      (SIE Milestone 26)
GET    /api/v1/risk-assessments/{id}/findings
POST   /api/v1/risk-assessments/{id}/findings
PATCH  /api/v1/risk-assessments/{id}/findings/{finding_id}
POST   /api/v1/risk-assessments/{id}/findings/{finding_id}/actions        (SIE Milestone 27)
POST   /api/v1/risk-assessments/{id}/findings/{finding_id}/actions/link   (SIE Milestone 27)
DELETE /api/v1/risk-assessments/{id}/findings/{finding_id}/actions/{action_id}  (SIE Milestone 27)
GET    /api/v1/risk-assessments/{id}/findings/{finding_id}/actions        (SIE Milestone 27)
POST   /api/v1/risk-assessments/{id}/findings/{finding_id}/close          (SIE Milestone 27)
GET    /api/v1/risk-assessments/actions/{action_id}/findings              (SIE Milestone 27)
GET    /api/v1/risk-assessments/{id}/report                               (SIE Milestone 28)
GET    /api/v1/risk-assessments/{id}/readiness                            (SIE Milestone 28)
GET    /api/v1/risk-assessments/{id}/findings/{finding_id}/controls                              (SIE Milestone 29)
POST   /api/v1/risk-assessments/{id}/findings/{finding_id}/controls                              (SIE Milestone 29)
GET    /api/v1/risk-assessments/{id}/findings/{finding_id}/controls/{control_id}                 (SIE Milestone 29)
PATCH  /api/v1/risk-assessments/{id}/findings/{finding_id}/controls/{control_id}                 (SIE Milestone 29)
POST   /api/v1/risk-assessments/{id}/findings/{finding_id}/controls/{control_id}/assess-effectiveness  (SIE Milestone 29)
POST   /api/v1/risk-assessments/{id}/findings/{finding_id}/controls/{control_id}/evidence/{evidence_id}    (SIE Milestone 29)
DELETE /api/v1/risk-assessments/{id}/findings/{finding_id}/controls/{control_id}/evidence/{evidence_id}    (SIE Milestone 29)
```

The first eight (minus `archive`) are the Milestone 25 spec's own named
minimum. `PATCH .../findings/{finding_id}` is one deliberate addition
beyond that list: without it, a system-generated candidate finding would
have no path to ever be reviewed, rated, or given controls — which would
make the "candidate ≠ approved risk" architecture unreachable through
this API. `POST .../{id}/archive` is Milestone 26's own one new route —
the sole, manual, human-invoked path to `ARCHIVED` (see "Assessment
lifecycle" above); every other transition already had a route. The six
Milestone 27 routes are its own named minimum functionality list (create/
link/unlink/view actions for a finding, view findings for an action,
close a finding) — see "Linking a finding to its response action(s)" and
"Closure governance" above for each one's own rationale. No "create new
version"/"supersede" endpoint exists (folded into `POST
/risk-assessments` via `supersedes_assessment_id`); no dedicated controls
sub-resource exists (folded into the finding `PATCH`).

## Idempotent creation

*(SIE Milestone 26.)* `POST /risk-assessments` accepts an optional
`Idempotency-Key` header, using the identical, already-established
mechanism `POST /actions` (`app/core/idempotency.py`) already uses:
replaying the same key with an identical request body returns the
original `201` response verbatim rather than creating a second
assessment; replaying the same key with a materially different body is a
`409`. See "Transaction integrity" below for how this composes with the
rest of the create path's own single transaction.

## Transaction integrity

*(SIE Milestone 26, item 9 — "the lesson from Milestone 17.")* Every
mutating endpoint in this domain wraps its assessment/finding row
changes, `RiskAssessmentHistory` entry/entries, `AuditLog` entry, and (for
create) the `IdempotencyKey` response record in one transaction
(`assessment_mutation_transaction()`, already the existing Milestone 25
pattern — reused, not duplicated). A failure at any point — including
one injected *after* an intermediate write has already flushed, such as
the audit call failing after history has already been recorded — rolls
back the entire transaction: no assessment, no finding, no history row,
no audit row, and no idempotency record survive a partial failure. See
`tests/test_risk_assessment_transaction_integrity.py` for the dedicated
regression coverage (mirrors `tests/test_actions_transaction_integrity.py`'s
own established pattern).

## Reporting & decision readiness (SIE Milestone 28)

Turns `Intelligence → Risk Assessment → Findings → Actions` into a
governed reporting/decision-readiness layer, without introducing any new
risk calculation, risk-area taxonomy, ontology engine, AI-generated
conclusion, or automatic approval/closure. Everything below is computed
by `app/risk_assessment/reporting.py::compute_risk_assessment_report()`
from data the domain already owns — it is read-only end to end (no
migration was needed for this milestone).

**Two routes, both `RISK_ASSESSMENT_READ`, both reuse
`_get_owned_assessment_or_404()`** (the same tenant-isolation/machine-
pinning/404 helper every other assessment route already uses — no new
authorization logic was written):

```
GET /api/v1/risk-assessments/{id}/report      -- full report
GET /api/v1/risk-assessments/{id}/readiness   -- just the readiness section
```

**Report sections** (`RiskAssessmentReportRead`):

* `assessment_summary` — identity fields (already on the assessment row)
  plus finding/action counts: `finding_count`, `findings_by_status`,
  `findings_by_candidate_status`, `unrated_finding_count`,
  `linked_action_count`, `action_status_counts`.
* `risk_distribution` — `RiskBandCounts` (critical/high/moderate/low/
  unrated) for `inherent` and `residual` risk, kept as two clearly
  separate objects rather than one merged count.
* `risk_areas` — one `RiskAreaSummary` per governed risk-area concept
  actually referenced by a finding in this assessment (the existing
  ontology's `risk_area_concept`, per Milestone 25A — no new risk-area
  enum): finding count, highest inherent/residual risk score and
  classification, open/closed finding counts, associated action count.
* `action_response_summary` — findings with zero/one/multiple response
  actions (both `linked_action_id` and the Milestone 27 relationship
  table, deduplicated), and completed/cancelled/outstanding/overdue
  response-action counts. **Deliberately computed against current wall-
  clock time, not the assessment's own `as_of`** — a linked
  `SafetyAction`'s status and due date keep changing after the assessment
  is approved (that is Milestone 27's whole point), so this section
  carries its own `computed_at` timestamp, distinct from
  `assessment.as_of`, and is documented as *current*, not historical,
  state. A completed action is never interpreted as an automatically
  closed finding — closure stays exclusively the Milestone 27
  `POST .../findings/{finding_id}/close` route.
* `evidence_coverage` — per-finding counts of event / knowledge-document /
  action / intelligence (`ANOMALY`+`PATTERN`+`ASSOCIATION` grouped, per
  the spec's own wording) evidence, plus findings with multiple evidence
  types and findings with none. No subjective "confidence score" — only
  the existing `RiskEvidenceType` categories, counted.
* `readiness` — a deterministic `READY`/`NOT_READY` **indicator**, never
  an approval recommendation: `status` plus a list of plain factual
  `reasons` (e.g. `"3 findings remain unrated."`). Reasons are checked
  in tests to never contain "recommend" or "approv" — see
  `test_readiness_never_recommends_approval`. `NOT_READY` triggers
  include unrated findings, pending candidate review, findings without
  evidence, unresolved critical/high risk findings (using residual risk
  once rated, falling back to inherent risk otherwise, and excluding
  `CLOSED` findings), and high-risk findings with no response action —
  the assessment having zero findings is also `NOT_READY`, not
  vacuously "ready."

**Historical integrity.** Once an assessment is `APPROVED`/`SUPERSEDED`/
`ARCHIVED`, `require_editable()` already blocks every route that would
mutate a finding (the existing Milestone 25 invariant) — so simply
reading `assessment.findings` fresh from the database *is* the correct
historical snapshot; Milestone 28 needed no new snapshot table or
copy-on-approve mechanism to satisfy this. A new assessment version
(`supersedes_assessment_id`) never touches the findings of the version it
supersedes, so re-fetching an older version's report after a newer
version is created and mutated is unaffected. A deprecated ontology
concept still renders correctly in `risk_areas` (deprecation does not
delete or rewrite the concept row). `methodology_version` is copied onto
the assessment at creation time (Milestone 26) and is never re-read from
current config, so a later config change cannot retroactively alter a
past report's methodology label. Only `action_response_summary` is an
intentional exception to "historical" — see above.

**Performance.** `_get_owned_assessment_or_404()` already eager-loads
`findings` → `controls`/`evidence`/`risk_area_concept` in one query
(pre-existing); the reporting module issues exactly one further query
(`_load_finding_actions()`, for the Milestone 27 relationship table) —
so a report is always **exactly 2 queries**, regardless of finding
count. `test_report_query_count_does_not_grow_with_finding_count` proves
this at 3 vs. 20 findings. No caching was added (the report is cheap and
correctness/historical-integrity matters more than shaving one query).

**Export architecture.** Every field in `RiskAssessmentReportRead` is a
plain, named, typed value — no free text a future exporter would need to
parse — so a PDF/Excel presentation layer can be built later directly
against this response shape without touching
`app/risk_assessment/reporting.py`. No export was built in this
milestone.

## Limitations

* Milestone 29 adds no control deletion or retirement route — a
  control's lifecycle is expressed entirely through its `status` field
  for v0.1; `CONTROL_DELETED`/`CONTROL_RETIRED` history event types do
  not exist yet (a future milestone that adds either route adds its own
  change type alongside it).
* Milestone 29 computes no "control effectiveness score" and never
  automatically alters `residual_risk_score`/`residual_risk_classification`
  from a control's effectiveness, type, or count — residual risk stays
  an independently supplied rating (see "Residual risk" below), exactly
  as it already was before this milestone.
* Milestone 28's report intentionally computes no new risk methodology,
  risk-area taxonomy, AI-generated conclusion, automatic approval,
  automatic risk acceptance, automatic finding closure, or predictive
  signal — it explains the assessment; it does not decide anything about
  it. No PDF/Excel export, no notification, and no frontend dashboard
  exist yet (deliberately out of scope — see the module's own docstring).
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
