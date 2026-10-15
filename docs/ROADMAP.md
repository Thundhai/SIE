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

Phase 1's remaining count (2/5) is: 1 deferred by deliberate decision (Render), 1 needs a human with repo admin access (branch protection — not automatable from here).

Priority legend: **P0** blocking/urgent · **P1** high value, this quarter · **P2** real but can wait · **P3** hygiene/cleanup/long-term.

---

## Phase 0 — Stop the Bleeding (days, not weeks)

- [x] **(P0)** Hide or clearly label the Decision/Outcome/Verification controls on Action Detail (`ActionOutcomeLifecycle.tsx`) — they're live, reachable, and every click currently 501s. — PR #35, merged into `main` (`15aa757`).
- [x] **(P0)** ~~Re-vendor `sie-contract` into the public repo~~ — **already done.** Verified 2026-10-15: `backend/vendor/sie_contract/` is already at 0.4.0 (`PROVENANCE.json`: vendored 2026-10-03 from Commercial Core commit `8fd692a`), includes `decisions.py`/`rag.py`/`intelligence_context.py`/`status.py`/`tenancy.py`, and `test_sie_contract_vendored.py`'s 8 drift-check tests pass. The earlier audit finding (stale at 0.2.0) was itself stale. PR #14 ("Vendor sie-contract 0.2.0") appears fully superseded by what's already on `main` — flagged for disposition, not yet closed.
- [x] **(P0)** Add root `README.md`, `LICENSE`, rebrand `package.json` (still named `react-example`, no description). — PR #34, merged into `main` (`46ec220`).

## Phase 1 — Close the Decision Loop (highest-leverage wiring)

Decisions is fully built on both ends (contract DTO `DecisionReferenceDTO` + backend service both exist and are tested) — this is integration work, not new engineering, following the pattern already proven for Attention.

- [x] **(P0)** Wire Decisions end-to-end: `domain_service` route → `app/contract_adapters/decisions_adapter.py` → `cc_service/domain_client/decisions.py` → public HTTP client → unhide UI. — `Thundhai/SIE-Commercial-Core` PR #11 (merged `8a63aa7`) + PR #37 here (merged `32f05dd`). Widened `sie_contract` 0.4.0 → 0.5.0 along the way (additive: `DecisionReferenceDTO` gained `scope`/`site_id`/`attention_category`/`attention_priority`/`attention_title`, all already public via Attention, plus a `DecisionListResultDTO` list envelope — see `BOUNDARY_DECISIONS.md` Section 13 in Commercial Core). `memory-context` stays a 501 stub pending Phase 2's Organizational Memory contract design.
- [~] **(P1)** ~~Move production off Render's free tier~~ — **deliberately deferred, not forgotten.** Explicit decision 2026-10-15: no new recurring spend while pre-revenue/still in production validation. Revisit once there's a paying deployment to justify it.
- [ ] **(P1)** Enforce real branch-protection / PR-merge discipline (all 24 closed PRs in history show `merged: false` — the review gate isn't actually the enforced merge path today). **Not automatable from here** — no GitHub MCP tool exposes branch-protection/ruleset management; this needs a human with repo admin access in Settings → Branches. Concretely, for `main` on both repos: require a PR before merging, require the `CI`/`backend`/`frontend` status checks to pass, require at least 1 approval, and (optionally) require branches to be up to date before merging.
- [x] **(P1)** Commit CodeQL + secret-scanning as version-controlled workflow config — done for `Thundhai/SIE` (this repo): `.github/workflows/codeql.yml` (javascript-typescript/python/actions, matching what "default setup" already covered) + a `security-scan` (gitleaks) job added to `ci.yml`, both free on a public repo. Required a `.gitleaks.toml` allowlist for 5 previously-audited, confirmed-false-positive strings already in history (example API keys in docs/UI, a test fixture constant, a report UUID, a mock sensor ID — none real) so the new job doesn't permanently fail on old, harmless commits. **Not yet done for `Thundhai/SIE-Commercial-Core`** (already has version-controlled gitleaks; still lacks a version-controlled CodeQL workflow) — deliberately not added without checking first: it's a *private* repo, so new CI minutes there may draw on a paid Actions quota depending on the org's GitHub plan, unlike the public repo's unlimited minutes. Needs an explicit go-ahead given the no-new-spend decision above.
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
