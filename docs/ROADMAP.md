# SIE Project Roadmap

**Purpose:** the single tracked backlog of everything pending/remaining across both `Thundhai/SIE` (public) and `Thundhai/SIE-Commercial-Core` (private), sequenced into phases and prioritized. This is the living source of truth until the items below are done — update the Status Summary and each item's checkbox as work lands, rather than keeping progress only in chat history.

**Derived from:** a full audit of both repositories (security, product completeness, architecture) conducted 2026-10-15.

**This document itself landed via PR #33** (merged `dd3d40d`); the README/LICENSE/rebrand item via PR #34 (merged `46ec220`); the Decision/Outcome/Verification UI fix via PR #35 (merged `15aa757`) — all three on `main` as of 2026-10-15. Phase 1's Decisions wiring landed via PR #37 (merged `32f05dd`), on top of `Thundhai/SIE-Commercial-Core` PR #11 (merged `8a63aa7`).

---

## Status Summary

*Updated automatically on a recurring schedule, and manually whenever a phase item is closed out.*

| Phase | Items | Done | % Complete | Last checked |
|---|---|---|---|---|
| Phase 0 — Stop the Bleeding | 3 | 3 | 100% | 2026-10-19 |
| Phase 1 — Close the Decision Loop | 5 | 3 | 60% | 2026-10-19 |
| Phase 2 — Finish the Intelligence Loop | 4 | 0 | 0% | 2026-10-21 |
| Phase 3 — Enterprise Readiness | 5 | 0 | 0% | 2026-10-19 |
| Phase 4 — Strategic Decisions + Expansion | 5 | 0 | 0% | 2026-10-19 |
| Phase 5 — Hygiene & Long-Term | 7 | 0 | 0% | 2026-10-19 |
| **Overall** | **29** | **6** | **21%** | **2026-10-21** |

**2026-10-19 check-in: no numeric change** from the 2026-10-16 check-in — re-verified against live GitHub state (PR states, CI, file contents), not just this file's checkboxes. One relevant development since then, not yet reflected in a checkbox: `Thundhai/SIE` PR #46 (draft) adds `docs/PHASE2_OUTCOMES_VERIFICATION_CONTRACT_SPEC.md` and a handoff doc proposing DTOs for Phase 2's first item below — specification only, explicitly not implemented pending the user's approval of the boundary/field-set questions it raises, so Phase 2 stays 0/4 until that lands for real. The three pre-existing PRs outside the 29 tracked items, previously noted here as open and under separate reconciliation, have since resolved (all 2026-10-19): #39 merged into `main` (`51245b7`); #32 (read-only Attention list for the Intelligence page) merged into `main` (`257cf23`); #30 (demo-key placeholder cleanup) closed without merging, superseded — see its own PR thread for why. None of the three are among the 29 tracked deliverables above, so this resolution leaves the Status Summary table's phase counts unchanged.

Phase 1's remaining count (2/5) is: 1 deferred by deliberate decision (Render), 1 half-done and blocked on a repo-settings switch (CodeQL half of the CodeQL+secrets item — secrets half is done).

**2026-10-19 (08:42 UTC) recurring check-in: no numeric change.** Independently re-verified all 29 items against live state — file/code contents and `git log` in `Thundhai/SIE`, GitHub API (PRs, branches, workflow files) for both repos — not just this file's checkboxes. Nothing flipped: Phase 0 stays 3/3, Phase 1 stays 3/5, Phases 2-5 stay at 0, overall stays 6/29 (21%). Two developments since the prior note, neither changing a checkbox: `Thundhai/SIE` PR #48 (draft, opened today) adds a preliminary rate-limiting coverage-audit doc for Phase 3's rate-limiting item — audit only; a static grep found roughly a dozen of the 26 `app/api/v1/` routers with no rate-limit-related import, which indicates a likely gap but is not a runtime-verified enforcement check (PR #48's own text makes the same caveat: "symbol presence per module is not proof of route-level coverage"), so that item stays unchecked; PR #46 (Phase 2 Outcomes/Verification contract design) remains open/draft/unmerged, unchanged, and the vendored `sie_contract` still carries no Outcome/Verification DTOs. Phase 1's branch-protection item was incidentally reconfirmed today: two unrelated small branches pushed by this session were each met with GitHub's own "Bypassed rule violations" notice (ref-creation/ref-update restricted), the same enforcement signature already on record. Phase 5's branch-cleanup item (still 0) has drifted further from its original count: the live branch list is still approximately 63 non-`main` branches, up from the 45 cited in the 2026-10-15 audit. Correction: an earlier draft of this note wrongly said the same-day 01:14 UTC check-in (PR #47) was closed without merging. It was in fact merged (`d0ccf41`, confirmed an ancestor of this `main`); its date-bump and the paragraph above it are already on `main` from that merge. This 08:42 UTC paragraph is a separate, later same-day check-in, not a supersession of unmerged work.

**2026-10-19 (afternoon) recurring check-in (corrected 2026-10-21): no numeric change.** Independently re-verified all 29 items against live state in both repos (file/code contents, `git log`, GitHub API for PRs/CI). `sie-contract` 0.6.0 (Outcome/Verification DTOs) is merged into `Thundhai/SIE-Commercial-Core` main (verified: files read off the merge commit, 127 contract tests passing, CI green). **Phase 2's first item is recorded as in progress (`[~]`), not done**: see the item for the two unmet requirements (corrected 2026-10-21). Counts unchanged: Phase 2 0/4, overall 6/29 (21%). Phase 2's second item stays open: confirmed `backend/vendor/sie_contract/VERSION` on `Thundhai/SIE` main is still `0.5.0` — no re-vendoring has happened, so Public SIE cannot yet construct these DTOs.

Checked explicitly per this check-in's own instruction: whether `Thundhai/SIE` PR #46 (Phase 2 contract design spec) or PR #48 (rate-limiting coverage audit) — both authored under the shared `Thundhai` account but whose own text identifies the drafting party as a separate collaborator ("ChatGPT — specification and audit only"), working alongside this session on this roadmap — had advanced since the last check-in. Both are unchanged: still open, draft, unmerged, same commit count and `updated_at` as previously recorded. Neither completes a roadmap item by merging alone (both say so explicitly in their own PR bodies), but PR #46's proposed field set and open questions were answered by the owner's authorization record (PR #53) and were **the basis for** PR #17's merged DTOs, with changes (for example `actor_reference` became `actor_id`). PR #48 remains an unimplemented, preliminary audit; the rate-limiting item (Phase 3) stays unchecked.

Priority legend: **P0** blocking/urgent · **P1** high value, this quarter · **P2** real but can wait · **P3** hygiene/cleanup/long-term.

---

## Phase 0 — Stop the Bleeding (days, not weeks)

- [x] **(P0)** Hide or clearly label the Decision/Outcome/Verification controls on Action Detail (`ActionOutcomeLifecycle.tsx`) — they're live, reachable, and every click currently 501s. — PR #35, merged into `main` (`15aa757`).
- [x] **(P0)** ~~Re-vendor `sie-contract` into the public repo~~ — **already done.** Verified 2026-10-15: `backend/vendor/sie_contract/` was at 0.4.0 (`PROVENANCE.json`: vendored 2026-10-03 from Commercial Core commit `8fd692a`) at the time of this check, includes `decisions.py`/`rag.py`/`intelligence_context.py`/`status.py`/`tenancy.py`, and `test_sie_contract_vendored.py`'s 8 drift-check tests pass. The earlier audit finding (stale at 0.2.0) was itself stale. PR #14 ("Vendor sie-contract 0.2.0") appears fully superseded by what's already on `main` — flagged for disposition, not yet closed. **Current version is 0.5.0**, not 0.4.0 — Phase 1's Decisions-wiring item below widened it same day; re-verified live 2026-10-19 against `backend/vendor/sie_contract/VERSION` and `PROVENANCE.json` on both repos (source commit `8a63aa77784508b5e9bcec94a5febaaacff7564e`, vendored 2026-10-15).
- [x] **(P0)** Add root `README.md`, `LICENSE`, rebrand `package.json` (still named `react-example`, no description). — PR #34, merged into `main` (`46ec220`).

## Phase 1 — Close the Decision Loop (highest-leverage wiring)

Decisions is fully built on both ends (contract DTO `DecisionReferenceDTO` + backend service both exist and are tested) — this is integration work, not new engineering, following the pattern already proven for Attention.

- [x] **(P0)** Wire Decisions end-to-end: `domain_service` route → `app/contract_adapters/decisions_adapter.py` → `cc_service/domain_client/decisions.py` → public HTTP client → unhide UI. — `Thundhai/SIE-Commercial-Core` PR #11 (merged `8a63aa7`) + PR #37 here (merged `32f05dd`). Widened `sie_contract` 0.4.0 → 0.5.0 along the way (additive: `DecisionReferenceDTO` gained `scope`/`site_id`/`attention_category`/`attention_priority`/`attention_title`, all already public via Attention, plus a `DecisionListResultDTO` list envelope — see `BOUNDARY_DECISIONS.md` Section 13 in Commercial Core). `memory-context` stays a 501 stub pending Phase 2's Organizational Memory contract design.
- [~] **(P1)** ~~Move production off Render's free tier~~ — **deliberately deferred, not forgotten.** Explicit decision 2026-10-15: no new recurring spend while pre-revenue/still in production validation. Revisit once there's a paying deployment to justify it.
- [x] **(P1)** Enforce real branch-protection / PR-merge discipline on `main` for both repos — done manually by the user 2026-10-15 via Settings → Branches (PR required, 1 approval, required status checks, branches up to date before merging). The settings API read is itself blocked (`gh api repos/.../branches/main/protection` → `403 Resource not accessible by integration` on both repos, same admin-only boundary that made this unautomatable), so this was verified a different way: a real direct push to `main` on each repo, which GitHub answered with its own "Bypassed rule violations" notice (PR-required + N/N required status checks expected) — proof the rule is genuinely enforced, not just configured. This session's push only succeeded because it still retains bypass rights (left unchecked deliberately — see Commercial Core's `docs/PRIVATE_CORE_BOOTSTRAP.md` "Branch protection on `main`" for the full verification record).
- [~] **(P1)** Commit CodeQL + secret-scanning as version-controlled workflow config — **fully done for `Thundhai/SIE`** (this repo). Secret-scanning: a `security-scan` (gitleaks) job in `ci.yml`, free on a public repo, with a `.gitleaks.toml` allowlist for 5 previously-audited, confirmed-false-positive strings already in history. CodeQL: `.github/workflows/codeql.yml` — first attempt (PR #40) was dropped after GitHub rejected its SARIF upload (`"CodeQL analyses from advanced configurations cannot be processed when the default setup is enabled"`, confirmed from the real job log). User disabled the repo's code-scanning default setup (Settings → Code security → Code scanning → Default setup → Disable) 2026-10-15; second attempt (PR #42) was a real test of that, not an assumption — all three `Analyze` jobs (javascript-typescript/python/actions) genuinely passed this time, merged `e0e8b44`. **`Thundhai/SIE-Commercial-Core`: secrets done, CodeQL deliberately deferred — not a workflow bug, a plan wall.** Explicit go-ahead given 2026-10-16 to add CodeQL there despite the Actions-minutes cost; `.github/workflows/codeql.yml` was written (python + actions matrix — confirmed no JS/TS present) and pushed (`ci/add-codeql` branch, PR #16). Found two real issues in order: (1) `Analyze (actions)` failed on `Resource not accessible by integration` calling the workflow-runs API — fixed by adding `actions: read` to permissions (`f471d13`), confirmed fixed since the next run got past that point; (2) both `Analyze (python)` and `Analyze (actions)` then failed at SARIF upload with GitHub's own `"Code scanning is not enabled for this repository"` — independently reproduced via direct API calls (`code-scanning/default-setup` and `code-scanning/alerts` both return `403` with that exact message, not just the job log), and confirmed via the repo's own Settings → Code security and analysis page showing no "Code scanning" or "GitHub Advanced Security" row at all, not even greyed out. Unlike the public repo's default-setup conflict (free to fix via a toggle), private-repo code scanning here isn't a self-serve setting — it would need a GitHub plan change (GitHub Advanced Security), which falls under the no-new-spend decision. PR #16 closed without merging 2026-10-16; `ci/add-codeql` branch and the workflow file (with the permissions fix already applied) left in place so a future revisit only needs the plan question answered, not the investigation redone.
- [x] **(P1)** Add Dependabot to both repos — `.github/dependabot.yml` added to both (npm/pip/github-actions for `Thundhai/SIE`; pip for the main package and the `sie-contract/` subpackage, plus github-actions, for `Thundhai/SIE-Commercial-Core`). Zero cost: Dependabot version/security updates don't consume Actions minutes on either public or private repos.

## Phase 2 — Finish the Rest of the Intelligence Loop

- [~] **(P1)** Design contract DTOs for Outcomes/Verification — **in progress, not complete.** Drafted in `Thundhai/SIE` PR #46 (draft); owner authorization recorded in PR #53; merged as `sie-contract` 0.6.0 in `Thundhai/SIE-Commercial-Core` PR #17 (`d303545`). Two requirements are unmet: (1) Outcomes and Verifications must be **human-actor-only** (owner decision, 2026-10-21), but 0.6.0 accepts `ActorType.MACHINE`; (2) actor identity after a user or API client is hard-deleted is unresolved (open finding on PR #55). Re-vendoring is in PR #55 (conditionally accepted, vendoring only). Not counted as done.
- [ ] **(P1)** Wire Outcomes/Verification end-to-end — **BLOCKED** until the actor-identity remediation and human-only enforcement (contract validation, Commercial Core service checks, Public SIE and Commercial Core write paths) are implemented and tested. No adapter, endpoint or UI before then.
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
