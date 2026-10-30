# Rate-Limiting Coverage — Pre-Implementation Audit

**Date:** 2026-10-19  
**Repository/ref inspected:** `Thundhai/SIE`, default branch `main`  
**Purpose:** evidence-led triage for Phase 3's pending rate-limiting item.  
**Status:** preliminary static audit; not implementation-ready.  
**Scope:** read-only inspection of the current public SIE API router and rate-limit abstraction/dependency. No application files changed.

## Executive finding

The current code explicitly documents two limitations that must remain visible in any release decision:

1. **The configured limiter is process-local, not multi-instance safe.** `backend/app/core/rate_limit.py` uses an in-memory fixed-window counter protected by a thread lock. Separate worker processes/replicas maintain independent counters, so a caller can exceed the intended aggregate limit across replicas. Process restarts also reset the counters.
2. **Rate limiting is off by default.** `backend/app/api/deps_rate_limit.py` returns without enforcing a limit when `settings.RATE_LIMIT_ENABLED` is false. Do not describe this as active protection in a deployment unless the setting and runtime behavior have been verified.
3. **Coverage is not yet proven complete.** The router currently includes 23 API route modules in `backend/app/api/v1/router.py`. A static presence check found `require_rate_limit` references in 12 modules and no references in 11. Presence at module level does not prove that every route is protected; absence does not alone prove a route is unprotected (a router-level dependency or middleware may exist elsewhere). A route-by-route inventory is still required before implementation or any completion claim.

## Static module inventory

| Route module | `require_rate_limit` symbol present in file? |
|---|---|
| `actions.py` | Yes |
| `api_clients.py` | No |
| `auth.py` | No |
| `data_ingestion.py` | Yes |
| `data_sources.py` | Yes |
| `events.py` | Yes |
| `governing_standards.py` | Yes |
| `ingestion.py` | No |
| `intelligence.py` | Yes |
| `intelligence_decisions.py` | Yes |
| `intelligence_learning_candidates.py` | No |
| `intelligence_outcomes.py` | No |
| `knowledge.py` | Yes |
| `memberships.py` | No |
| `model_governance.py` | No |
| `organizational_memory.py` | No |
| `organizations.py` | No |
| `predictions.py` | No |
| `projects.py` | Yes |
| `rag.py` | Yes |
| `retrieval.py` | Yes |
| `risk_assessments.py` | Yes |
| `sites.py` | No |

This is a **triage signal only**, not a claim that 12/23 routers are fully protected or that the other 11 are definitely unprotected. The roadmap refers to 27 routers; the current `api/v1/router.py` imports 23 route modules, so reconcile what the roadmap means by “27 routers” (mounted routers, nested routers, or a stale count) as part of the endpoint inventory.

## Relevant implementation evidence

- `backend/app/core/rate_limit.py`: defines the `RateLimiter` protocol and `LocalRateLimiter`; its own module documentation explicitly says the implementation is unsuitable for multi-instance production.
- `backend/app/api/deps_rate_limit.py`: defines read/write classes and the `require_rate_limit(...)` FastAPI dependency. It bypasses enforcement when `RATE_LIMIT_ENABLED` is false and keys the local counter by caller identity and limit class.
- `backend/app/core/observability.py`: adds `X-RateLimit-*` headers only when the dependency ran and attached a result to the request state.
- `backend/app/api/v1/router.py`: current mounted route-module inventory was used for the table above.
- `backend/app/core/request_limits.py`: request-size limits are a separate control and must not be counted as request-rate limiting.

## Risks and decisions required before implementation

1. **Coverage semantics:** define whether coverage is required for every authenticated route, selected expensive/read routes, mutation routes, authentication endpoints, ingestion/upload endpoints, and health endpoints. Avoid applying one blanket limit without considering operational use and abuse risks.
2. **Identity and keying:** verify the key used for each route and distinguish authenticated human, machine client, unauthenticated/IP-based requests, and tenant scoping. Do not rely on unverified identity headers.
3. **Shared-state backend:** choose and approve a production-safe multi-instance strategy (for example, a managed Redis-compatible store or another shared atomic counter). Do not add a paid dependency/service or recurring spend without explicit approval. The current in-memory limiter must not be presented as equivalent.
4. **Failure mode:** decide fail-open vs fail-closed behavior when the shared store is unavailable, including endpoint-specific exceptions and observability.
5. **HTTP contract:** standardize 429 response shape and `Retry-After` / `X-RateLimit-*` semantics; test reset-window behavior and concurrent requests.
6. **Configuration and deployment:** define safe defaults and verify the production setting before describing protection as enabled.
7. **Tests:** test every mounted route's policy, identity isolation, boundary-window behavior, concurrent requests, multi-worker/shared-store behavior, disabled mode, and backend failure mode.

## Recommended next actions

1. Perform an AST/route-level inventory of every mounted endpoint, recording HTTP method, auth dependency, current limiter dependency, limit class, and any deliberate exemption.
2. Reconcile the “27 routers” roadmap count against the 23 modules currently imported by `api/v1/router.py`.
3. Write a short design decision record for the shared-state backend and outage policy, with cost implications stated explicitly.
4. Only after the route matrix and deployment decision are approved, implement coverage in a dedicated PR with focused tests. Do not modify limiter behavior as part of the current Claude Priority 0 work.

## Validation limits

- Read-only source inspection and static symbol-presence scan only.
- No application code was changed.
- No runtime tests, integration tests, load tests, deployment settings, or live production behavior were exercised.
- Therefore this audit does **not** mark the roadmap's rate-limiting item complete.
