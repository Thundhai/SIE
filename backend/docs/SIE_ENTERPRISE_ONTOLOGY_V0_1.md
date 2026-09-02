# SIE Enterprise Ontology & Data Model Expansion v0.1

**A source-system term is not automatically a canonical SIE concept.**

**Ontology expansion is separate from terminology calibration and
separate from real-data reprocessing.** This milestone builds a
governed, versioned, extensible *canonical ontology foundation* — it
does not decide which real-dataset terms map to which concepts (that is
terminology calibration, already built and frozen), and it does not
touch a single real `SafetyEvent` (no reprocessing occurs here, and
none of the 15 rejected real-dataset terminology decisions are changed
by this milestone).

---

## 1. Purpose

Prior milestones built two things: (a) a static, curated canonical
ontology (`SafetyEventType`, `_SUBTYPE_ALIASES`, training/maintenance
vocabularies — all in `app/intelligence/`), and (b) a governed mechanism
for deciding whether a *real source term* maps onto an *already-existing*
canonical concept (`TerminologyMappingDecision`). Real-enterprise
terminology calibration then surfaced 18 genuinely unresolved terms, of
which 15 were correctly **rejected** — not because they were
unimportant, but because SIE's existing ontology had no sufficiently
precise canonical concept for any of them, and inventing one on the
spot (per-term, under ingestion pressure) is exactly the kind of
ungoverned ontology drift this codebase has consistently refused to do.

This milestone closes that loop **the right way**: a deliberate,
evidence-based investigation of those 15 gaps, run as its own governed
process, independent of any specific real dataset execution — producing
a small number of well-justified new canonical concepts (never a
sprawling new taxonomy), each versioned, each with recorded
provenance/justification, each requiring platform-wide governance to
exist at all.

```
SOURCE TERMINOLOGY
       |
TERMINOLOGY MAPPING          TerminologyMappingDecision (org-scoped,
       |                     unchanged by this milestone)
CANONICAL SIE ONTOLOGY       OntologyConcept (platform-wide, NEW)
       |                     + the pre-existing static ontology
       |                     (SafetyEventType, _SUBTYPE_ALIASES, ...)
ENTERPRISE SAFETY DATA       SafetyEvent (unaffected -- no row is
       |                     classified against a new concept yet)
INTELLIGENCE
```

## 2. Canonical domains (existing, unchanged baseline)

The pre-existing, unmodified canonical vocabulary this milestone builds
on top of, never renames, and never restructures:

- **`SafetyEventType`** (`app/intelligence/enums.py`) — the eleven
  top-level event types: `INCIDENT`, `NEAR_MISS`, `OBSERVATION`,
  `INSPECTION`, `AUDIT`, `CORRECTIVE_ACTION`, `PERMIT`, `TRAINING`,
  `WORKFORCE`, `EQUIPMENT`, `ENVIRONMENTAL`. There is no separate
  top-level `MAINTENANCE` type — equipment maintenance is represented
  as a *status* on the `EQUIPMENT` type (`MAINTENANCE_STATUS_TARGET_FIELDS`),
  a deliberate existing design choice this milestone leaves untouched.
- **`_SUBTYPE_ALIASES`** (`app/intelligence/terminology_mapping.py`) —
  the curated `event_type -> {raw alias: canonical subtype}` tables for
  `INCIDENT`, `NEAR_MISS`, `OBSERVATION`, `INSPECTION`, `AUDIT`, `PERMIT`.
  Untouched by this milestone (see §9).
- **Training vocabulary** (`_TRAINING_STATUS_ALIASES`,
  `TRAINING_STATUS_TARGET_FIELDS`) and **maintenance vocabulary**
  (`MAINTENANCE_STATUS_TARGET_FIELDS`) — status-oriented, not
  event-type/subtype-oriented; out of this milestone's scope entirely
  (no gap was found or investigated here).
- **`TerminologyMappingDecision`** (`app/models/terminology_mapping_decision.py`)
  — the org-scoped, versioned record of how a real source term maps
  onto an already-existing canonical concept. Its `provenance["target_event_subtype"]`
  compound-target mechanism (Terminology Calibration v0.1 corrective
  commit) is the one place a single governed decision can set both
  `event_type` and `event_subtype` on a `SafetyEvent` — untouched here.

## 3. Ontology boundaries (this milestone's own model)

### A. Event type

The broad top-level classification of an event — `SafetyEventType`,
above. Unchanged.

### B. Event subtype

A subtype belonging to one specific parent event type — e.g.
`INCIDENT -> NEAR_MISS | PROPERTY_DAMAGE | VEHICLE_INCIDENT`. **A
subtype concept must always declare a real, existing parent
`event_type`; cross-domain combinations (`INCIDENT+OBSERVATION`,
`INCIDENT+PERMIT`, `INCIDENT+TRAINING`, `OBSERVATION+PERMIT`,
`OBSERVATION+TRAINING`, or any other pairing that exists elsewhere in
the ontology) are never valid, regardless of which layer is asking.**
This is enforced twice, independently, in this codebase:

- `terminology_calibration_service._valid_compound_subtype_for()` (the
  Terminology Calibration v0.1 corrective commit) — governs what a
  *terminology-mapping decision's* compound `target_event_subtype` may
  be.
- `ontology_governance_service._validate_layer_and_parent_domain()`
  (this milestone) — governs what an *ontology concept itself* may
  declare as its `parent_domain`/`concept_key` combination.

Neither mechanism widens the other; both independently refuse
`INCIDENT+OBSERVATION`-shaped combinations.

### C. Observation topic — the new semantic layer this milestone adds

Investigating the 15 rejected terms surfaced a genuine architectural
gap: SIE's existing `event_subtype` layer answers "what **kind of
finding** was this?" (`UNSAFE_ACT`, `UNSAFE_CONDITION`,
`POSITIVE_OBSERVATION`, `HOUSEKEEPING_DEFICIENCY`, `PPE_ISSUE`) — but
several of the rejected terms (`PPE Compliance`, `Working At Height`,
`Electrical Safety`, `Environmental`, `Lifting Operations`, `Equipment
Safety`, `Fire Safety`, `Emergency Preparedness`) are not findings at
all. They are the **subject-matter/activity/hazard category** an
observation is *about* — a genuinely different, orthogonal dimension.
Forcing a topic into the finding-type layer (e.g. `PPE Compliance` ->
`PPE_ISSUE`) silently assumes every one of those records was a negative
finding, which the topic name alone never establishes — exactly the
kind of semantic guessing this codebase has consistently refused to do
(see the corrective commit's own PPE Compliance investigation).

This milestone therefore introduces `observation_topic` as a new,
explicit ontology **layer**, structurally parallel to (never a
replacement for) `event_subtype`:

```
OBSERVATION (event_type)
 |
 +-- event_subtype layer:      UNSAFE_ACT, UNSAFE_CONDITION,
 |                              POSITIVE_OBSERVATION,
 |                              HOUSEKEEPING_DEFICIENCY, PPE_ISSUE,
 |                              PROCEDURE_VIOLATION (new, this milestone)
 |
 +-- observation_topic layer:  PPE_COMPLIANCE, WORKING_AT_HEIGHT,
                                ELECTRICAL_SAFETY, ENVIRONMENTAL,
                                LIFTING_OPERATIONS, EQUIPMENT_SAFETY,
                                FIRE_SAFETY, EMERGENCY_PREPAREDNESS
                                (all new, this milestone)
```

A record's finding-type and its topic are independent: a `PPE
Compliance`-topic observation could, in principle, resolve to a
`POSITIVE_OBSERVATION` finding (compliant) or a `PPE_ISSUE` finding
(non-compliant) — the topic layer says nothing about which, by design.

**`observation_topic` concept_key values may deliberately reuse an
existing top-level `SafetyEventType` name** (e.g. `ENVIRONMENTAL`,
which also names a top-level event type and an `INCIDENT` subtype,
`ENVIRONMENTAL_EVENT`). This is safe and intentional: `(layer,
parent_domain, concept_key)` together is the real scope key, and
`observation_topic` is a genuinely separate namespace, never read by
the same code path as `event_type`/`event_subtype` classification. The
cross-domain-collision check described in §3B applies only to
`layer='event_subtype'`, where the collision risk is real (a subtype
value is written to the same `SafetyEvent.event_subtype` column
regardless of which event_type it's nested under).

### D. Activity/domain concepts — determined per-concept, not assumed

The milestone's own instructions are explicit that activity/hazard
concepts (working at height, lifting, electrical, environmental,
emergency preparedness) "may represent activities, hazards, topics,
controls, or observation categories rather than event subtypes" and
that determining the correct layer is a core requirement, not an
assumption. §6's proposal table records exactly this determination for
each of the 15 investigated gaps — most landed in the new
`observation_topic` layer, but `Procedure Violation` (a genuine
finding-type, not a topic) correctly landed in the existing
`event_subtype` layer instead, and `FireIncident` (a genuine Incident
subtype, not an observation at all) landed in `event_subtype` under
`INCIDENT`. Five gaps (`Others` ×2, `SecurityBreach`,
`HazardObservation`, `Documentation`) received **no** new concept at
all — see §6 and §8.

## 4. Ontology proposal table

All evidence (occurrence counts) is already public in
`docs/REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.md`; full justification
text lives in the durable artifact,
[`backend/config/enterprise_ontology_concepts_v1.json`](../config/enterprise_ontology_concepts_v1.json).

| Investigated gap | Proposed concept | Layer / parent | Evidence | Existing equivalent? | Why a new concept is required | Impact |
|---|---|---|---|---:|---|---|
| Fire-related incident classification | `FIRE` | `event_subtype` / `INCIDENT` | 4 | None (`ENVIRONMENTAL_EVENT` covers spills, not fire) | Universal, high-severity, distinct HSE category | Additive; not wired into mapping |
| Security-related incident classification | *(none)* | — | 2 | — | Ambiguous scope (physical vs. cyber) + thin evidence | Documented gap, no concept |
| Hazard observation classification | *(none)* | — | 1 | Existing `OBSERVATION` event_type already covers it | Data-entry mismatch, not an ontology gap | Documented gap, no concept |
| PPE compliance topic | `PPE_COMPLIANCE` | `observation_topic` / `OBSERVATION` | 117 | `PPE_ISSUE` exists but is a narrower finding, not this topic | Topic-vs-finding semantic-layer distinction; largest gap after Working At Height | Additive; not wired into mapping |
| Electrical safety topic | `ELECTRICAL_SAFETY` | `observation_topic` / `OBSERVATION` | 47 | None | Universal, distinct HSE topic | Additive |
| Environmental observation topic | `ENVIRONMENTAL` | `observation_topic` / `OBSERVATION` | 32 | Top-level `ENVIRONMENTAL` type / `ENVIRONMENTAL_EVENT` subtype exist but classify events, not topics | Topic-vs-event distinction; deliberate, namespaced reuse of the name | Additive |
| Procedure violation / nonconformance | `PROCEDURE_VIOLATION` | `event_subtype` / `OBSERVATION` | 29 | None | Genuine finding-type, extends the existing finding vocabulary | Additive |
| Equipment safety topic | `EQUIPMENT_SAFETY` | `observation_topic` / `OBSERVATION` | 13 | Top-level `EQUIPMENT` type exists but classifies maintenance events, not topics | Topic-vs-event distinction | Additive |
| Documentation observation topic | *(none)* | — | 11 | — | Ambiguous, low generalizable HSE value | Documented gap, no concept |
| Fire safety topic | `FIRE_SAFETY` | `observation_topic` / `OBSERVATION` | 4 | None (distinct from the new `FIRE` incident subtype) | Universal HSE topic | Additive |
| Emergency preparedness topic | `EMERGENCY_PREPAREDNESS` | `observation_topic` / `OBSERVATION` | 2 | None | Well-defined, industry-standard HSE management element despite low volume | Additive |
| Working at height topic | `WORKING_AT_HEIGHT` | `observation_topic` / `OBSERVATION` | 128 | `PERMIT`'s `WORK_AT_HEIGHT` exists but is a different domain (a permit record, not an observation topic) | Largest single gap in the real dataset; clear, universal topic | Additive |
| Lifting operations topic | `LIFTING_OPERATIONS` | `observation_topic` / `OBSERVATION` | 31 | `PERMIT`'s `LIFTING_OPERATION` exists but is a different domain | Same reasoning as Working At Height | Additive |

Plus, not in the table above (catch-all terms, never semantically
exact by construction, in either domain): `Others` (Incident) and
`Others` (Observation) — no concept, and none is possible.

**10 new concepts. 5 documented gaps with no new concept.** Every
"Impact" is additive-only: no existing `SafetyEvent`,
`TerminologyMappingDecision`, or intelligence feature reads any of
these new concepts yet (see §10).

## 5. Ontology governance

```
UNKNOWN / QUARANTINED        (existing terminology-mapping lifecycle,
      |                       unchanged)
TERMINOLOGY REVIEW
      |
PROPOSED CANONICAL CONCEPT   propose_concept()  -- OntologyConcept, NEW
      |
ONTOLOGY GOVERNANCE          approve_concept() / reject_concept()
      |
APPROVED CANONICAL CONCEPT   -> DEPRECATED (deprecate_concept(), a
                                 later, separate, explicit step)
```

**Authorization: platform-admin-only.** Every mutating
`ontology_governance_service.py` function calls
`authorization_service.require(..., Permission.GOVERNANCE_MANAGE,
organization_id=None)`. Passing `organization_id=None` is the
mechanism: `AuthorizationService.can()` grants a non-platform-admin
caller nothing once there is no organization to check membership
against, and grants a genuine `PLATFORM_ADMIN` every permission
regardless of the `organization_id` argument. The net effect — 100%
existing authorization code, zero new permission, zero backdoor — is
that **only a human `PLATFORM_ADMIN` may govern the ontology**, exactly
the rule `app/api/v1/knowledge.py` already enforces for writing GLOBAL
knowledge. An organization's own `GOVERNANCE_MANAGE` holder (an
`ORG_ADMIN`) cannot govern the platform-wide ontology through this
service — verified by
`tests/test_ontology_governance.py::test_an_organizations_own_governance_manage_holder_cannot_govern_the_ontology`.

**Never a backdoor around terminology calibration.** Approving an
`OntologyConcept` makes it *exist* — nothing more. It never creates,
proposes, approves, or rejects a `TerminologyMappingDecision`, never
calls `reprocess_quarantined_records()`, and never touches a
`SafetyEvent`.

**Naming rules.** `concept_key` must match `^[A-Z][A-Z0-9_]*$` — the
same convention every existing canonical value already uses,
mechanically enforced. "Not customer-specific, not source-system-
specific, one defined semantic meaning" is enforced by the
platform-admin review this whole module gates, exactly like a
`TerminologyMappingDecision.rationale` string's own quality is never
algorithmically checked, only gated by authorization.

**Durable artifact application & semantic conflict detection** (corrective
commit: "Ontology Artifact Semantic Conflict Detection v0.1").
`backend/config/enterprise_ontology_concepts_v1.json` is applied through
`app/services/ontology_concept_artifact_service.py`, which drives every
`APPROVED` entry through this exact `propose_concept()`/`approve_concept()`
lifecycle — never a second, parallel system. Re-running the apply
function is safe, but safety here means something specific:

> **Artifact application is idempotent only when an existing approved
> concept matches the artifact's semantic definition. A same-key concept
> with conflicting semantic content raises an explicit artifact conflict
> and is not overwritten.**

A same `(layer, parent_domain, concept_key)` scope key is never, by
itself, treated as proof of a same ontology meaning:

- **same key + same meaning** — an existing `APPROVED` concept whose
  `definition`, `ontology_version`, and justification content match the
  artifact entry — a genuine no-op, counted as `already_satisfied`,
  never re-approved, never duplicated;
- **same key + conflicting meaning** — an existing concept at that same
  scope key that is not `APPROVED` (still `PROPOSED`, or terminally
  `REJECTED`/`DEPRECATED`), or is `APPROVED` but whose `definition`,
  `ontology_version`, or justification content differs from the
  artifact — raises `OntologyConceptArtifactConflictError` immediately.
  The existing database row is always left completely untouched: this
  is never resolved automatically in either direction ("database wins"
  and "artifact wins" are both refused) — a human platform administrator
  must resolve the conflict explicitly through the governance service.

This mirrors `terminology_decision_artifact_service.py`'s own
`TerminologyDecisionArtifactConflictError` pattern for the identical
reason: fail loudly rather than silently reinterpret, overwrite, or
bypass an already-governed decision. See
`tests/test_ontology_concept_artifact.py`'s own semantic-conflict,
version-conflict, and REJECTED/DEPRECATED-lifecycle-protection tests for
the verified behavior.

## 6. Versioning

- **`ontology_version`** (an `int` on every `OntologyConcept` row)
  records which SIE Enterprise Ontology version introduced (or, for a
  later status change, last touched) the concept. This milestone is
  **ontology version 1** — the first version of the new *governed
  concept registry*; the pre-existing static ontology
  (`SafetyEventType`/`_SUBTYPE_ALIASES`) predates any version concept
  and is treated as the implicit baseline every version-1 concept is
  additive to.
- **Concept identity**: `(layer, parent_domain, concept_key)`, unique
  and immutable once a row exists (a `UniqueConstraint` on the table
  enforces this at the schema level, independent of status).
- **Lifecycle state**: `PROPOSED -> APPROVED -> DEPRECATED`, or
  `PROPOSED -> REJECTED` — see `app/models/ontology_concept.py`'s own
  docstring for the full state machine and why `PROPOSED`/`REJECTED`
  rows are never deleted.
- **No silent redefinition.** An `APPROVED` concept's `definition` is
  never rewritten in place; a genuinely different definition needs a
  new `concept_key` (mirrors `TerminologyMappingDecision`'s own
  `open_new_version()` discipline — a changed decision gets a new row,
  never an overwritten one).
- **Compatibility considerations**: a `DEPRECATED` concept is no longer
  `is_valid_concept()`-eligible for a *new* terminology-mapping
  decision to target, but nothing retroactively touches any decision or
  event that already used it (there are none yet, in this milestone).
- **Milestone 16 traceability decision — no new column.** A NEW
  `TerminologyMappingDecision` whose canonical target is validated
  against an exact-scope `OntologyConcept` records that concept's `id`
  and `ontology_version` on the decision's existing `provenance` JSON
  column, not a new schema field: `provenance` already carries exactly
  this kind of "which specific governed thing resolved this decision"
  fact (`target_event_subtype`, from the prior milestone), so a second,
  redundant version column would only duplicate that pattern for no
  behavioral gain. **No Alembic migration was required for Milestone
  16** — see §7.

## 7. Terminology mapping relationship

**Before Milestone 16:**

```
Terminology mapping
    ↓
static canonical vocabulary   (SafetyEventType / _SUBTYPE_ALIASES /
                                TRAINING_STATUS_TARGET_FIELDS /
                                MAINTENANCE_STATUS_TARGET_FIELDS --
                                _canonical_terms_for(), unchanged)
```

**After Milestone 16 ("Governed Ontology-to-Terminology Integration &
Controlled Remapping Foundation v0.1"):**

```
Terminology mapping
    ↓
governed APPROVED OntologyConcept   (when one exists at the decision's
    ↓                                 exact scope -- authoritative)
    ↓  (falls back when no exact match exists)
static canonical vocabulary          (unchanged, for every pre-existing
                                       term the ontology does not govern)
```

`app/services/ontology_terminology_integration_service.py::validate_canonical_target(db,
layer=..., parent_domain=..., concept_key=...)` is the deterministic
contract this milestone adds: it answers "is this proposed canonical
mapping target valid against the currently `APPROVED` SIE ontology?"
with exactly one of `VALID` / `NOT_APPROVED` / `NOT_FOUND` /
`WRONG_LAYER` / `WRONG_PARENT_DOMAIN` / `INVALID` — never a bare
boolean, never fuzzy/LLM/semantic inference, every answer an exact-match
lookup against governed `OntologyConcept` rows.

- **Layer semantics (unchanged from §3).** `event_type`,
  `event_subtype`, and `observation_topic` remain three distinct
  dimensions. `PPE_COMPLIANCE` validates at `observation_topic`/
  `OBSERVATION` (`VALID`) and fails at `event_subtype`/`OBSERVATION`
  (`WRONG_LAYER`) — the exact same concept_key, two different answers,
  because the scope key is the triple, never `concept_key` alone.
- **Approval requirement, enforced centrally.** Only
  `OntologyConceptStatus.APPROVED` ever validates. `PROPOSED`,
  `REJECTED`, and `DEPRECATED` concepts at an otherwise-matching scope
  all resolve to `NOT_APPROVED` — never silently treated as usable
  merely because a row exists.
- **Cross-domain protection.** A concept_key that was never governed
  anywhere (e.g. a bare top-level type name reused as a bogus
  event_subtype, like `event_subtype`/`INCIDENT`/`OBSERVATION`) resolves
  `NOT_FOUND` — it was never created, because
  `ontology_governance_service._validate_layer_and_parent_domain()`
  already refuses to let such a concept be *proposed* in the first
  place (§3/§5). `WRONG_LAYER`/`WRONG_PARENT_DOMAIN` catch the case
  where a *legitimately governed* concept_key is requested at the wrong
  scope.
- **Wired into `terminology_calibration_service.approve_mapping()`**,
  for `event_type`/`event_subtype`-domain decisions only
  (`_ontology_scope_for_decision()` maps a decision's `(domain,
  context)` onto the corresponding ontology `(layer, parent_domain)`;
  `training_status`/`maintenance_status` decisions target a
  `SafetyEvent.attributes` field name, not a canonical concept, and stay
  governed by `_canonical_terms_for()` alone, unchanged). The rule
  applied there: if — and only if — an `OntologyConcept` row exists at
  the decision's EXACT scope, that row is authoritative (must be
  `APPROVED`, and the pre-existing static vocabulary is never
  consulted for that term); otherwise, validation falls back to
  `_canonical_terms_for()` exactly as before this milestone.
- **Historical compatibility.** This exact-scope-only rule is what
  keeps a term like the top-level `SafetyEventType` `ENVIRONMENTAL`
  approvable exactly as before, even though a *different*,
  `observation_topic`/`OBSERVATION`-scoped `ENVIRONMENTAL` concept also
  exists: `event_type`/`None`/`ENVIRONMENTAL` has no exact-scope
  `OntologyConcept` row, so it is never treated as ontology-governed —
  the static vocabulary remains authoritative for it, unmutated,
  unreinterpreted. No historical, already-terminal
  `TerminologyMappingDecision` is touched, rewritten, or reinterpreted
  by this milestone in any way; "historically valid under ontology
  version X" is a fact about a row's own frozen history, never
  retroactively recomputed.
- **Ontology version traceability.** When a NEW decision's target *is*
  governed by an exact-scope `OntologyConcept`, `approve_mapping()`
  records that concept's `id` and `ontology_version` (plus `layer` and
  `parent_domain`) onto `decision.provenance` — the same existing JSON
  column `target_event_subtype` already uses, not a new schema column
  (see §6; no migration was required for this milestone). This
  completes the full provenance chain: source term → terminology
  decision → canonical ontology concept → ontology version.
- **Real-enterprise remapping remains deferred.** This milestone makes
  the 10 Milestone 15 concepts *usable* as mapping targets in principle
  — it does not map anything to them. None of the 15 real-dataset terms
  that remain `REJECTED` in
  `backend/config/real_enterprise_terminology_decisions_v1.json` (byte-
  for-byte unchanged by this milestone) are remapped, reopened, or
  auto-approved here. That remains a deliberate, separate, future human
  decision — see §8.

## 8. Rejected terminology treatment (this milestone changes nothing here)

The 15 terminology decisions the corrective commit rejected remain
exactly `REJECTED`, exactly as recorded in
`backend/config/real_enterprise_terminology_decisions_v1.json` (byte-
for-byte unchanged by this milestone — verified by
`tests/test_ontology_real_data_safety.py`). Introducing a new,
`APPROVED` `OntologyConcept` does not, by itself, change any
`TerminologyMappingDecision`'s status, canonical term, or eligibility
for reprocessing. A rejected term "now having a possible canonical
target" (§4's table) is a statement about the *ontology* — that a
concept now exists that *could* someday be targeted — never a
statement about the *terminology decision*, which stays `REJECTED`
until a human, in a future milestone, deliberately reopens it via
`open_new_version()`.

## 9. Backward compatibility

- **Existing canonical values retain their existing meaning.** No
  `SafetyEventType` member, `_SUBTYPE_ALIASES` entry, training/
  maintenance vocabulary value, or `TerminologyMappingDecision` row is
  renamed, removed, or reinterpreted.
- **`terminology_mapping.py` (the ontology alias file) is not modified
  at all** by this milestone — every new concept lives in the new
  `OntologyConcept` table instead.
- **Existing `SafetyEvent` records, approved mappings, and RAG
  provenance are unaffected** — no ingestion, adapter, or reprocessing
  code path was touched.
- **Existing API contracts are unaffected** — no new API router is
  introduced this milestone (explicitly excluded, §18 of the milestone
  spec).
- **The full existing regression suite passes unmodified** — see the
  completion report's test counts.

## 10. Intelligence / predictive compatibility

`app/intelligence/features.py` groups by `event.event_type` (whatever
string is actually present) and reads a small number of specific
`event.event_subtype` string literals for the `training`/`equipment`
domains only — it does not enumerate or depend on the full
`SafetyEventType`/`_SUBTYPE_ALIASES` vocabulary, and none of the new
concepts this milestone introduces are ever written to a `SafetyEvent`
row (no reprocessing occurred; no adapter was changed). **Impact: none,
today.** The new `observation_topic` layer is not read by any feature,
label, dataset-snapshot, drift, anomaly, or RAG-retrieval-filter code
path — there is nothing yet for those to read, since no `SafetyEvent`
carries a topic value. A future milestone that wires `observation_topic`
into ingestion/classification would need to: (a) decide where a topic
value is stored on `SafetyEvent` (a new column, or the existing
`attributes` JSON, mirroring `_terminology_calibration`'s own pattern);
(b) assess whether any existing feature/label definition implicitly
assumed `event_subtype` was the only classification dimension. Neither
decision is made here.

## 11. Examples

```
Approved:   layer=observation_topic  parent_domain=OBSERVATION  concept_key=PPE_COMPLIANCE
Approved:   layer=event_subtype      parent_domain=INCIDENT     concept_key=FIRE
Approved:   layer=event_subtype      parent_domain=OBSERVATION  concept_key=PROCEDURE_VIOLATION

Rejected (never proposed as a concept -- catch-all):
            source term "Others" (event_type domain)      -> no concept
            source term "Others" (event_subtype/OBSERVATION domain) -> no concept, independently scoped

Invalid, refused before any row is created:
            layer=event_subtype  parent_domain=INCIDENT  concept_key=OBSERVATION   (cross-domain)
            layer=event_subtype  parent_domain=INCIDENT  concept_key=PERMIT        (cross-domain)
            layer=event_subtype  parent_domain=NOT_A_TYPE concept_key=X            (unknown parent)

Deliberately valid despite the name collision (different layer/namespace):
            layer=observation_topic  parent_domain=OBSERVATION  concept_key=ENVIRONMENTAL
            (distinct from the top-level ENVIRONMENTAL event_type and the
             INCIDENT subtype ENVIRONMENTAL_EVENT -- never confused, since
             (layer, parent_domain, concept_key) is the real scope key)
```

## 12. Known gaps and limitations (honest, as of this milestone)

1. **Not wired into terminology mapping or ingestion.** `is_valid_concept()`
   exists and is tested, but no terminology-mapping validation function
   calls it yet, and no adapter reads `observation_topic`. This is
   deliberate (§7, §10), not an oversight.
2. **No API router.** Ontology governance is script/service-callable
   only, matching this milestone's explicit scope (no frontend, no new
   API endpoints).
3. **`SecurityBreach`, `HazardObservation`, `Documentation`, and both
   `Others` terms remain genuine, unresolved ontology gaps** — not
   force-fit, not silently dropped, documented in §4 and in the
   artifact's own `justification`/`why_no_new_concept` fields.
4. **`observation_topic` has no storage location on `SafetyEvent` yet**
   — deciding one (new column vs. `attributes` JSON) is left to
   whichever future milestone actually wires this layer into
   classification.
5. **Ontology version 1 covers only this milestone's own 10 concepts.**
   A future ontology-review milestone extending the vocabulary further
   would be ontology version 2, following the same governed
   `propose_concept()`/`approve_concept()` path.

---

*See the durable artifact,
[`backend/config/enterprise_ontology_concepts_v1.json`](../config/enterprise_ontology_concepts_v1.json),
for the full machine-readable justification of every concept and every
documented non-concept; `app/models/ontology_concept.py` and
`app/services/ontology_governance_service.py` for the model and service
this document describes; and `tests/test_ontology_governance.py`,
`tests/test_ontology_concept_artifact.py`,
`tests/test_ontology_real_data_safety.py` for the full, reproducible
test suite this document's claims are verified against.*
