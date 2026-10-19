# Shared Work Handoff — Phase 2 Outcomes/Verification: Owner Authorization Record

**Handoff ID:** SIE-PH2-OV-CONTRACT-2026-10-19-AUTH
**Status:** Boundary and DTO shape **authorized** by the owner. Implementation **not yet authorized** — a separate, explicit go-ahead is required before any code, contract PR, or merge.
**Supersedes (clarifies, does not replace):** [PR #46](https://github.com/Thundhai/SIE/pull/46) — `docs/PHASE2_OUTCOMES_VERIFICATION_CONTRACT_SPEC.md`, `docs/handoffs/2026-10-19-phase2-outcomes-verification-contract-design.md`. PR #46 remains open and **unmerged**; this document does not merge it, alter it, or substitute for it. It records the owner's response to the open questions PR #46 raised.
**Claude Priority 0:** PRESERVE AS ACTIVE, UNINTERRUPTED. Nothing in this document reassigns, pauses, or replaces it.

## What this document is

A durable record of the owner's authorization decisions on PR #46's open questions, so a future implementation task does not need to re-derive or re-ask for them. **This document itself authorizes nothing beyond the boundary/DTO-shape decisions below.** No code, no Commercial Core contract PR, no re-vendoring, and no merge (of PR #46 or anything else) is authorized by this handoff. That requires a separate, explicit instruction from the owner.

## Owner's approved decisions (2026-10-19)

Responding to PR #46 §4 ("Decisions required before approval"):

1. **Boundary authorization — APPROVED.** The owner approves a limited exception in `Thundhai/SIE-Commercial-Core/docs/BOUNDARY_DECISIONS.md` admitting factual, human-authored Outcome/Verification governance records into `sie-contract`, despite the learning loop's current `REVIEW_REQUIRED` status. This exception covers only the four DTOs below — it does **not** extend to the learning loop, evidence-evaluation mechanics, learning-eligibility gating, or any model/scoring data, which stay excluded.
2. **`NO_OUTCOME_RECORDED` semantics — CLARIFIED.** This is an explicit, human-recorded classification meaning a reviewer affirmatively could not establish an outcome. It is **not** an automatic or inferred state for a missing record. The absence of an Outcome record remains absence (no row, no DTO instance) — it must never be synthesized as a `NO_OUTCOME_RECORDED` value. Implementation must keep this distinction enforceable (e.g. the enum value is only ever set by an explicit write, never defaulted).
3. **Actor identity — CONDITIONALLY APPROVED.** `actor_type` + opaque `actor_id` is accepted in principle, aligned with the existing `DecisionReferenceDTO` convention (not `actor_reference` as PR #46's draft spec named it — the implementation task must validate the exact field name and type against `DecisionReferenceDTO` and `sie_contract.tenancy.ActorType` before finalizing, and confirm no drift between the two DTOs' actor representations).
4. **Evidence references — APPROVED.** Restricted to `EvidenceType.SAFETY_EVENT` only, using the existing `EvidenceReference` shape from `sie_contract.common`. No new evidence-reference type without a demonstrated need.
5. **Temporal semantics — APPROVED.** Timezone-aware UTC timestamps throughout; `outcome_at`/`verified_at` (event/review time) kept distinct from `recorded_at` (persistence time) on both DTOs.
6. **Append-only history — APPROVED.** No update/PATCH DTO, no mutable status, no implicit supersession. A correction or re-review is a new record.
7. **Version — APPROVED.** Target `sie-contract 0.6.0` (additive, per current 0.x policy), only after the Commercial Core contract PR is itself reviewed and merged.
8. **Combined verification-state DTO — still deferred**, per PR #46 §3.5. Not part of this authorization.
9. **Consumer/adapter/endpoint/UI wiring — still a separate, later, explicitly-allocated task**, per PR #46 §4 item 7 and the out-of-scope list below.

## Authorized DTO shapes (for the future implementation task)

These refine PR #46's draft field tables with the owner's decisions above. The implementation task must re-validate every field against current contract source before writing code (see "Pre-implementation checklist" below) — this table is the authorized *target*, not a substitute for that check.

### `OutcomeReferenceDTO`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | |
| `organization_id` | `UUID` | |
| `decision_id` | `UUID` | |
| `classification` | contract-owned closed enum | `EFFECTIVE`, `PARTIALLY_EFFECTIVE`, `INEFFECTIVE`, `NO_OUTCOME_RECORDED` — see clarification above; mirror the Commercial Core enum's four values, do not import it directly |
| `summary` | `str`, 1–4000 chars | non-empty, human-authored |
| `site_id` | `UUID \| None` | |
| `linked_action_id` | `UUID \| None` | |
| `evidence` | `list[EvidenceReference]` | restricted to `EvidenceType.SAFETY_EVENT` |
| `outcome_at` | tz-aware UTC `datetime` | event time |
| `recorded_at` | tz-aware UTC `datetime` | persistence time |
| `actor_type` | existing `ActorType` | |
| `actor_id` | `UUID` | opaque; validate against `DecisionReferenceDTO` convention |

### `OutcomeListResultDTO`
`items: list[OutcomeReferenceDTO]`, `total`, `page`, `page_size` — same envelope convention as `DecisionListResultDTO`.

### `OutcomeVerificationReferenceDTO`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | |
| `organization_id` | `UUID` | |
| `outcome_id` | `UUID` | |
| `status` | contract-owned closed enum | `VERIFIED`, `INSUFFICIENT_EVIDENCE`, `DISPUTED` |
| `rationale` | `str`, 1–4000 chars | non-empty, human-authored |
| `verified_at` | tz-aware UTC `datetime` | review time |
| `recorded_at` | tz-aware UTC `datetime` | persistence time |
| `actor_type` | existing `ActorType` | |
| `actor_id` | `UUID` | opaque |

**Excluded from both DTOs:** evidence-evaluation details, `LearningEligibility` and its reasons, private learning gates, confidence/scoring, model internals, raw ORM fields, and any combined verification-state DTO.

### `OutcomeVerificationListResultDTO`
`items: list[OutcomeVerificationReferenceDTO]`, `total`, `page`, `page_size`.

## Contract source and release rules (for the future implementation task)

- All contract changes originate in `Thundhai/SIE-Commercial-Core/sie-contract/`. Never hand-edit `Thundhai/SIE/backend/vendor/sie_contract/`.
- No imports of private `app.*` modules from the contract package.
- Update contract `VERSION`, package metadata, README changelog, and `docs/BOUNDARY_DECISIONS.md` (recording the limited exception from decision 1 above) in the same contract PR.
- Preserve the existing `EvidenceReference` shape — do not duplicate it.
- Add contract-owned enums; do not import Commercial Core's application-model enums directly.

## Mandatory tests (for the future implementation task)

DTO serialization/validation; frozen/immutable behavior; both list envelopes and pagination bounds; every approved enum value including `NO_OUTCOME_RECORDED`'s explicit-only semantics; SafetyEvent-only evidence references; UTC-aware and event-vs-persistence timestamp distinctness; absence of private evaluation/learning/scoring/model/ORM/raw-internal-ID fields; contract import isolation from `app.*`; compatibility with existing contract conventions (`DecisionReferenceDTO`, `EvidenceReference`, `ActorType`).

## Controlled re-vendoring (only after the Commercial Core contract PR is reviewed, approved, and merged)

1. Record the exact approved Commercial Core source commit.
2. Re-vendor into `Thundhai/SIE/backend/vendor/sie_contract/` from that commit only.
3. Update `backend/vendor/sie_contract/PROVENANCE.json` atomically: source commit, version, vendored date, tree hash.
4. Run the vendored-contract integrity tests and relevant Public SIE tests/CI.

## Explicitly out of scope (unchanged from PR #46)

Endpoint/adapter wiring; UI activation; database migrations; Organizational Memory/Learning Candidate exposure; evidence-evaluation or learning-eligibility exposure; model/recommendation/prediction changes or changes to M43A–C6; any interruption, reassignment, or replacement of the active Priority 0 task.

## Pre-implementation checklist (before writing any code)

- [ ] Re-confirm `DecisionReferenceDTO`'s exact actor field name/type in current `sie_contract.decisions` (validate decision 3 above).
- [ ] Re-confirm the four Commercial Core outcome-classification enum values and the three verification-status values against current `app/models/intelligence_outcome_enums.py` / `intelligence_outcome_verification_enums.py` (do not trust this document's copy if the source has moved).
- [ ] Re-confirm current vendored `sie_contract` version/provenance on `main` (do not assume 0.5.0 is still current).
- [ ] Re-check PR #46 and this document's own branch state — do not assume either is still in the state described here.

## Completion criteria for this handoff

This document is complete as an **authorization record** once committed. It does not complete Phase 2, does not implement anything, and does not authorize an implementation task to begin on its own — the owner's separate, explicit go-ahead is still required, per the instruction that produced this document.

## Status

- [x] Owner authorization decisions recorded (this document).
- [ ] Explicit owner go-ahead to begin implementation — **pending**.
- [ ] Commercial Core `sie-contract` 0.6.0 PR — not started.
- [ ] Public SIE re-vendoring — not started.
- [ ] Endpoint/adapter/UI wiring — not started (separate future task).
