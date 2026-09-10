# SIE Enterprise Read API & Browser Integration

**SIE Enterprise Read API & Browser Integration Foundation v0.1.** This
document covers the backend surface added in this milestone — the
human-facing Events read API, the effective-permissions endpoint, CORS
configuration, and the production authentication boundary — and how the
frontend built in `docs/FRONTEND_ARCHITECTURE.md` connects to it. It does
not re-document the identity/authorization architecture built in an
earlier milestone; see `backend/README.md`'s "Identity architecture"
section for that (referenced throughout below, not repeated).

## 1. Architecture

```
Browser (SIE frontend, e.g. http://localhost:3000)
    │  fetch(), credentials: cross-origin
    ▼
CORSMiddleware                    backend/app/main.py
    │  (configured origin allowlist — §4 below)
    ▼
Frontend API client                src/services/api/*
    │  X-SIE-Dev-User-Id (dev) or Bearer token (future — §5 below)
    ▼
Enterprise API (versioned REST)    backend/app/api/v1/events.py, auth.py
    │
    ▼
RequestContext / TenantContext     backend/app/api/deps_context.py,
    │                              backend/app/api/deps_auth.py
    ▼
Authorization                      backend/app/services/tenant_context.py,
    │                              backend/app/services/permissions.py
    ▼
Tenant-scoped service/repository   backend/app/services/base.py
    │  (organization_id always part of the WHERE clause, never
    │   trusted from the caller alone — see §3 below)
    ▼
SafetyEvent (+ Site, DataSource)   backend/app/models/safety_event.py
```

This is the same pipeline every other authenticated route in this
backend already uses (`app/api/v1/memberships.py`,
`app/api/v1/api_clients.py`); the Events and `/auth/me` endpoints
introduce **zero new authentication or authorization logic** — they are
new routes built on that existing pipeline, not a parallel one.

## 2. Events read API

### `GET /api/v1/events`

Lists `SafetyEvent` rows for one organization, paginated, filtered, and
searched server-side. Requires `Permission.SAFETY_DATA_READ` in the
organization named by `organization_id` (checked by
`require_context_permission`, the same dependency every other
machine-or-human read route in this backend uses — see
`app/api/deps_context.py`).

**Query parameters**

| Parameter | Type | Notes |
|---|---|---|
| `organization_id` | UUID, required | The organization to list events for. Authorization is checked against this id — it is never inferred from a filter. |
| `page` | int, default 1 | 1-indexed. |
| `page_size` | int, default 25, max 100 | |
| `event_type` | string | Exact match against `SafetyEvent.event_type`. |
| `event_subtype` | string | Exact match against `SafetyEvent.event_subtype`. |
| `site_id` | UUID | Exact match against `SafetyEvent.site_id`. |
| `status` | string | Exact match against `SafetyEvent.status`. |
| `source_system` | string | Exact match against `SafetyEvent.source_system`. |
| `event_time_from` / `event_time_to` | datetime (ISO 8601) | Inclusive range filter on `SafetyEvent.event_time`. |
| `search` | string | Case-insensitive substring match, `OR`ed across `description`, `external_reference`, and the canonical `event_type`/`event_subtype` fields — a single parameterized ORM query (`ILIKE`), never raw/unrestricted SQL. |

Every filter and search field maps to a real column already present on
`SafetyEvent` — nothing here is fabricated to make the query surface
look larger than the data actually supports.

**Response** (`EventListRead`):

```json
{
  "items": [ { "...": "SafetyEventSummaryRead — §2.1 below" } ],
  "total": 137,
  "page": 1,
  "page_size": 25
}
```

`total` comes from a separate `COUNT(*)` query using the same filter
predicates as the page query — the full result set is never loaded into
memory to compute it. Sorting is deterministic:
`event_time DESC, id DESC` (a stable secondary key breaks ties between
events with an identical `event_time`), so the same query against
unchanged data always returns rows in the same order across pages.

An out-of-range `page` (past the last page) returns an empty `items`
list with a valid `total`/`page`/`page_size`, not an error — this
matches how `page`-based pagination is already handled elsewhere in this
backend (`app/api/v1/data_ingestion.py`, `app/api/v1/predictions.py`).

#### 2.1 `SafetyEventSummaryRead` (list item shape)

`id`, `event_type`, `event_subtype`, `event_time`, `site_id`, `site_name`,
`status`, `source_system`, `external_reference`, `description`.

### `GET /api/v1/events/{event_id}`

Returns one event's full detail, or `404` — identically whether
`event_id` does not exist at all, or exists in a **different**
organization than `organization_id` (§3 below). Same authorization
dependency as the list endpoint.

**Response** (`SafetyEventDetailRead`): everything in the summary shape,
plus `narrative` (the long-form description field, where distinct from
`description`) and an `EventProvenanceRead` object:

```json
{
  "...": "SafetyEventSummaryRead fields",
  "narrative": "...",
  "provenance": {
    "organization_id": "...",
    "data_source_id": "...",
    "data_source_name": "...",
    "ingestion_batch_id": "...",
    "external_record_id": "...",
    "source_version": "...",
    "ingested_at": "..."
  }
}
```

No internal database implementation detail (row-level audit columns,
internal foreign keys unrelated to provenance, etc.) is exposed — only
what a human reviewing the event's origin actually needs.

**No evidence/knowledge references are included.** `SafetyEvent` has no
backend relationship today to a knowledge or evidence record (unlike
`InsightPanel`'s intelligence-analytics use of that pattern, which is
backed by a real relationship — see `app/schemas/intelligence.py`).
Rather than manufacture an empty `evidence: []` array that implies a
relationship exists and simply found nothing, this schema omits the
field entirely; the frontend's existing `InsightPanel` "insufficient
evidence" fallback (built in the Frontend Foundation milestone) already
renders this state correctly with no code changes required. If a real
evidence/knowledge relationship for events is built in a future
milestone, it is added here as a genuinely populated field, not
backfilled as an always-empty one.

## 3. Tenant isolation

Both endpoints combine `organization_id` into the same `WHERE` clause as
every other filter — never as a separate check performed after loading a
row. For the detail endpoint specifically:

```python
stmt = select(SafetyEvent).where(
    SafetyEvent.id == event_id,
    SafetyEvent.organization_id == organization_id,
)
```

An event that exists but belongs to a different organization and an
event id that does not exist at all produce the **same** `404` — a
cross-tenant id is never distinguishable from a nonexistent one (no
`403` that would confirm the id's existence to an unauthorized caller).
See `backend/tests/test_events_api.py` (tenant isolation cases) for the
tests exercising this directly, in both directions, for both human and
machine callers.

## 4. CORS

`CORSMiddleware` (`backend/app/main.py`) is configured from
`settings.CORS_ALLOWED_ORIGINS` (`backend/app/core/config.py`) — a
comma-separated environment variable, parsed into an explicit list of
exact origins via `settings.cors_allowed_origins_list`. It defaults to
`http://localhost:3000` (the frontend's own local dev origin) for local
development; a production deployment sets `CORS_ALLOWED_ORIGINS` to its
real, explicit frontend origin(s) — **`allow_origins=["*"]` is never
used**, since this API serves authenticated, credentialed requests and a
wildcard origin is incompatible with `allow_credentials=True` by the CORS
spec itself (browsers reject the combination outright).

**Middleware ordering matters.** `CORSMiddleware` is registered *last* —
in this codebase's Starlette-based ordering (see `main.py`'s own
"Outermost first" comment), the last `add_middleware()` call becomes the
**outermost** layer. This is deliberate: a preflight `OPTIONS` request
must get a correct CORS response before it ever reaches rate limiting,
request-size checks, or routing, and every real response — including a
`401`/`403`/`404`/`429`/`500` produced by any inner layer or by
`register_exception_handlers()` — must still carry
`Access-Control-Allow-Origin`, or a browser reports a misleading "CORS
error" that masks the real one.

**Verified empirically**, not just by code review (`backend/main.py`
started standalone, `curl` against a running instance):

```
$ curl -i -X OPTIONS http://127.0.0.1:8000/api/v1/events \
    -H "Origin: http://localhost:3000" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: authorization"
HTTP/1.1 200 OK
access-control-allow-origin: http://localhost:3000
access-control-allow-credentials: true
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-allow-headers: authorization

$ curl -i -X OPTIONS http://127.0.0.1:8000/api/v1/events \
    -H "Origin: http://evil.example.com" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: authorization"
HTTP/1.1 400 Bad Request
# no Access-Control-Allow-Origin header — the disallowed origin is
# refused, not silently allowed through.
Disallowed CORS origin

$ curl -i http://127.0.0.1:8000/api/v1/events?organization_id=... \
    -H "Origin: http://localhost:3000"
HTTP/1.1 401 Unauthorized
access-control-allow-origin: http://localhost:3000
# the header is present even on an error response from an inner layer,
# confirming the outermost-middleware placement works as intended.
```

See `backend/tests/test_cors.py` for the automated version of these same
cases (allowed origin, disallowed origin, preflight, credentials).

## 5. Production authentication boundary

This milestone does **not** implement a real OIDC/OAuth2 identity
provider integration — that remains explicitly out of scope (per the
milestone's own instruction and the pre-existing `TokenVerifier` seam's
own docstring). What follows is a plain statement of what is actually
true today, split the way the milestone requires: **Implemented**,
**Architecture/seam established** (code exists and works end-to-end, but
stands in for something a real integration must replace), and
**Requires external infrastructure** (genuinely not buildable without an
external system this milestone has no access to).

| Component | Status |
|---|---|
| `Identity` model, `(issuer, subject)` uniqueness, `IdentityResolverService` | **Implemented** — resolves already-verified claims to a `User`, creates one if needed. Built in a prior milestone, unchanged here. |
| `TokenVerifier` protocol (`app/services/identity_service.py`) | **Architecture/seam established** — the interface a real verifier implements. No behavior of its own. |
| `DevTokenVerifier` | **Architecture/seam established, dev-only** — performs no cryptographic verification; exists solely to exercise the resolver in tests/dev. Never reachable outside `DEV_MODE`. |
| `get_dev_authenticated_user_id` / `X-SIE-Dev-User-Id` header (`app/api/deps_auth.py`) | **Architecture/seam established, dev-only** — the only identity mechanism any HTTP route currently accepts. Gated by `settings.DEV_MODE` (default `false`); fails closed with `501` when off, not "trust the caller." |
| `TenantContext`, `authorize_tenant_context()`, `Permission`/`ROLE_PERMISSIONS`, `require_permission()`/`require_context_permission()` | **Implemented** — real authorization, real membership/status checks, real permission resolution. Everything downstream of "who is this user" is genuinely production logic, not a stand-in. |
| `GET /api/v1/auth/me` (this milestone) | **Implemented** — a thin, honest serializer over `TenantContext`, itself real. Its *input* (how the caller was authenticated) is still the dev-only mechanism above until a real verifier is wired in. |
| CORS (this milestone) | **Implemented** — configurable, environment-driven, verified against a real running server (§4). Not seam-only: this is the actual production behavior, not a placeholder for one. |
| Machine-client authentication (`ApiClient` + bearer secret, `app/services/api_client_service.py`) | **Implemented** — a separate, already-production mechanism for machine callers (see `backend/README.md`'s "Machine-client authentication" section), unaffected by any of the above. |
| Real OIDC/OAuth2 `TokenVerifier` implementation (Auth0, Entra ID, Okta, Keycloak, ...) | **Requires external infrastructure** — an actual identity provider to verify tokens against. Connecting one is a new module implementing the existing `TokenVerifier` protocol (e.g. `app/services/oidc_verifier.py`) plus provider configuration (issuer, JWKS endpoint, audience) — no change to `IdentityResolverService`, `TenantContext`, `Permission`, or any route built on `require_context_permission`/`get_tenant_context`, since all of those already consume the resolved identity, not the verification step itself. |
| A frontend `ProdAuthProvider` (mirrors `src/auth/DevAuthProvider.tsx`) | **Requires external infrastructure** (the IdP above) before it has anything real to call — the frontend's own `src/auth/` abstraction already isolates this to one file (`app/App.tsx`, which provider is mounted), so no screen changes when it lands. |

**What this means concretely:** a deployment of this backend today, with
`DEV_MODE=false` (the production default) and no `TokenVerifier`
implementation configured, correctly refuses every identity-dependent
request with `501 Not Implemented` — it does not silently accept
unauthenticated traffic, and it does not misrepresent itself as having
working production authentication. Claiming "production authentication
complete" would be false; claiming "the boundary a real IdP integration
plugs into already exists, is exercised end-to-end in dev/test, and
requires no changes to authorization or tenant isolation once
connected" is the accurate claim, and is what this section states.

## 6. Effective permissions

### `GET /api/v1/auth/me?organization_id=...`

Human-only (mirrors every other route built on `get_tenant_context` —
see `app/api/deps_context.py`'s own "item 7" rule: machine clients have
no per-session "current user" to introspect). Returns the authenticated
user's identity, organization, role, and **effective permission set**
for that organization — the same `TenantContext.permissions` value every
authorization check in the backend already uses, serialized rather than
re-derived. Introduces zero new authorization logic (§1).

```json
{
  "user_id": "...",
  "name": "...",
  "email": "...",
  "organization_id": "...",
  "organization_name": "...",
  "role": "HSE_MANAGER",
  "permissions": ["safety_data:read", "intelligence:read", "..."],
  "is_platform_admin": false
}
```

The frontend's `hasPermission()` (`src/auth/`) is backed by this
endpoint's response — the backend's `ROLE_PERMISSIONS` mapping
(`app/services/permissions.py`) is never duplicated in React; see
`docs/FRONTEND_ARCHITECTURE.md` §3.

## 7. Errors

Both new routers use the backend's existing standardized error contract
(`app/core/errors.py`) — no new error shape introduced. A validation
failure (e.g. a malformed `organization_id`) returns FastAPI's normal
`422`; an authorization failure returns `403`; an unauthenticated
request returns `401` (dev-mode header missing/invalid) or `501`
(`DEV_MODE` off, §5); a cross-tenant or nonexistent event returns `404`.
