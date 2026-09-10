# SIE Outcome Verification & Evidence v0.1 (SIE Milestone 38)

## 1. What this milestone is

SIE Milestone 37 let a human record what happened after a decision/
intervention (`IntelligenceOutcome`). It deliberately never judged
whether that recorded outcome was trustworthy — a human could record
`EFFECTIVE` with zero evidence, and M37 had no opinion on that at all.

This milestone adds the verification layer the loop needed next:

```
DECIDE (M34) -> INTERVENE -> OUTCOME RECORDED (M37) -> VERIFY (this milestone) -> LEARN (M39+, not built here)
```

`IntelligenceOutcomeVerification` (`app/models/intelligence_outcome_
verification.py`) answers one question: *"can this recorded outcome be
trusted?"* It is still not the SIE learning engine — see §9.

## 2. Five separate concepts, never collapsed into one field

1. **What a human recorded** — `IntelligenceOutcome`, unchanged from M37.
2. **What evidence was supplied** — `IntelligenceOutcome.
   evidence_event_ids`, unchanged.
3. **Whether that evidence is structurally/temporally sufficient** — a
   computed, never-persisted evaluation
   (`evaluate_outcome_evidence()`, §5).
4. **Whether a human verified it** — `IntelligenceOutcomeVerification`
   (§3).
5. **Whether the outcome is eligible for future learning** — a computed
   gate (`evaluate_learning_eligibility()`, §7).

An outcome is not automatically truth simply because a human recorded
it (M38 spec §2). This milestone's entire job is keeping these five
things distinct in both the data model and the API.

## 3. The verification model

`IntelligenceOutcomeVerification` — append-only, tenant-scoped, one row
per governance judgment:

| Field | Meaning |
|-------|---------|
| `outcome_id` | The `IntelligenceOutcome` this verifies (required, composite-FK tenant-hardened). |
| `status` | One of `VERIFIED` / `INSUFFICIENT_EVIDENCE` / `DISPUTED` (§4). |
| `rationale` | Required free text: why this judgment was made. |
| `verified_at` | The real-world instant a human actually reviewed the outcome/evidence — caller-supplied, never future. |
| `verified_by_user_id` / `verified_by_api_client_id` | Exactly one set, derived from `RequestContext`. |
| `created_at` | When this row was written — distinct from `verified_at`, mirroring `outcome_at`/`created_at`. |

## 4. The verification taxonomy — deliberately small

Three values, not a confidence scale:

- `VERIFIED` — a human accepts the outcome as trustworthy. Writing this
  value is rejected (422) unless the outcome's own evidence
  deterministically evaluates as fully valid (§5-6) — see §6 for why
  this is necessary but never sufficient.
- `INSUFFICIENT_EVIDENCE` — the supplied evidence (or its absence) does
  not meet the bar for `VERIFIED`. Never implies the outcome itself is
  wrong, only that it is not yet trustworthy enough to rely on.
- `DISPUTED` — a human actively disagrees with the recorded outcome or
  its evidence (e.g. a second reviewer's field check contradicts the
  first report). Distinct from merely insufficient evidence.

## 5. Deterministic evidence evaluation

`evaluate_outcome_evidence()` checks each of an outcome's
`evidence_event_ids` against exactly two fixed timestamps already on
the outcome itself — no fuzzy matching, no LLM, no weighted score:

- `SafetyEvent.event_time <= IntelligenceOutcome.outcome_at` — the
  evidence must have genuinely happened by the time the outcome became
  observable. Reuses `events_as_of()`'s own `event_time` filter, with
  `outcome_at` playing the role `as_of` normally plays.
- `SafetyEvent.ingestion_time <= IntelligenceOutcome.created_at` — the
  evidence must have already been in the system when the outcome was
  recorded. Reuses `events_as_of()`'s own `ingestion_time` filter, with
  `outcome.created_at` playing the role of `as_of`. An event whose
  `event_time` predates `outcome_at` but whose own `ingestion_time`
  postdates the outcome's `created_at` does **not** silently become
  valid historical evidence merely because its `event_time` looks
  right.

Each evidence id is classified **valid**, **invalid** (not found in
this organization, or ingested too late), or **future** (its own
`event_time` is after `outcome_at`). The structural result:

- `NO_EVIDENCE` — `evidence_count == 0`.
- `INVALID_EVIDENCE` — at least one id supplied, none of them valid.
- `INSUFFICIENT_EVIDENCE` — a mix: some valid, some not.
- `VALID_EVIDENCE` — every supplied id is valid.

`evidence_eligible_for_verification` is `True` iff the status is
`VALID_EVIDENCE`.

**Why this is anchored to the outcome alone, never to any one
verification's own `verified_at`.** Once an outcome is created, its
`evidence_event_ids`/`outcome_at`/`created_at` never change (M37's own
immutability), and `SafetyEvent` rows are never deleted or mutated
either — so whether one evidence id is "valid evidence for this
outcome" is a fixed historical fact from the moment the outcome is
created, never a moving target that depends on which verification
later references it. Threading each verification's own (also
caller-supplied) `verified_at` into this check would let the *same*
evidence id evaluate as valid for one verification row and invalid for
another on the identical outcome — an inconsistent, unexplainable
result the spec's own "small and explainable" schema instruction rules
out. `verified_at` therefore governs only that verification row's own
audit trail and `as_of` read-time visibility, never evidence validity.

## 6. "VALID EVIDENCE ≠ VERIFIED OUTCOME"

The central rule this milestone enforces, in both directions:

- Evidence passing `evaluate_outcome_evidence()`'s checks is a
  **necessary** condition for a `VERIFIED` row — the API route rejects
  `status=VERIFIED` (422) when the outcome's evidence does not evaluate
  as `VALID_EVIDENCE`.
- It is never a **sufficient** condition — a human choosing not to
  verify an outcome whose evidence *is* valid is equally legitimate.
  Nothing auto-promotes valid evidence into a `VERIFIED` row.
- The reverse never happens either: no code path infers `VERIFIED` (or
  any other status) merely from evidence being present, from
  `SafetyAction` closure, or from the absence of a subsequent incident.
  `INSUFFICIENT_EVIDENCE`/`DISPUTED` carry no evidence-validity
  requirement at all — a human may record either regardless of what the
  evidence evaluation says.

## 7. Learning eligibility — a gate, not learning

`evaluate_learning_eligibility()` answers one deterministic yes/no
question per outcome, requiring all of:

1. the outcome exists,
2. the outcome is temporally visible as of the given `as_of` (mirrors
   M37's own list-read filter: `outcome_at <= as_of` and
   `created_at <= as_of`),
3. the resolved current verification (§8, as of the same `as_of`) has
   `status == VERIFIED`,
4. the outcome's evidence independently re-evaluates as
   `VALID_EVIDENCE` (defense in depth — redundant with the write-time
   check in §6, at negligible cost, since both are simple, live,
   deterministic recomputations, never cached).

**Nothing reads `.eligible` to actually learn anything.** No model
retraining, feature generation, prediction update, adaptive threshold,
automatic policy change, or embedding update reads this flag. This
remains a distinct, out-of-scope future milestone (M39+, `LEARN`).

## 8. Append-only, deterministic resolution

No route ever issues an `UPDATE` against `intelligence_outcome_
verifications`. There is no `PUT`/`PATCH`/`DELETE` endpoint. A
correction (a reviewer changing their mind, or a second reviewer
disagreeing) is a **second** row referencing the same `outcome_id` —
never an in-place edit.

`resolve_current_verification()` is the one deterministic "resolved
current state" rule: the single most recent row, ordered
`created_at DESC, id DESC` — never an aggregate, a vote, or a weighted
combination of multiple rows. `GET .../verifications`, ordered the same
way, *is* the correction/audit history.

## 9. What this milestone explicitly is not

- **Not the SIE learning engine.** No ML training, no automatic
  learning, no model retraining, no AI-generated outcome conclusions.
- **Not an inference mechanism.** No automatic `EFFECTIVE`/
  `INEFFECTIVE`/`PARTIALLY_EFFECTIVE` determination (that remains M37's
  own human-only judgment); no inference from `SafetyAction` closure
  alone; no inference from absence of incidents alone; no inference
  from subsequent events without an explicit evidence reference.
- **Not fuzzy or AI-assisted evidence matching.** Every check in §5 is
  a plain timestamp/organization comparison. No LLM is invoked
  anywhere in this milestone's code path (verified by a static
  import-audit test — see `tests/test_intelligence_outcome_
  verification_service.py::test_no_llm_or_external_ai_dependency_is_
  used`).
- **Not a new evidence-management platform.** Evidence stays a bounded
  reference list on `IntelligenceOutcome` (unchanged from M37); this
  milestone only adds a read-time evaluation of that list, never a new
  ingestion or storage mechanism.
- **Not incident/inspection/permit/corrective-action/contractor/
  training/case/workflow management.** SIE remains the intelligence
  layer.
- **Not a frontend feature.** No UI work is part of this milestone.

## 10. API surface

```
POST /api/v1/intelligence/outcomes/{outcome_id}/verifications
GET  /api/v1/intelligence/outcomes/{outcome_id}/verifications
GET  /api/v1/intelligence/outcomes/{outcome_id}/verification-state
```

No `PUT`/`PATCH`/`DELETE` anywhere (§8). `verification-state` is one
read-time composition (current resolved verification + live evidence
evaluation + learning-eligibility gate) rather than three separate
round trips — the spec's own "provide an evaluation endpoint if useful,
but do not create redundant APIs" instruction.

`POST .../verifications` supports `Idempotency-Key` exactly like every
other write route in this codebase.

## 11. Authorization

Recording a verification is the same trusted-authority tier as
recording the decision/outcome that started the chain — so
`Permission.INTELLIGENCE_DECISION_WRITE` gates the write (granted to
the same `HSE_MANAGER`/`HSE_ANALYST` roles), not a new permission or
role. Every read reuses `Permission.INTELLIGENCE_READ`, identical to
every other intelligence read route.

## 12. Point-in-time (`as_of`) behavior

`GET .../verifications` and `GET .../verification-state` both accept an
optional `as_of`. A verification recorded after `as_of` never appears
(`created_at <= as_of`), and an outcome not yet visible as of `as_of`
(per M37's own `outcome_at`/`created_at` rule) is excluded from
eligibility the same way M37's own list read already excludes it — one
interpretation of `as_of`, never two. No new `app/intelligence/
temporal.py` helper was needed: both tables are already
immutable/append-only, so point-in-time semantics reduce to direct
column filters.

## 13. Known limitations (accepted, documented, not gaps)

- `verified_at` is not itself a temporal anchor for evidence validity
  (§5) — a deliberate simplification, documented and reasoned through
  explicitly, not an oversight.
- Evidence evaluation has no numeric "confidence" — it is a small,
  explainable, four-value classification by design (spec's own
  instruction against arbitrary weighted scores).
- Correction is a new row, not a formal supersession workflow (§8) —
  mirrors M37's own identical, deliberate simplicity choice.
- The learning-eligibility gate is exposed but unused by any other code
  path in this milestone — that is correct: `LEARN` is explicitly out
  of scope for M38.
