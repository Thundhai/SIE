# SIE Organizational Memory Architecture v0.1 (SIE Milestone 40)

## 1. What organizational memory is

SIE Milestone 39 established the governed entry boundary into `LEARN`:
a verified outcome could become an `IntelligenceLearningCandidate`, and
a human could separately judge it `ACCEPTED` or `REJECTED`. Nothing
downstream of that acceptance existed yet — an `ACCEPTED` candidate sat
there, eligible in principle, consumed by nothing.

This milestone adds the next layer the loop needs:

```
DECIDE (M34) -> INTERVENE -> OUTCOME (M37) -> VERIFY (M38)
   -> LEARNING CANDIDATE (M39) -> ACCEPTED (M39 governance)
      -> ORGANIZATIONAL MEMORY (this milestone) -> LEARN (M41, not built here)
```

`OrganizationalMemory` (`app/models/organizational_memory.py`) answers
one question: *"what durable knowledge does this organization choose to
remember from this accepted experience?"* It is a small, explicit,
human-authored knowledge statement — a governed record of *"experience
that became organizational knowledge,"* not *"everything that happened
in the organization."*

## 2. What organizational memory is not

- **Not a copy of all historical events.** It contains no denormalized
  event/incident data — see §8.
- **Not an incident register, inspection register, or HSE case-management
  system.** SIE already has those underlying operational sources; this
  milestone adds nothing that duplicates them.
- **Not a document-management system or a generic JSON archive.** The
  schema is small and explicit (§7), not an unrestricted content blob.
- **Not a vector database of everything**, and not semantic/vector
  retrieval at all yet — reads are deterministic filters (organization,
  memory type, `as_of`, pagination), never similarity search. That
  remains a choice for `M41` to make, once it decides how memory
  participates in intelligence reasoning.
- **Not an automatic collection of every outcome, or every accepted
  learning candidate.** Every `OrganizationalMemory` row is the direct,
  explicit result of one `POST /intelligence/organizational-memory`
  call — nothing creates one automatically merely because a candidate
  became `ACCEPTED`.
- **Not an automatic ML training dataset**, and not itself training
  anything.
- **Not a second source of truth for operational records.** `Intelligence
  Outcome`/`IntelligenceOutcomeVerification` remain the sole record of
  what happened and whether it was trusted; memory only references them.

## 3. Relationship to M37 (Field Outcome Foundation)

`IntelligenceOutcome` is the ground-truth record of what a human
observed after a decision/intervention. Organizational memory never
duplicates this content — it is reached only by following
`OrganizationalMemory.learning_candidate_id ->
IntelligenceLearningCandidate.outcome_id -> IntelligenceOutcome`, a live
reference, never a copy.

## 4. Relationship to M38 (Outcome Verification & Evidence)

`IntelligenceOutcomeVerification` is the human judgment of whether an
outcome is trustworthy. A memory's provenance chain passes through the
*specific* verification that made its originating candidate eligible
(`IntelligenceLearningCandidate.verification_id`, pinned since M39) —
so a memory's authority is traceable all the way back to a specific,
named verification decision, never merely "some verification exists."

## 5. Relationship to M39 (Learning Candidate Foundation)

This is the most important boundary this milestone draws, and it is
enforced in code, not merely documented (M40 spec §5):

**Only an `ACCEPTED` learning candidate may become organizational
memory.** `app/services/organizational_memory_service.py::
create_organizational_memory()` reuses M39's own
`resolve_current_governance()` verbatim (never forked) to resolve the
candidate's *current* governance state, and rejects (422) unless that
state is `ACCEPTED`:

- A **pending** candidate (no governance decision has ever been
  recorded) is rejected.
- A **`REJECTED`** candidate is rejected.
- A candidate that does not exist, or belongs to another organization,
  is rejected (404) before the governance check is even reached.

The full structurally-enforceable chain:

```
IntelligenceOutcome
    -> IntelligenceOutcomeVerification
        -> IntelligenceLearningCandidate
            -> latest governance decision == ACCEPTED
                -> OrganizationalMemory
```

Creating a memory never mutates the candidate or its governance
history — both remain exactly as immutable as M39 already made them
(verified by `tests/test_organizational_memory_service.py::
test_creating_a_memory_never_mutates_the_originating_candidate_or_its_governance`).

## 6. Memory vs. learning candidate vs. learning integration

Three questions, three milestones, never collapsed into one model:

- **M39 — Eligibility/acceptance:** *"May this verified experience be
  considered for future learning, and has a human accepted it as
  such?"*
- **M40 — Organizational memory (this milestone):** *"What durable
  organizational knowledge does the organization choose to remember
  from this accepted experience?"*
- **M41 — Learning integration (not built here):** *"How does SIE
  actually use that remembered knowledge to improve intelligence?"*

`OrganizationalMemory` and `IntelligenceLearningCandidate` live on
entirely separate tables. A candidate can be `ACCEPTED` without a
memory ever being created from it (an authorized actor may simply
choose not to compose a knowledge statement) — acceptance is necessary,
never sufficient, for memory to exist.

## 7. The memory representation — deliberately small, explicit fields

`OrganizationalMemory` — append-only, tenant-scoped, at most one row
per learning candidate:

| Field | Meaning |
|-------|---------|
| `learning_candidate_id` | The `IntelligenceLearningCandidate` this memory derives from (required, composite-FK tenant-hardened). |
| `memory_type` | One of a small, closed taxonomy (§8). |
| `title` | A short, human-scannable label. |
| `memory_content` | The explicit knowledge statement itself — see §9. |
| `rationale` | Why this statement was judged worth remembering. |
| `created_by_user_id` / `created_by_api_client_id` | Exactly one set, derived from `RequestContext`. |
| `created_at` / `updated_at` | Standard timestamps — see §10 for `as_of` semantics. |

No `event_type`, `event_subtype`, `evidence_event_ids`, or any other
`SafetyEvent`/`IntelligenceOutcome` field is denormalized here.

## 8. The memory-type taxonomy — deliberately small, and deliberately *not* ontology-backed

Five values:

- `LESSON_LEARNED` — a general takeaway, applicable beyond the single
  originating outcome.
- `EFFECTIVE_PRACTICE` — a specific approach/control that worked and is
  worth repeating.
- `FAILED_APPROACH` — a specific approach/control that did not work,
  worth avoiding.
- `EARLY_WARNING_PATTERN` — a recognizable precursor pattern worth
  watching for.
- `CONTROL_INSIGHT` — an insight about the adequacy/gap of an existing
  control.

**Why this is a plain, closed Python/DB enum, never an `OntologyConcept`.**
`OntologyConcept`'s `layer` values (`event_type` / `event_subtype` /
`observation_topic`) classify *what happened in the operational world*
— the same axis `SafetyEvent.event_type`/`event_subtype` already uses.
`OrganizationalMemoryType` classifies a completely orthogonal axis:
*what epistemic kind of knowledge statement this memory is* — a
property of the memory record itself, independent of which operational
concept the underlying outcome touched. Routing it through
`OntologyConcept` would conflate two unrelated classification systems
and let an ontology governance action accidentally add or remove valid
memory categories — a capability nobody has asked for. This mirrors the
established precedent of `IntelligenceOutcomeClassification` and
`IntelligenceLearningCandidateGovernanceStatus`: small, closed,
non-ontology-backed enums for their own milestones' own record-shape
concepts.

## 9. Memory content is explicitly authored, never LLM-generated

A memory is not simply "Outcome X happened" — it is meant to capture
organizational knowledge (e.g. *"Repeated permit deviations during
simultaneous operations indicate that permit verification should occur
before the coordination meeting,"* not *"Permit-related intervention
occurred on Project A"*). But M40 does not use any AI/LLM to compose,
summarize, or infer that statement. `memory_content` and `rationale`
are ordinary required string fields on `OrganizationalMemoryCreate`
(schema-validated non-empty) — the system stores the organization's own
knowledge statement; it never invents one. A static import-audit test
(`test_no_llm_or_ml_dependency_is_used`) confirms no LLM/ML-provider
import exists anywhere in this milestone's write path.

## 10. Provenance and traceability

`GET /intelligence/organizational-memory/{id}` composes, in one
response, the full one-hop provenance chain:

```
Memory -> Learning Candidate -> Outcome + Verification
```

reusing `IntelligenceLearningCandidateOutcomeRead`/
`IntelligenceLearningCandidateVerificationRead` directly from M39's own
schema module rather than redefining an equivalent shape. The
decision/intervention/evidence chain beyond that (M34's own
`IntelligenceDecision`, `SafetyAction`, and the underlying
`SafetyEvent` evidence rows) remains reachable by following the
outcome's own `decision_id` against the existing M34/M37 endpoints —
never duplicated here. A user can always answer *"why does SIE remember
this?"* by following this one response plus, if needed, one further
hop.

## 11. Immutability and correction

No route ever issues an `UPDATE` against `organizational_memories`.
There is no `PUT`/`PATCH`/`DELETE` endpoint. The knowledge statement a
memory records is a historical fact about what the organization chose
to remember at creation time — not a living document.

If a memory later turns out to be outdated or wrong, that is recorded
as a new, append-only row on the separate
`OrganizationalMemoryGovernanceDecision` table
(`ACTIVE`/`RETRACTED`) — never as a silent edit or deletion of the
original statement. `resolve_current_memory_governance()` is the one
deterministic "resolved current state" rule: the single most recent
row, ordered `created_at DESC, id DESC` — identical to M38's/M39's own
resolution rule. The *absence* of any governance row is the memory's
own implicit `ACTIVE` state (unlike M39's candidates, whose absence of
governance means "pending": a memory is already the direct output of a
human's deliberate authoring act, so it is authoritative from creation
— there is no separate "should this even exist" step still pending).

## 12. Tenant model

Identical to every prior milestone in this chain: `OrganizationScopedMixin`,
`ON DELETE CASCADE` on `organization_id`, and a genuine, DB-enforced
composite foreign key `(learning_candidate_id, organization_id) ->
intelligence_learning_candidates(id, organization_id)` — a plain
single-column FK on `learning_candidate_id` alone would happily accept
a cross-tenant candidate; the composite FK cannot (proven at the
database level, bypassing the service layer entirely, by
`tests/test_migrations.py::
test_organizational_memory_composite_foreign_key_rejects_cross_tenant_rows_at_the_database_level`).
Machine callers remain credential-bound to their own organization;
human callers use the existing authorized organization-selection
mechanism — both resolved through the shared
`app.api.deps_context.resolve_authorized_organization_id()`, never a
new or forked tenant-resolution path.

## 13. Temporal / `as_of` semantics

`GET .../organizational-memory`, `GET .../governance-decisions`, and
`GET .../state` all accept an optional `as_of`, filtered against
`created_at <= as_of` on the row being listed/resolved. A memory or
governance decision created after `as_of` never appears — there is no
attempt to reconstruct what the *current* memory state would have
looked like at an earlier moment; `as_of` filters strictly on when each
row was actually written, exactly mirroring M38/M39's own `as_of`
discipline.

## 14. Authorization

Creating a memory, or recording a governance decision about one, is the
same trusted-authority tier as accepting the learning candidate that
made it possible — so `Permission.INTELLIGENCE_DECISION_WRITE` gates
every write in this router (granted to the same `HSE_MANAGER`/
`HSE_ANALYST` roles), not a new permission or role. Every read reuses
`Permission.INTELLIGENCE_READ`, identical to every other intelligence
read route.

## 15. Idempotency

`OrganizationalMemory` carries a DB-level `UNIQUE(organization_id,
learning_candidate_id)` constraint — idempotent by construction,
mirroring `IntelligenceLearningCandidate`'s own `UNIQUE(organization_id,
outcome_id)` precedent exactly: at most one memory per accepted
candidate, ever. A repeat `POST /organizational-memory` for the same
candidate returns the existing row (`created=False`), never a duplicate
or an error. This reflects a deliberate choice: one accepted candidate
represents one governed experience, and that experience earns exactly
one canonical memory record (which may later be elaborated via a
governance decision — e.g. `RETRACTED` — but never duplicated as a
second, competing memory for the same candidate). Both write routes
additionally support the standard `Idempotency-Key` header, guaranteeing
exact response replay on a retried request. Governance-decision
creation deliberately does **not** get natural-key deduplication: a
second, distinct governance action (e.g. later retracting, or later
reinstating, a memory) is a legitimate new row, not a duplicate.

## 16. API surface

```
POST /api/v1/intelligence/organizational-memory
GET  /api/v1/intelligence/organizational-memory
GET  /api/v1/intelligence/organizational-memory/{memory_id}
POST /api/v1/intelligence/organizational-memory/{memory_id}/governance-decisions
GET  /api/v1/intelligence/organizational-memory/{memory_id}/governance-decisions
GET  /api/v1/intelligence/organizational-memory/{memory_id}/state
```

No `PUT`/`PATCH`/`DELETE` anywhere for either table (§11). `state` is
one read-time composition (memory + resolved current governance) rather
than two separate round trips, mirroring M39's own `state` endpoint.

## 17. What M41 is expected to consume

M40 establishes clean, deterministic read semantics precisely so a
future `M41` can consume them without redesigning this layer:

- `GET /organizational-memory` filtered by organization, `memory_type`,
  and `as_of`, paginated — a stable list `M41` can iterate.
- `GET /organizational-memory/{id}` and `/state` — a single memory's
  full provenance chain and current governance status, for whatever
  consumption `M41` designs (e.g. only ever reading `ACTIVE` memories).
- The `memory_type` taxonomy itself, as a stable categorical signal
  `M41` may choose to weight or filter on.

M40 makes no commitment about *how* `M41` will use any of this —
semantic retrieval, feature engineering, prompt context, or something
else entirely remain open questions for that milestone.

## 18. Explicit deferred capabilities

- Semantic/vector retrieval over memory content (§2) — not built; may
  or may not be needed depending on what `M41` decides.
- Any mechanism that reads organizational memory to actually change
  SIE's intelligence (predictions, thresholds, risk scores, ontology,
  terminology, rules) — entirely `M41`'s job, not started here.
- A confidence/quality score on memory — deliberately omitted (M40 spec
  §19); a memory's authority is definitionally the chain of verified
  outcome + accepted candidate + explicit authored statement +
  provenance + governance, not a numeric estimate.
- Automatic memory creation from every accepted candidate — deliberately
  not built; every memory is the explicit result of one authorized
  actor's own `POST` call (verified by
  `tests/test_organizational_memory_api.py::
  test_accepting_a_candidate_never_automatically_creates_a_memory`).

SIE does not yet "learn" from organizational memory. This milestone
only establishes what the organization has chosen to remember, and how
to retrieve it deterministically.
