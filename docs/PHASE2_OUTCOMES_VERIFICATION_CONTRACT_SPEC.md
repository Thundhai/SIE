# Phase 2 Contract Design — Outcomes and Verification

**Status:** Draft for architecture review — not approved for implementation  
**Date:** 2026-10-19  
**Scope:** Shared DTO design only for Public SIE ↔ Private Commercial Core.  
**Out of scope:** Runtime DTO implementation, adapters/routes, client integration, UI activation, database changes, learning, or deployment.

## 1. Recommendation

Design an additive `sie-contract` 0.6.0 release with narrow DTOs for factual, human-authored Outcome and Verification governance records. Do not mirror internal ORM models or internal HTTP schemas field-for-field.

This requires an explicit boundary decision before implementation. Current Commercial Core boundary documentation says the learning loop—including outcomes and verification—is excluded from the shared contract pending deliberate review. This draft proposes a limited exception for factual governance records only. It does **not** propose exposing the learning loop, evidence-evaluation mechanics, learning-eligibility gate, or algorithmic decision criteria.

No implementation is authorized until the owner approves the boundary decision and field set.

## 2. Audit basis and current-state findings

Inspected the following current files on repository `main` on 2026-10-19:

- Public SIE `backend/app/schemas/intelligence_outcome.py` — create/read/list HTTP shapes; tenant context and actor IDs are excluded from client write payloads.
- Public SIE `backend/app/schemas/intelligence_outcome_verification.py` — verification create/read/list plus evidence evaluation, learning eligibility, and composed verification state.
- Commercial Core `app/models/intelligence_outcome.py` and `app/models/intelligence_outcome_enums.py` — outcomes are explicit, append-only records; classifications are `EFFECTIVE`, `PARTIALLY_EFFECTIVE`, `INEFFECTIVE`, and `NO_OUTCOME_RECORDED`.
- Commercial Core `app/models/intelligence_outcome_verification_enums.py` — verification statuses are `VERIFIED`, `INSUFFICIENT_EVIDENCE`, and `DISPUTED`; evidence evaluation is separately classified.
- Commercial Core `app/services/intelligence_outcome_service.py` and `app/services/intelligence_outcome_verification_service.py` — explicit writes, tenant-scoped reference resolution, future-timestamp rejection, deterministic evidence evaluation.
- Commercial Core `sie-contract/src/sie_contract/decisions.py`, `common.py`, `tenancy.py`, and `README.md` — DTO conventions, `EvidenceReference`, actor types, UTC timestamps, frozen models, organization scope, and versioning rules.
- Commercial Core `docs/BOUNDARY_DECISIONS.md` and `docs/PUBLIC_SIE_MIGRATION_MAP.md` — current boundary says Outcome/Verification contract exposure remains `REVIEW_REQUIRED`.
- Public SIE `backend/vendor/sie_contract/PROVENANCE.json` — vendored contract is **0.5.0**, sourced from Commercial Core commit `8a63aa77784508b5e9bcec94a5febaaacff7564e`. Public vendor files must not be edited independently.

Source links:
- [Outcome HTTP schema](https://github.com/Thundhai/SIE/blob/main/backend/app/schemas/intelligence_outcome.py)
- [Verification HTTP schema](https://github.com/Thundhai/SIE/blob/main/backend/app/schemas/intelligence_outcome_verification.py)
- [Outcome model](https://github.com/Thundhai/SIE-Commercial-Core/blob/main/app/models/intelligence_outcome.py)
- [Verification service](https://github.com/Thundhai/SIE-Commercial-Core/blob/main/app/services/intelligence_outcome_verification_service.py)
- [Shared contract README](https://github.com/Thundhai/SIE-Commercial-Core/blob/main/sie-contract/README.md)
- [Boundary decisions](https://github.com/Thundhai/SIE-Commercial-Core/blob/main/docs/BOUNDARY_DECISIONS.md)
- [Public migration map](https://github.com/Thundhai/SIE-Commercial-Core/blob/main/docs/PUBLIC_SIE_MIGRATION_MAP.md)

### Audit conclusion

The domain records and HTTP schemas exist, but their full field sets are not automatically safe shared-contract DTOs. The contract-design gap is a boundary/governance decision plus a minimal external schema, not a request to copy internal models. Phase 2 remains open; this draft is not an implemented contract or an end-to-end feature.

## 3. Proposed DTO set

Use frozen Pydantic models, keyword construction, explicit UTC timestamps, organization scope on every organization-scoped fact, and specialized list envelopes matching `items/total/page/page_size`.

### 3.1 `OutcomeReferenceDTO`

| Field | Proposed type | Required | Rationale |
|---|---|---:|---|
| `id` | UUID | Yes | Opaque reference to the outcome record. |
| `organization_id` | UUID | Yes | Explicit tenant scope; never inferred from the parent response. |
| `decision_id` | UUID | Yes | Links the outcome to the decision it reports on. |
| `classification` | Closed enum, pending approval | Yes | Human-recorded outcome classification; consumers must not infer effectiveness. |
| `summary` | string (max 4,000) | Yes | Human-authored explanation. |
| `site_id` | UUID or null | Yes | Optional site scope; no site label or join data. |
| `linked_action_id` | UUID or null | Yes | Optional existing action reference; not proof of causation. |
| `evidence` | list of `EvidenceReference` | Yes | Restrict to resolvable public SafetyEvent references; never internal ID arrays or event payloads. |
| `outcome_at` | datetime | Yes | UTC instant outcome became observable; distinct from persistence time. |
| `recorded_at` | datetime | Yes | UTC instant record was persisted. |
| `actor_type` | existing actor enum | Yes | Human or authorized machine actor. |
| `actor_reference` | UUID | Yes | Opaque actor reference subject to tenant authorization. |

Exclude ORM fields, raw user/API-client column names, site labels, full Decision/Action payloads, evidence-evaluation details, learning eligibility, prediction/model fields, internal request IDs, database/audit implementation details, and mutable correction/supersession state.

### 3.2 `OutcomeListResultDTO`

Frozen specialized envelope: `items: list[OutcomeReferenceDTO]`, `total >= 0`, `page >= 1`, `page_size >= 1`. Follow `DecisionListResultDTO`; do not introduce a second pagination vocabulary.

### 3.3 `OutcomeVerificationReferenceDTO`

| Field | Proposed type | Required | Rationale |
|---|---|---:|---|
| `id` | UUID | Yes | Opaque reference to one append-only verification record. |
| `organization_id` | UUID | Yes | Explicit tenant scope. |
| `outcome_id` | UUID | Yes | Links verification to its outcome. |
| `status` | Closed enum, pending approval | Yes | Human judgment: VERIFIED, INSUFFICIENT_EVIDENCE, or DISPUTED. |
| `rationale` | string (max 4,000) | Yes | Human-authored explanation. |
| `verified_at` | datetime | Yes | UTC instant review occurred; distinct from persistence time. |
| `recorded_at` | datetime | Yes | UTC persistence time. |
| `actor_type` | existing actor enum | Yes | Human or authorized machine actor. |
| `actor_reference` | UUID | Yes | Opaque actor reference subject to authorization. |

Exclude `EvidenceEvaluation` internals (counts, reasons, temporal-validation categories), `LearningEligibility` and its reasons, private learning gates, confidence/scoring, model internals, and full outcome/evidence payloads. Do not mirror `IntelligenceOutcomeVerificationStateRead` wholesale: it combines candidate governance records with internal evaluation and learning-gate details.

### 3.4 `OutcomeVerificationListResultDTO`

Frozen specialized envelope with `items: list[OutcomeVerificationReferenceDTO]`, `total >= 0`, `page >= 1`, and `page_size >= 1`.

### 3.5 No combined verification-state DTO in this release

Do not add a shared DTO for composed verification state yet. If a consumer later needs an aggregate, define it through a separate boundary decision with explicit field-level redaction and acceptance criteria.

## 4. Decisions required before approval

1. **Boundary authorization:** Approve/reject the limited exception allowing factual Outcome/Verification records in `sie-contract` despite the current documented exclusion of the learning loop. If approved, update Commercial Core `docs/BOUNDARY_DECISIONS.md` in the contract-origin PR.
2. **Classification typing:** Recommendation: closed enums for the deliberately small current vocabularies. Adding a member must be a deliberate coordinated versioning event under the current contract policy.
3. **Actor identity:** Confirm `actor_type + actor_reference` works across both repositories; do not copy database-specific actor columns into the contract.
4. **Evidence references:** Confirm only SafetyEvent references are needed initially. Do not expose arbitrary internal IDs or invent a new evidence API here.
5. **Temporal semantics:** Confirm UTC-aware timestamps and distinct event/review time versus persistence time.
6. **Append-only history:** Preserve separate records for corrections/reviews; no update DTO, PATCH semantics, mutable status, or implicit supersession.
7. **Consumer plan:** Adapter/client integration is a later implementation task, not part of this design-only delivery.

## 5. Compatibility and implementation rules

- Target **`sie-contract 0.6.0`** only after approval; this is additive under the current 0.x policy.
- Contract changes originate in Commercial Core `sie-contract/`. Never independently edit Public SIE `backend/vendor/sie_contract/`; re-vendor from the exact approved source commit and update `PROVENANCE.json` atomically.
- Keep contract imports independent of private `app.*` modules and Public SIE source.
- Public writes must derive organization and actor from authenticated/authorized request context, never client JSON.
- Scope every lookup and nested reference to the organization. Missing/cross-tenant references must not leak existence.
- Preserve append-only records. Action closure does not prove an outcome, and outcomes must not trigger learning automatically.
- Do not expose private evaluation reasons, learning eligibility, model outputs, or implementation-version fields.
- Tests should cover serialization, immutability, tenant scope, timestamps, enum behavior, evidence-reference restrictions, absence of private fields, and import isolation.

## 6. Design acceptance criteria

- [ ] Boundary owner explicitly approves/rejects limited Outcome/Verification exposure.
- [ ] DTO fields and enum strategy approved.
- [ ] Versioning decision recorded; if approved, target is 0.6.0.
- [ ] Actor/evidence references and Public/Private responsibilities documented.
- [ ] Contract-origin and controlled re-vendoring process agreed.
- [ ] No runtime implementation, UI activation, or backend behavior changed by this specification-only task.

## 7. Non-goals and safety rails

This design does not authorize endpoint wiring, UI activation, database migrations, Organizational Memory/Learning Candidate exposure, evidence-evaluation/learning-gate exposure, model updates, recommendation/prediction changes, changes to M43A–C6, or changes to Claude's active Priority 0 assignment.

## 8. Validation record

- Source/doc review across both repositories: completed for the files listed in Section 2.
- Contract/runtime tests: **not run**; no contract code changed.
- DTO schema validation: **not run**; proposed DTOs are specification text, not implemented types.
- API/UI/tenant-isolation tests: **not run**; implementation is explicitly deferred.
- Independent architecture approval: **pending**.
