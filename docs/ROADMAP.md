# SIE Project Roadmap

**Purpose:** the single tracked backlog of everything pending/remaining across both `Thundhai/SIE` (public) and `Thundhai/SIE-Commercial-Core` (private), sequenced into phases and prioritized. This is the living source of truth until the items below are done — update the Status Summary and each item's checkbox as work lands, rather than keeping progress only in chat history.

**Derived from:** a full audit of both repositories (security, product completeness, architecture) conducted 2026-10-15.

**This document itself landed via PR #33** (merged `dd3d40d`); the README/LICENSE/rebrand item via PR #34 (merged `46ec220`); the Decision/Outcome/Verification UI fix via PR #35 (merged `15aa757`) — all three on `main` as of 2026-10-15. Phase 1's Decisions wiring landed via PR #37 (merged `32f05dd`), on top of `Thundhai/SIE-Commercial-Core` PR #11 (merged `8a63aa7`).

---

## Status Summary

*Updated automatically on a recurring schedule, and manually whenever a phase item is closed out.*

| Phase | Items | Done | % Complete | Last checked |
|---|---|---|---|---|
| Phase 0 — Stop the Bleeding | 3 | 3 | 100% | 2026-10-15 |
| Phase 1 — Close the Decision Loop | 5 | 3 | 60% | 2026-10-15 |
| Phase 2 — Finish the Intelligence Loop | 4 | 0 | 0% | 2026-10-15 |
| Phase 3 — Enterprise Readiness | 5 | 0 | 0% | 2026-10-15 |
| Phase 4 — Strategic Decisions + Expansion | 5 | 0 | 0% | 2026-10-15 |
| Phase 5 — Hygiene & Long-Term | 7 | 0 | 0% | 2026-10-15 |
| **Overall** | **29** | **6** | **21%** | **2026-10-15** |

Phase 1's remaining count (2/5) is: 1 deferred by deliberate decision (Render), 1 half-done and blocked on a repo-settings switch (CodeQL half of the CodeQL+secrets item — secrets half is done).

Priority legend: **P0** blocking/urgent · **P1** high value, this quarter · **P2** real but can wait · **P3** hygiene/cleanup/long-term.

---

## Phase 0 — Stop the Bleeding (days, not weeks)

- [x] **(P0)** Hide or clearly label the Decision/Outcome/Verification controls on Action Detail (`ActionOutcomeLifecycle.tsx`) — they're live, reachable, and every click currently 501s. — PR #35, merged into `main` (`15aa757`).
- [x] **(P0)** ~~Re-vendor `sie-contract` into the public repo~~ — **already done.** Verified 2026-10-17: `backend/vendor/sie_contract/` is at **0.5.0** (`VERSION` and `PROVENANCE.json` agree), sourced from Commercial Core commit `8a63aa7`; the 0.5.0 update added the Decision DTO fields and `DecisionListResultDTO` required by the Decisions integration (see Phase 1 / PR #37). `test_sie_contract_vendored.py` validates version/provenance consistency and drift. The earlier audit finding (stale at 0.2.0) was itself stale. PR #14 ("Vendor sie-contract 0.2.0") is superseded by what is already on `main` — flagged for disposition, not yet closed.
- [x] **(P0)** Add root `README.md`, `LICENSE`, rebrand `package.json` (still named `react-example`, no description). — PR #34, merged into `main` (`46ec220`).

## Phase 1 — Close the Decision Loop (highest-leverage wiring)

Decisions is fully built on both ends (contract DTO `DecisionReferenceDTO` + backend service both exist and are tested) — this is integration work, not new engineering, following the pattern already proven for Attention.

- [x] **(P0)** Wire Decisions end-to-end: `domain_service` route → `app/contract_adapters/decisions_adapter.py` → `cc_service/domain_client/decisions.py` → public HTTP client → unhide UI. — `Thundhai/SIE-Commercial-Core` PR #11 (merged `8a63aa7`) + PR #37 here (merged `32f05dd`). Widened `sie_contract` 0.4.0 → 0.5.0 along the way (additive: `DecisionReferenceDTO` gained `scope`/`site_id`/`attention_category`/`attention_priority`/`attention_title`, all already public via Attention, plus a `DecisionListResultDTO` list envelope — see `BOUNDARY_DECISIONS.md` Section 13 in Commercial Core). `memory-context` stays a 501 stub pending Phase 2's Organizational Memory contract design.
- [~] **(P1)** ~~Move production off Render's free tier~~ — **deliberately deferred, not forgotten.** Explicit decision 2026-10-15: no new recurring spend while pre-revenue/still in production validation. Revisit once there's a paying deployment to justify it.
- [x] **(P1)** Enforce real branch-protection / PR-merge discipline on `main` for both repos — done manually by the user 2026-10-15 via Settings → Branches (PR required, 1 approval, required status checks, branches up to date before merging). The settings API read is itself blocked (`gh api repos/.../branches/main/protection` → `403 Resource not accessible by integration` on both repos, same admin-only boundary that made this unautomatable), so this was verified a different way: a real direct push to `main` on each repo, which GitHub answered with its own "Bypassed rule violations" notice (PR-required + N/N required status checks expected) — proof the rule is genuinely enforced, not just configured. This session's push only succeeded because it still retains bypass rights (left unchecked deliberately — see Commercial Core's `docs/PRIVATE_CORE_BOOTSTRAP.md` "Branch protection on `main`" for the full verification record).
- [~] **(P1)** Commit CodeQL + secret-scanning as version-controlled workflow config — **fully done for `Thundhai/SIE`** (this repo). Secret-scanning: a `security-scan` (gitleaks) job in `ci.yml`, free on a public repo, with a `.gitleaks.toml` allowlist for 5 previously-audited, confirmed-false-positive strings already in history. CodeQL: `.github/workflows/codeql.yml` — first attempt (PR #40) was dropped after GitHub rejected its SARIF upload (`"CodeQL analyses from advanced configurations cannot be processed when the default setup is enabled"`, confirmed from the real job log). User disabled the repo's code-scanning default setup (Settings → Code security → Code scanning → Default setup → Disable) 2026-10-15; second attempt (PR #42) was a real test of that, not an assumption — all three `Analyze` jobs (javascript-typescript/python/actions) genuinely passed this time, merged `e0e8b44`. **`Thundhai/SIE-Commercial-Core`: secrets done, CodeQL deliberately deferred — not a workflow bug, a plan wall.** Explicit go-ahead given 2026-10-16 to add CodeQL there despite the Actions-minutes cost; `.github/workflows/codeql.yml` was written (python + actions matrix — confirmed no JS/TS present) and pushed (`ci/add-codeql` branch, PR #16). Found two real issues in order: (1) `Analyze (actions)` failed on `Resource not accessible by integration` calling the workflow-runs API — fixed by adding `actions: read` to permissions (`f471d13`), confirmed fixed since the next run got past that point; (2) both `Analyze (python)` and `Analyze (actions)` then failed at SARIF upload with GitHub's own `"Code scanning is not enabled for this repository"` — independently reproduced via direct API calls (`code-scanning/default-setup` and `code-scanning/alerts` both return `403` with that exact message, not just the job log), and confirmed via the repo's own Settings → Code security and analysis page showing no "Code scanning" or "GitHub Advanced Security" row at all, not even greyed out. Unlike the public repo's default-setup conflict (free to fix via a toggle), private-repo code scanning here isn't a self-serve setting — it would need a GitHub plan change (GitHub Advanced Security), which falls under the no-new-spend decision. PR #16 closed without merging 2026-10-16; `ci/add-codeql` branch and the workflow file (with the permissions fix already applied) left in place so a future revisit only needs the plan question answered, not the investigation redone.
- [x] **(P1)** Add Dependabot to both repos — `.github/dependabot.yml` added to both (npm/pip/github-actions for `Thundhai/SIE`; pip for the main package and the `sie-contract/` subpackage, plus github-actions, for `Thundhai/SIE-Commercial-Core`). Zero cost: Dependabot version/security updates don't consume Actions minutes on either public or private repos.

## Phase 2 — Finish the Rest of the Intelligence Loop

- [ ] **(P1)** Design contract DTOs for Outcomes/Verification (currently `REVIEW_REQUIRED` — the backend service already exists, this is a design task).
- [ ] **(P1)** Wire Outcomes/Verification end-to-end once the contract lands.
- [ ] **(P1/P2)** Design contract + wire Organizational Memory / Learning Candidates (fully-built governed pipeline, currently unused).
- [ ] **(P1)** Wire RAG (contract DTO `RAGAnswerDTO`/`CitationReferenceDTO` already exists, zero wiring) — high market differentiation, a working citation-grounded Q&A feature sitting idle.

## Phase 3 — Enterprise Readiness

- [ ] **(P1)** SOC 2 / ISO 27001 prep + a written security-review package (security fundamentals are genuinely strong — this is documentation/certification work).
- [ ] **(P1)** Write the data-flow / IP-boundary explainer doc for buyers (the referenced-but-missing `M43_IP_03_PUBLIC_EXTRACTION.md` or equivalent).
- [ ] **(P1)** Rate limiting: consistent coverage across all 27 routers + a production-safe (multi-instance) limiter.
- [ ] **(P1)** Notifications/webhook delivery (currently an explicit non-goal — promote to roadmap, it's table-stakes for this category).
- [ ] **(P1)** File attachments on events/actions (same — currently a non-goal, but incident evidence without photos is weak).

## Phase 4 — Strategic Decisions + Market Expansion

- [ ] **(P2)** Decide what/when to expose Predictions (deliberately excluded from the contract today to avoid model-confidence leakage — product/IP decision, not an engineering one).
- [ ] **(P2)** Decide what/when to expose Recommendation Generation (most mature capability in Commercial Core, zero HTTP layer by explicit design).
- [ ] **(P2)** Pre-built regulatory report formats (OSHA 300, RIDDOR, etc.).
- [ ] **(P2)** Validate mobile/offline field-capture need with real prospects, then build if confirmed (nothing exists today — web SPA only).
- [ ] **(P2/P3)** M43B — standards-applicability reasoning (region/site/hazard), explicitly deferred; prioritize against actual deal needs.

## Phase 5 — Hygiene & Long-Term

- [ ] **(P3)** Delete the 14 unwired legacy view files + mock data (`src/views/*`, `mockData.ts`) — confirmed dead/unreachable.
- [ ] **(P3)** Clean up 45 stale/duplicate branches; adopt a post-merge deletion policy.
- [ ] **(P2/P3)** Add frontend tests for Knowledge and Reports (currently zero).
- [ ] *(Ongoing)* Add backend tests for each stub router as it goes live, landing alongside its wiring PR.
- [ ] **(P3)** Give Commercial Core independent migration tooling; plan the eventual move off shared-DB ("Option A") toward separate schemas ("Option D").
- [ ] **(P3)** Credential rotation without requiring a redeploy (currently a documented, deliberate trade-off).
- [ ] **(P3)** Fix the stale CI comment describing an already-resolved migration drift (Milestone 19A actually fixed it; `ci.yml`'s comment wasn't updated).

---

## Suggested Sequencing

- **Now → 2 weeks:** Phase 0 entirely, start Phase 1's Decisions wiring.
- **This quarter:** Finish Phase 1, work through Phase 2 (Outcomes/Verification, then RAG — RAG is the stronger sales story, consider it before Organizational Memory).
- **Next quarter:** Phase 3 in parallel with any remaining Phase 2 work — compliance prep has a long lead time, start early even though it's P1 not P0.
- **Ongoing/opportunistic:** Phase 4 decisions (leadership calls, not sprints) and Phase 5 cleanup (fold into whatever PR already touches that area).
