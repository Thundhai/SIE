# Shared Work Handoff — Phase 2 Outcomes/Verification Contract Design

**Handoff ID:** SIE-PH2-OV-CONTRACT-2026-10-19  
**Owner:** ChatGPT — specification and audit only  
**Status:** Draft prepared; architecture approval pending  
**Branch:** `docs/phase2-outcomes-verification-contract-design`  
**Claude Priority 0:** PRESERVE AS ACTIVE. This task does not reset, replace, or take ownership of it.

## Objective

Prepare a reviewable Outcomes/Verification shared-contract proposal and audit trail for Phase 2. No runtime DTOs, adapters, endpoints, UI, database changes, or learning behavior are included.

## Work in this branch

- Added `docs/PHASE2_OUTCOMES_VERIFICATION_CONTRACT_SPEC.md` with audit findings, proposed DTO fields, exclusions, open architecture decisions, versioning rules, acceptance criteria, and validation status.
- Updated the Phase 2 roadmap item to show specification drafted / review pending. The item is **not done**.
- No runtime or contract package code changed. No Public SIE vendor files changed.

## Inspection evidence

Inspected current default-branch files from both repositories, including:

- Public SIE: `docs/ROADMAP.md`, `backend/app/schemas/intelligence_outcome.py`, `backend/app/schemas/intelligence_outcome_verification.py`, `backend/vendor/sie_contract/PROVENANCE.json`.
- Commercial Core: `sie-contract/README.md`, `sie-contract/src/sie_contract/common.py`, `sie-contract/src/sie_contract/decisions.py`, `app/models/intelligence_outcome.py`, `app/models/intelligence_outcome_enums.py`, `app/models/intelligence_outcome_verification_enums.py`, `app/services/intelligence_outcome_service.py`, `app/services/intelligence_outcome_verification_service.py`, `docs/BOUNDARY_DECISIONS.md`, `docs/PUBLIC_SIE_MIGRATION_MAP.md`.

The current Public SIE vendored contract is 0.5.0. Commercial Core boundary docs classify Outcomes/Verification exposure as `REVIEW_REQUIRED` / learning-loop territory. Existing HTTP schemas are not automatically safe shared-contract definitions.

Open Public SIE PRs observed included #30, #31, #32, #39 and older #14. PR #32/#39 and the stale roadmap contract-version reference remain in Claude's Priority 0 lane as previously allocated. This handoff does not duplicate their reconciliation, security remediation, CI checks, or version-reference correction. Re-check live PR state before follow-on work.

## Proposed design (not approved)

- Proposed contract target: `sie-contract 0.6.0`, only after explicit approval.
- Proposed DTOs: `OutcomeReferenceDTO`, `OutcomeListResultDTO`, `OutcomeVerificationReferenceDTO`, `OutcomeVerificationListResultDTO`.
- Exclude combined verification-state DTO for now because the existing aggregate contains evidence-evaluation details and learning-eligibility reasons.
- Expose factual human-authored governance records only; no private evaluation logic, learning gate, model output, scoring, or algorithmic criteria.
- Preserve append-only records and event/review time versus persistence time.
- If approved, contract source changes originate in Commercial Core `sie-contract/`; Public SIE vendor files are re-vendored from the exact approved source commit, never hand-edited.

## Validation record

- [x] Read current source/docs in both repositories.
- [x] Recorded source links and audit conclusions in the specification.
- [x] Documented proposed fields, exclusions, versioning and acceptance criteria.
- [ ] Contract package tests — not run; no contract code changed.
- [ ] DTO schema tests — not run; DTOs are specification only.
- [ ] CI/build/API/UI tests — not run; implementation is out of scope.
- [ ] Boundary-owner approval — pending.
- [ ] Claude acknowledgment — pending.

## Explicit next actions for Claude

1. **Do not stop or restart the active Priority 0 task.** Finish its currently assigned PR reconciliation, security remediation, checks, and roadmap-version correction as already instructed.
2. Before taking any new Phase 2 implementation task, read this handoff and the linked specification.
3. Do not implement or expose Outcomes/Verification DTOs until the user explicitly approves the boundary decision and field set in Section 4 of the specification.
4. If approved, create a separate Commercial Core contract-origin PR for `sie-contract 0.6.0`, update its changelog and `docs/BOUNDARY_DECISIONS.md`, and add contract tests limited to the approved DTOs.
5. After that contract PR merges, re-vendor from the exact approved source commit into Public SIE and update `backend/vendor/sie_contract/PROVENANCE.json` atomically. Never hand-edit vendor files.
6. Wire adapters/client/endpoints only in a later, separately allocated task with tenant-isolation and integration tests. UI activation is later still.
7. Record PRs, source/vendor commits, test runs, and changed decisions here. Do not mark the roadmap item done until contract implementation, tests, approval, and controlled re-vendoring are complete.

## Completion definition

This allocation is complete only as a **specification/audit handoff** when the documentation PR is reviewed and merged. It does not complete Phase 2 contract implementation or Outcomes/Verification wiring.
