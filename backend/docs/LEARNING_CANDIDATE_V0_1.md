# SIE Learning Candidate Foundation v0.1 (SIE Milestone 39)

## 1. What this milestone is

SIE Milestone 38 let a human judge whether a recorded outcome was
trustworthy (`IntelligenceOutcomeVerification`) and exposed a
deterministic `evaluate_learning_eligibility()` gate — but nothing read
that gate. This milestone is the first thing that does:

```
DECIDE (M34) -> INTERVENE -> OUTCOME (M37) -> VERIFY (M38) -> LEARNING CANDIDATE (this milestone) -> LEARN (M40/M41, not built here)
```

`IntelligenceLearningCandidate` (`app/models/intelligence_learning_
candidate.py`) answers one question: *"may this verified operational
experience be considered by future learning?"* It is still not the SIE
learning engine — see §9. Nothing in this milestone trains, retrains, or
adjusts a model; nothing changes a threshold, a risk score, prediction
logic, ontology, terminology, or any intelligence rule.

## 2. A verified outcome is evidence; a candidate is a governed opinion about its usefulness

These are kept separate deliberately:

- **`IntelligenceOutcome`** (M37) — what a human recorded happened.
- **`IntelligenceOutcomeVerification`** (M38) — whether a human judged
  that recording trustworthy.
- **`IntelligenceLearningCandidate`** (this milestone) — a governed
  representation that this verified experience *may* be useful for
  future learning. Creating one never mutates the outcome or
  verification it derives from — both stay exactly as immutable as
  M37/M38 already made them.

## 3. Eligibility vs. acceptance — two different concepts, never conflated

This is the central distinction M39 spec §8 requires, and it is
architectural, not merely a naming choice:

- **Eligibility** — a deterministic, always-recomputable *system* check:
  "is this verified outcome technically eligible to become a learning
  candidate?" Reuses M38's own `evaluate_learning_eligibility()`
  verbatim as the one write-time gate
  (`intelligence_learning_candidate_service.py::
  create_learning_candidate()`) — never forked, never duplicated. It is
  a write-time gate, not a stored value: `IntelligenceLearningCandidate`
  carries no eligibility column at all, because a candidate's mere
  existence already proves it was eligible at creation time.
- **Acceptance** — a separate, later, *human governance* judgment
  (`ACCEPTED`/`REJECTED`) about a candidate that already exists, made
  independently of eligibility and recorded on its own append-only
  table (`IntelligenceLearningCandidateGovernanceDecision`, §5).

A verified outcome can be technically eligible (and therefore have a
candidate row) without that candidate ever being `ACCEPTED`. Eligibility
answers "can this exist"; acceptance answers "should the organization
actually treat this as learning-worthy."

## 4. The learning-candidate model

`IntelligenceLearningCandidate` — append-only, tenant-scoped, **at most
one row per outcome ever** (§6):

| Field | Meaning |
|-------|---------|
| `outcome_id` | The `IntelligenceOutcome` this candidate derives from (required, composite-FK tenant-hardened). |
| `verification_id` | The exact `IntelligenceOutcomeVerification` row that made this candidate eligible at creation time — **pinned**, never re-pointed later even if a subsequent verification is recorded for the same outcome (composite-FK tenant-hardened). |
| `created_by_user_id` / `created_by_api_client_id` | Exactly one set, derived from `RequestContext`. |
| `request_id` | Mirrors `AuditLog.request_id`/`IntelligenceOutcomeVerification.request_id`. |
| `created_at` / `updated_at` | Standard timestamps. |

No `classification`, `summary`, `evidence_event_ids`, or any other
outcome/verification field is denormalized onto this row (§7).

## 5. Governance decisions — the human layer

`IntelligenceLearningCandidateGovernanceDecision` — append-only,
tenant-scoped, one row per governance judgment:

| Field | Meaning |
|-------|---------|
| `candidate_id` | The candidate this decision governs (composite-FK tenant-hardened). |
| `status` | `ACCEPTED` or `REJECTED` — a deliberately small taxonomy (§3). |
| `rationale` | Required free text: why this judgment was made. |
| `decided_at` | Server-derived (`default=utcnow`) — unlike `outcome_at`/`verified_at`, a governance action has no "I decided this earlier and am filing it late" concept, so no backdating discipline is needed; mirrors `IntelligenceDecision.decided_at`. |
| `decided_by_user_id` / `decided_by_api_client_id` | Exactly one set, derived from `RequestContext`. |

No route ever issues an `UPDATE`/`DELETE` against this table. A
reviewer changing their mind is a **second** row referencing the same
`candidate_id` — never an in-place edit. `resolve_current_governance()`
resolves the single most recent row (`created_at DESC, id DESC`) —
identical rule to M38's own `resolve_current_verification()`. The
*absence* of any governance row for a candidate is its own distinct
initial state ("pending") — deliberately not given its own enum member,
since it is the absence of a row, not a value a row can hold.

## 6. Verification requirement — reused, never forked

A candidate may only be created from an outcome whose *resolved
current* verification (M38's own `resolve_current_verification()`,
unchanged) is `VERIFIED`, and whose evidence independently evaluates as
valid. `INSUFFICIENT_EVIDENCE`, `DISPUTED`, or no verification at all
are all rejected (422) at creation time — the API route never silently
coerces an ineligible outcome into a candidate. This is the exact same
`evaluate_learning_eligibility()` function M38 already exposed but left
unused; M39 is the first (and, deliberately, only) caller.

## 7. Provenance — reused via live joins, never denormalized

`outcome_id` and `verification_id` are both `NOT NULL`, referenced via
*composite* foreign keys `(outcome_id, organization_id)` and
`(verification_id, organization_id)` — mirroring `intelligence_outcomes`/
`intelligence_outcome_verifications`' own M37/M38 composite-FK hardening
exactly. `intelligence_outcome_verifications` gains a new
`UNIQUE(id, organization_id)` constraint in this same migration to
support the second one.

**Why no content is copied onto this row.** Unlike `IntelligenceDecision`'s
own snapshot of "what SIE said" (necessary there because the
*computation* producing an `AttentionItem` is never persisted anywhere
else), `IntelligenceOutcome` and `IntelligenceOutcomeVerification` are
already immutable, already-persisted rows — a live read through
`outcome_id`/`verification_id` returns the identical
classification/`outcome_at`/`evidence_event_ids`/`site_id` forever, so
denormalizing any of it here would be pure redundancy, not a
temporal-integrity requirement. `GET /learning-candidates/{id}` and its
siblings compose this context live via `db.get()` joins, exactly
mirroring `IntelligenceOutcomeRead.decision`/`.linked_action`.

## 8. Evidence revalidation — "verified at time T" vs. "currently revalidated"

Do not assume evidence valid at verification time remains valid
forever, in some abstract sense — but also do not build a second
verification system to track it. Instead, this milestone keeps two
concepts explicitly distinct:

- **"Verified at time T"** — the pinned `verification_id`, a fixed
  historical fact, never re-evaluated.
- **"Currently revalidated"** — a *live*, never-persisted re-run of
  M38's own `evaluate_outcome_evidence()`, exposed only by
  `GET /learning-candidates/{id}/state`.

`state` composes the candidate, its resolved current governance
decision (or `None` — "pending"), and this live evidence re-evaluation
into one response — mirrors `IntelligenceOutcomeVerificationStateRead`'s
own identical shape.

## 9. What this milestone explicitly is not

- **Not the SIE learning engine.** No ML training, no retraining, no
  model-parameter or model-weight changes, no reinforcement learning, no
  online/autonomous learning, no LLM call to determine learning
  eligibility or acceptance.
- **Not automatic mutation of anything downstream.** No automatic change
  to thresholds, risk scores, prediction logic, ontology, terminology
  mappings, organizational configuration, or intelligence rules/signals.
  A candidate — even an `ACCEPTED` one — changes nothing about how SIE
  currently predicts, scores, or reasons.
- **Not organizational memory (M40).** M39 = "this verified operational
  experience is eligible/accepted for future learning." M40 will answer
  a different question: "what does the organization remember from
  accumulated experience?" Not implemented here.
- **Not learning integration (M41).** M41 will answer "how does SIE
  actually use learning signals to improve intelligence?" Not
  implemented here.
- **Not an inference mechanism.** No automatic acceptance/rejection
  inferred from outcome classification, evidence count, or any other
  signal — every governance decision is an explicit, auditable human
  (or credentialed machine) act.
- **Not a new evidence-management platform** — reuses M38's evidence
  evaluation verbatim (§8), never a second implementation.
- **Not incident/inspection/permit/corrective-action/contractor/
  training/case/workflow management.** SIE remains the intelligence
  layer.
- **Not a frontend feature.** No UI work is part of this milestone.

## 10. API surface

```
POST /api/v1/intelligence/learning-candidates
GET  /api/v1/intelligence/learning-candidates
GET  /api/v1/intelligence/learning-candidates/{candidate_id}
POST /api/v1/intelligence/learning-candidates/{candidate_id}/governance-decisions
GET  /api/v1/intelligence/learning-candidates/{candidate_id}/governance-decisions
GET  /api/v1/intelligence/learning-candidates/{candidate_id}/state
```

No `PUT`/`PATCH`/`DELETE` anywhere for either table (§5). `state` is one
read-time composition rather than three separate round trips, mirroring
M38's own `verification-state` endpoint.

Both write routes support `Idempotency-Key` exactly like every other
write route in this codebase.

## 11. Idempotency — two independent guarantees

`POST /learning-candidates` is idempotent **by construction**:
`IntelligenceLearningCandidate` carries a DB-level
`UNIQUE(organization_id, outcome_id)` constraint, so a repeat call for
the same outcome always returns the existing row (`created=False`),
never a duplicate or an error — this holds even without any
`Idempotency-Key` header. Mirrors `ProjectSite`'s own
`(project_id, site_id)` uniqueness precedent exactly. Both write routes
additionally support the `Idempotency-Key` header, guaranteeing exact
response replay on a retried request.

Governance-decision creation deliberately does **not** get natural-key
deduplication: a second, distinct governance action against the same
candidate (e.g. a later reviewer changing an earlier decision) is a
legitimate new row, not a duplicate — only the `Idempotency-Key` header
protects against an accidental literal-duplicate submission there.

## 12. Authorization

Creating a candidate, or recording a governance decision about one, is
the same trusted-authority tier as recording the decision/outcome/
verification that started the chain — so `Permission.
INTELLIGENCE_DECISION_WRITE` gates every write in this router (granted
to the same `HSE_MANAGER`/`HSE_ANALYST` roles), not a new permission or
role. Every read reuses `Permission.INTELLIGENCE_READ`.

## 13. Tenant resolution — one shared implementation, not two

Every handler resolves its operative `organization_id` through
`app.api.deps_context.resolve_authorized_organization_id()` — for a
machine caller, the credential-bound `RequestContext.
machine_organization_id` always wins over the query parameter (and
`authorize_context()` itself already rejects a mismatched query value
before the route is ever reached — see the M38 corrective hardening);
for a human caller, the already-authorized query parameter remains the
only available source, unchanged from every other endpoint in this
codebase. This function was moved from being private to
`intelligence_outcomes.py` to a shared location on `deps_context.py`
during this same milestone specifically so M39 reuses the identical
implementation rather than forking a second copy — tenant selection
itself is not redesigned (M39 spec §14).

## 14. Point-in-time (`as_of`) behavior

`GET .../learning-candidates`, `GET .../governance-decisions`, and
`GET .../state` all accept an optional `as_of`, filtered against
`created_at <= as_of` on the row being listed/resolved — a candidate or
governance decision created after `as_of` never appears. The live
evidence re-evaluation exposed by `state` always reflects the *current*
database state regardless of `as_of` (§8's own "currently revalidated"
is never itself a historical reconstruction).

## 15. Known limitations (accepted, documented, not gaps)

- A candidate carries no numeric "confidence" or priority — governance
  is a binary `ACCEPTED`/`REJECTED` judgment by design, mirroring M38's
  own small, explainable taxonomy instruction.
- Correction (both for candidates — there is none, since a candidate's
  existence is itself immutable and idempotent — and for governance
  decisions) is a new row, not a formal supersession workflow, mirroring
  M37/M38's own identical, deliberate simplicity choice.
- `SUPERSEDED` was considered as a candidate lifecycle state and
  deliberately omitted — no trigger for it exists in this milestone's
  scope (an outcome can only ever have one candidate, so there is
  nothing for a later candidate to supersede).
- Organizational memory (M40) and learning integration (M41) are
  explicitly out of scope — this milestone stops at the governed
  learning-candidate boundary, as instructed.
