# SIE Field Outcome Foundation v0.1 (SIE Milestone 37)

## 1. What this milestone is

Every SIE intelligence loop before this milestone ended at the human's
decision:

```
OBSERVE -> CAPTURE -> UNDERSTAND -> CONTEXTUALIZE -> REMEMBER -> REASON ->
SIGNAL -> EXPLAIN -> DECIDE -> INTERVENE -> ?
```

SIE Milestone 34 (`IntelligenceDecision`) recorded *what a human decided*
and, optionally, *what intervention resulted* (a reference to an existing
`SafetyAction`). Nothing recorded *what happened as a result of that
intervention*. This milestone closes that gap with one new governed,
append-only record:

```
OBSERVE -> ... -> DECIDE -> INTERVENE -> OUTCOME
```

`IntelligenceOutcome` (`app/models/intelligence_outcome.py`) is that
record. It is deliberately narrow: a ground-truth capture layer, not a
prediction, not a workflow, and not the SIE learning engine.

## 2. What an outcome is

An outcome is a human's own governed statement of *what happened* after
one specific `IntelligenceDecision` — optionally after one specific
`SafetyAction` intervention. The milestone's own worked example:

```
Attention item (HIGH priority)
  -> Human Decision: ACT
  -> SafetyAction: "Install temporary guardrail"
  -> Outcome: EFFECTIVE
  -> Evidence: follow-up observation event confirms no further exposure
```

Each `IntelligenceOutcome` row carries:

| Field                                          | Meaning |
|-------------------------------------------------|---------|
| `decision_id`                                    | The `IntelligenceDecision` this outcome reports the result of (required). |
| `site_id`                                        | Optional, independently supplied — need not match the decision's own site. |
| `linked_action_id`                               | Optional reference to an existing `SafetyAction` — never required, never automatic. |
| `classification`                                 | One of `EFFECTIVE` / `PARTIALLY_EFFECTIVE` / `INEFFECTIVE` / `NO_OUTCOME_RECORDED` (§3). |
| `summary`                                        | Required free text: why the human believes this outcome occurred. |
| `evidence_event_ids`                             | Optional, bounded reference list of existing `SafetyEvent` ids. |
| `outcome_at`                                     | The real-world instant the outcome became observable (§4). |
| `recorded_by_user_id` / `recorded_by_api_client_id` | Exactly one set, derived from `RequestContext`. |
| `created_at`                                     | When this row was written — distinct from `outcome_at` (§4). |

## 3. The outcome taxonomy — deliberately small

Four values, not an open-ended effectiveness scale:

- `EFFECTIVE` — the intervention resolved the condition.
- `PARTIALLY_EFFECTIVE` — some effect, but not full resolution.
- `INEFFECTIVE` — the intervention did not resolve the condition.
- `NO_OUTCOME_RECORDED` — an explicit human statement that no outcome
  could be established (e.g. no follow-up was possible). **This value
  is never produced automatically merely because a decision has no
  recorded outcome.** The absence of any `IntelligenceOutcome` row is a
  different, and far more common, state than a row that exists and says
  this. Adding a fifth member to this enum is a deliberate, reviewed
  code change, not routine data entry — the same discipline every other
  native-enum vocabulary in this codebase already follows.

## 4. `outcome_at` vs. `created_at` — why two timestamps

`outcome_at` is the real-world instant the outcome became
observable/was established (e.g. the date of a day-30 follow-up
inspection). It is always caller-supplied — only the reporting human
knows it — and validated to never be in the future
(`app/services/intelligence_outcome_service.py::reject_future_outcome_at()`):
an outcome describes something that has already happened, never a
forecast.

`created_at` (`TimestampMixin`) is when this row was written to the
database — very often significantly later than `outcome_at`, since
field outcomes are routinely reported well after the fact. This is why
`IntelligenceOutcome` needed this split where `IntelligenceDecision` did
not: a decision is made at the moment it is recorded, so
`IntelligenceDecision.decided_at` has no equivalent gap.

`GET /intelligence/outcomes?as_of=...` filters on **both** columns
(`outcome_at <= as_of AND created_at <= as_of`) — mirroring
`app/intelligence/temporal.py::events_as_of()`'s own `event_time`/
`ingestion_time` dual-timestamp discipline exactly, never a second,
competing temporal framework. The first condition guarantees the
outcome had genuinely happened by `as_of`; the second guarantees it was
already *known* by `as_of` — a backdated `outcome_at` entered after the
fact must not leak into an earlier historical reconstruction merely
because its own `outcome_at` predates `as_of`.

Unlike SIE Milestone 35B/36's history-reconstruction problem
(`SafetyEventProjectAttributionHistory`, `ProjectSiteHistory`),
`IntelligenceOutcome` needed no new `app/intelligence/temporal.py`
helper function at all: outcome rows are themselves already immutable
and append-only (§6), so there is no separate "current state"
representation that could drift out of sync with history. The correct
point-in-time semantics reduce to a direct two-column `WHERE` filter
applied straight in the list query
(`app/api/v1/intelligence_outcomes.py::list_intelligence_outcomes()`).

## 5. Decision relationship — required, schema-hardened

`decision_id` is `NOT NULL`: an outcome never exists as an arbitrary,
unrelated record. It is referenced via a genuine, DB-enforced composite
foreign key, `(decision_id, organization_id) -> intelligence_decisions(id,
organization_id)` — mirroring `project_sites`'/`project_site_history`'s
own SIE Milestone 35A/36 composite-FK hardening exactly (safe here
because `ON DELETE CASCADE` applies: no `SET NULL`/`NOT NULL` conflict).
Migration 0026 adds a new `UNIQUE(id, organization_id)` constraint to
`intelligence_decisions` to support it, identical precedent to
`sites`/`projects`' own SIE Milestone 35A constraint. PostgreSQL itself
rejects a cross-tenant row, not merely a service-layer check — proved by
`tests/test_migrations.py::test_intelligence_outcomes_composite_foreign_key_rejects_cross_tenant_rows_at_the_database_level`.

An `IntelligenceOutcome` row is **never created automatically**. No
route anywhere in this codebase creates one except the one explicit
`POST /intelligence/outcomes` call — never inferred from `SafetyAction.
status` transitioning to `COMPLETED`/`CANCELLED` (closure does not prove
effectiveness — see `app/models/safety_action.py`'s own "Closure
semantics" section, deliberately untouched by this milestone), and never
inferred from the absence of a subsequent `SafetyEvent` at the same
site.

## 6. Action relationship — optional, never forced

`linked_action_id` may be `NULL`: a human may act operationally outside
the `SafetyAction` mechanism entirely and later report the result.
`Decision -> Outcome` with no `SafetyAction` in between is a legitimate,
first-class case — this milestone never forces every outcome through
the action model.

When supplied, it is a plain, single-column foreign key
(`ON DELETE SET NULL`) — **not** composite, for the identical reason
`IntelligenceDecision.linked_action_id` itself already is not composite:
combining a composite FK with `ON DELETE SET NULL` would null every
column in the constraint together, including `organization_id`, which
is `NOT NULL`. Tenant consistency for this reference is enforced by the
one governed write path
(`app/services/intelligence_outcome_service.py::record_outcome()`, via
`app.services.risk_assessment_service.resolve_action_reference()` — the
same reused check `IntelligenceDecision.linked_action_id` and
`RiskAssessmentFinding`'s own finding-action linking already share)
rather than a schema-level guarantee. This is an accepted, documented
limitation matching an already-established precedent, not a new gap
this milestone introduces.

## 7. Site — optional, independently supplied

`site_id` may differ from (or be absent when) the referenced decision's
own `site_id` is set — this milestone does not enforce that the two
match, the same "independently supplied, service-layer tenant-validated"
shape `IntelligenceDecision.site_id` itself already has.

**No project attribution is added anywhere on this table.** If a future
milestone needs project-scoped outcomes, the honest derivation path is
`decision_id -> IntelligenceDecision.site_id` (or `linked_action_id ->
SafetyAction.source_event_id -> SafetyEvent.attributed_project_id`, when
that chain exists) evaluated explicitly at read time — never a new
duplicated `project_id` column inferred automatically from `ProjectSite`
co-location (SIE Milestone 35A already established this can never prove
genuine attribution).

## 8. Evidence — a governed reference, not a new subsystem

`summary` (required) is the human's own account of why they believe
this outcome occurred. `evidence_event_ids` (optional, bounded) is a
reference list of existing `SafetyEvent` ids — mirrors
`IntelligenceDecision.evidence_event_ids`'s own exact shape: a reference
list, never a copy of the referenced rows' content. Each id, when
supplied, is validated at write time via
`app.services.safety_action_service.validate_source_event_reference()`
— no new evidence-ingestion engine, no new provenance table.

## 9. Actor governance and tenant scoping

Identical shape to `IntelligenceDecision`: exactly one of
`recorded_by_user_id`/`recorded_by_api_client_id` is set, derived from
`RequestContext`, never accepted as client input. `request_id` mirrors
`AuditLog.request_id`/`IntelligenceDecision.request_id` exactly.
`OrganizationScopedMixin`, `ON DELETE CASCADE` on `organization_id`.

## 10. Immutability — append-only, no correction workflow

No route ever issues an `UPDATE` against this table. There is no
`PUT`/`PATCH`/`DELETE` endpoint, and none is planned for this milestone.
If a later verification needs to correct or supersede a previously
recorded outcome (e.g. "recorded INEFFECTIVE on day 3, but a day-30
follow-up confirms EFFECTIVE"), the governed mechanism is a **second**
`IntelligenceOutcome` row referencing the same `decision_id` — never an
in-place edit. `GET /intelligence/outcomes?decision_id=...`, ordered
newest-first (`outcome_at DESC, created_at DESC, id DESC`), *is* that
correction history.

This is a deliberate simplicity choice: the milestone spec explicitly
asks that correction be "a new row, not a complex workflow," and this
initial M37 implementation favors that simple append-only model over a
correction workflow with its own status/supersession fields. A future
milestone could add explicit supersession tracking if the append-only
history proves insufficient in practice — nothing here forecloses that,
but nothing here builds it speculatively either.

## 11. API surface

```
POST /api/v1/intelligence/outcomes
GET  /api/v1/intelligence/outcomes
GET  /api/v1/intelligence/outcomes/{outcome_id}
```

No `PUT`/`PATCH`/`DELETE` anywhere (§10).

`GET /intelligence/outcomes` filters: `site_id`, `decision_id`,
`linked_action_id`, `classification`, `as_of` (§4). Ordering:
`outcome_at DESC, created_at DESC, id DESC`.

`POST /intelligence/outcomes` supports `Idempotency-Key` exactly like
every other write route in this codebase
(`app.core.idempotency.compute_request_hash`/`check_and_replay`/
`store_response`).

## 12. Authorization — reuses M34's governance, not a new role

Recording an outcome is the same trusted-authority tier as recording the
decision it reports on, within one continuous
DECIDE -> INTERVENE -> OUTCOME human-governance capability. So
`Permission.INTELLIGENCE_DECISION_WRITE` gates
`POST /intelligence/outcomes` too (granted to the same `HSE_MANAGER`/
`HSE_ANALYST` roles) — this milestone deliberately does not invent a new
`INTELLIGENCE_OUTCOME_WRITE` permission for what is not a genuinely new
capability tier. Both `GET` routes reuse `Permission.INTELLIGENCE_READ`,
identical to every other intelligence read route in this codebase.

## 13. What this milestone explicitly is not

- **Not the SIE learning engine.** No model retraining, feature
  generation, prediction update, adaptive threshold, automatic policy
  change, automatic risk recalculation, automatic attention
  reprioritization, automatic action generation, LLM fine-tuning on
  outcomes, or outcome-based embedding update reads this table. "AI
  learns from feedback" is explicitly out of scope for this milestone.
- **Not an inference mechanism.** `SafetyAction.status = COMPLETED`
  never implies `EFFECTIVE`; the absence of a subsequent `SafetyEvent`
  never implies `EFFECTIVE`. Every `IntelligenceOutcome` row is the
  direct, explicit result of one human `POST /intelligence/outcomes`
  call.
- **Not incident/inspection/permit/corrective-action/contractor/
  training/case/workflow management.** SIE remains the intelligence
  layer; this milestone adds one narrow ground-truth capture table, not
  a field-operations system.
- **Not a frontend feature.** No UI work is part of this milestone.

## 14. The loop, before and after this milestone

Before:

```
OBSERVE -> CAPTURE -> UNDERSTAND -> CONTEXTUALIZE -> REMEMBER -> REASON ->
SIGNAL -> EXPLAIN -> DECIDE -> INTERVENE -> ?
```

After SIE Milestone 37:

```
OBSERVE -> CAPTURE -> UNDERSTAND -> CONTEXTUALIZE -> REMEMBER -> REASON ->
SIGNAL -> EXPLAIN -> DECIDE -> INTERVENE -> OUTCOME
```

A future loop, explicitly **not** part of this milestone:

```
... -> INTERVENE -> OUTCOME -> LEARN
```

`LEARN` — any mechanism that reads `IntelligenceOutcome` rows to adjust
SIE's own models, thresholds, priorities, or generated content — is
deliberately left for a future, separately-scoped and separately-
governed milestone. This milestone only establishes the ground truth
that a future `LEARN` stage would need; it does not build that stage.

## 15. Known limitations (accepted, documented, not gaps)

- `linked_action_id`/`site_id` are service-layer-validated, not
  schema-composite-hardened (§6, §7) — matches `IntelligenceDecision`'s
  own pre-existing, unremarked precedent for the identical shape.
- Correction is a new row, not a formal supersession workflow (§10) —
  a deliberate simplicity choice for this initial implementation.
- No project attribution is derived or stored (§7) — a future milestone
  would need to evaluate the derivation chain explicitly at read time,
  never infer it automatically from `ProjectSite` co-location.
- `evidence_event_ids` is a reference list only; no new evidence
  subsystem or provenance chain beyond the existing `SafetyEvent`
  validation (§8).
