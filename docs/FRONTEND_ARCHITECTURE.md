# SIE Frontend Architecture

**SIE Frontend Foundation & Core UX Implementation v0.1.** This document
covers the *new* SIE frontend (Home, Events, Event Detail) established
in this milestone — its architecture, design tokens, the legacy-vs-new
boundary, and the backend gaps discovered while building it. It does not
cover the backend (see `backend/README.md`).

## 1. Legacy vs. new — read this first

This repository's frontend previously contained one thing only: a
fully-built, dark-themed, AI-dashboard-styled prototype ("Safelytic
Intelligence Engine") — `src/App.tsx`, `src/views/*`, most of
`src/components/*`, `src/mockData.ts`, `src/types.ts`. It ran entirely
on hardcoded mock data (no `fetch` anywhere), had no router, no auth, no
tests, and its own information architecture (Executive Overview,
Intelligence Center, Intervention Center, AI Assistant, ...) does not
match the approved SIE UX direction (Home / Events / Actions /
Intelligence / Knowledge / Reports / Administration).

**That prototype is left completely untouched.** Not one file inside
`src/views/`, and none of `src/components/{ErrorBoundary,
EvidenceDetailModal, EvidenceLineageModal, GlobalFilterBar,
GlobalSearchModal, Header, NotificationDrawer, PredictionMethodologyCard,
Sidebar, Toast}.tsx`, `src/mockData.ts`, `src/types.ts`, or
`src/utils/*` was modified. `src/App.tsx` itself is also untouched.

The **new** SIE application lives in its own set of top-level
directories (`src/app/`, `src/auth/`, `src/features/`, `src/fixtures/`,
`src/services/`, `src/styles/`, `src/test/`, plus the *new* subfolders
`src/components/ui/`, `src/components/layout/`, `src/components/data/`,
`src/components/intelligence/` — none of which existed before this
milestone).

**Three small, shared files were changed** to make the new app the live
one, without altering the legacy prototype's own behavior:

- `src/main.tsx` — now mounts `src/app/App.tsx` (new) instead of
  `src/App.tsx` (legacy). The legacy file itself is unchanged and would
  render identically if `main.tsx` were pointed back at it.
- `index.html` — `<body>` no longer hardcodes the legacy dark theme
  (`bg-[#09090B] text-slate-100 ...`) at the document level. This was a
  real bug: that background was visible underneath *any* app mounted
  into `#root` (e.g. during overscroll, or any gap before the mounted
  app's own root element painted), fighting the new light theme. The
  legacy prototype is unaffected — its own root element already sets
  this same background on itself, redundantly.
- `src/index.css` — now imports `src/styles/tokens.css` (new design
  tokens) and adds two small rules scoped to `[data-sie-app]` (the new
  app's own root element), so nothing here can affect the legacy
  prototype if it were ever mounted again for comparison.

Because the legacy views are no longer imported from `main.tsx`, they
are dead code as far as the shipped bundle is concerned (`vite build`
tree-shakes them out entirely — module count dropped from 2,288 to
1,723, JS bundle from 1.17 MB to 281 KB) — but the source files remain
in the repository, unmodified, exactly as instructed.

## 2. Directory structure

```
src/
  app/                    New app root, router
    App.tsx               <div data-sie-app> + DevAuthProvider + BrowserRouter
    router.tsx             Route table (AppRoutes)
    AppErrorBoundary.tsx    Light-themed top-level error boundary
  auth/                    Authentication/identity abstraction (§3 below)
  components/
    ui/                    Generic primitives: Button, Input, SearchInput,
                            Select, FilterBar, Tabs, Table, Pagination,
                            StatusBadge, PriorityBadge, LoadingState,
                            EmptyState, ErrorState, Modal, Drawer, Overlay
    layout/                AppShell, Sidebar, Header, PageContainer,
                            Section, Breadcrumb
    data/                  EvidenceItem, EvidenceList, DocumentReference,
                            RelatedRecord
    intelligence/           InsightPanel (the "What SIE found" pattern)
  features/
    home/HomePage.tsx
    events/                EventsPage, EventDetailPage, eventRepository.ts
                            (interface), fixtureEventRepository.ts
  services/api/            Typed API client (§4 below)
  fixtures/                Isolated fixture data (§5 below) — see its own README.md
  types/                   Shared cross-feature types (common.ts, events.ts, evidence.ts)
  styles/tokens.css         Design tokens (§6 below)
  test/setup.ts             Vitest setup (jest-dom matchers)
```

No `pages/` or `routes/` directory: `features/*/XPage.tsx` plus
`app/router.tsx` already cover that role, and adding an extra layer for
it would be pure ceremony (per this milestone's own "don't create
architecture purely for the sake of folders" instruction).

## 3. Authentication abstraction

**The backend has no production login/session endpoint yet.** The only
identity mechanism it exposes (`backend/app/api/deps_auth.py`) is a
development-mode request header, `X-SIE-Dev-User-Id`, explicitly
documented there as non-production.

`src/auth/` exists so no page ever depends on that mechanism directly:

- `types.ts` — the `AuthContextValue` interface (`isAuthenticated`,
  `isDevIdentity`, `user`, `organization`, `memberships`, `permissions`,
  `hasPermission()`).
- `AuthContext.tsx` — the context + `useAuth()` hook. No default value;
  throws if used outside a provider.
- `DevAuthProvider.tsx` — today's only implementation. Reads
  `VITE_DEV_USER_ID`/`VITE_DEV_ORGANIZATION_ID` (see `devIdentity.ts`)
  and resolves them against the **real** backend (`GET
  /organizations/{id}`, `GET /organizations/{id}/members/{user_id}` —
  both genuinely existing endpoints), so the organization name and role
  shown are real backend data — but the underlying mechanism (the dev
  header) is not a real session. When unconfigured, or when the backend
  can't resolve the configured ids, `isAuthenticated` is simply `false`
  — the UI never fabricates a user or organization.
- `permissions` is always `[]` and `hasPermission()` always returns
  `false`. The backend has no endpoint to resolve a user's *effective*
  permission set (only their role); reimplementing
  `app/services/permissions.py::ROLE_PERMISSIONS` client-side to derive
  one would drift from the backend's own source of truth, so this was
  deliberately not attempted. Nothing in this milestone's UI depends on
  `hasPermission()` returning `true` — every real enforcement is the
  backend's own 403 response.

Swapping in a real `ProdAuthProvider` later touches exactly one file
(`app/App.tsx`, which provider wraps the router) — no screen changes.

## 4. API layer

`src/services/api/`:

- `config.ts` — `API_BASE_URL` from `VITE_API_BASE_URL`, defaulting to
  `http://localhost:8000/api/v1` for local development only.
- `client.ts` — `apiRequest<T>()`, the only place `fetch` is called from.
  Attaches `X-Client-Request-Id` (echoed by the backend's
  `RequestIdMiddleware`) and the dev-identity header when configured;
  normalizes every failure (HTTP error status OR a network-level
  failure — offline, DNS, **CORS**, see §7) into one `ApiError` type.
- `errors.ts` — `ApiError`, parsed from the backend's own standardized
  error contract (`backend/app/core/errors.py`:
  `{ detail, error: { code, message, request_id } }`).
- `organizations.ts`, `analytics.ts` — typed wrappers around the real
  endpoints actually used (`GET /organizations/{id}`, `GET
  /organizations/{id}/members/{user_id}`, `GET
  /intelligence/analytics/summary`, `GET
  /intelligence/analytics/signals`). Every field mirrors the backend's
  own Pydantic schemas (`backend/app/schemas/intelligence.py`,
  `backend/app/schemas/organization*.py`) exactly — nothing invented.

## 5. Fixtures vs. real data

See `src/fixtures/README.md` for the full rule. Summary: Home uses only
real backend data (no fixture exists for it). Events and Event Detail
are fixture-backed (`src/fixtures/events.ts`) because the backend has no
human-facing read endpoint for `SafetyEvent` records (§7) — accessed
only through the `EventRepository` interface
(`src/features/events/eventRepository.ts`), so swapping in a future
`ApiEventRepository` changes one file
(`src/features/events/useEventRepository.ts`), not the screens. Every
fixture-backed screen visibly discloses this to the user (a small inline
notice — "Showing example event data...") — fixture data is never
presented as live.

## 6. Design tokens

`src/styles/tokens.css`, imported by `src/index.css`. Tailwind v4
CSS-first tokens (`@theme` block) — every `--color-*`/`--radius-*`/
`--shadow-*`/`--font-*` value becomes a matching utility class
automatically (`bg-teal-600`, `rounded-lg`, ...). No component hardcodes
a raw hex value.

**Limitation, stated plainly:** the Figma file
(`https://www.figma.com/design/PkWBneIfrMuMUp8Du8aGnD`, "SIE UX & Brand
Design System v0.1") could not be read directly in this session — the
Figma MCP connection was unavailable. The token *values* (specific hex
codes, exact spacing numbers) are therefore restrained, professional
enterprise-SaaS defaults chosen from the written brief ("light
professional surfaces, white and soft neutral backgrounds, deep navy,
restrained teal, subtle borders, generous whitespace"), not measurements
taken from the Figma file. Every value lives in this one file so a
future pass with real Figma access can correct them centrally without
touching a single component.

## 7. Known backend gaps discovered while building this milestone

These are documented, not worked around — per this milestone's explicit
instruction, the backend was not modified to address any of them.

1. **No human-facing `GET /events` / `GET /events/{id}`.** The backend
   only exposes machine-client event *ingestion*
   (`POST /intelligence/events`, `POST /data/ingestion`) and aggregate
   analytics reads (`summary`/`trends`/`signals`/`features`) — there is
   no endpoint to list or fetch individual `SafetyEvent` records for a
   human-facing UI. This is why Events/Event Detail are fixture-backed.
2. **No CORS configuration.** Verified directly in this session:
   `backend/app/main.py` registers no `CORSMiddleware`, and an `OPTIONS`
   preflight request to any endpoint returns `405 Method Not Allowed`
   with no `Access-Control-Allow-Origin` header. Every endpoint
   works correctly when called server-to-server (verified with `curl`
   against a real seeded organization — `GET /organizations/{id}`, `GET
   /organizations/{id}/members/{user_id}`, and `GET
   /intelligence/analytics/summary` all returned correct data), but a
   **browser** refuses to let this frontend's JavaScript read the
   response from a different origin (`http://localhost:3000` →
   `http://localhost:8000`) without CORS headers. This blocks *any*
   browser-based frontend from calling this API directly, not just this
   one. This frontend's own error handling was verified to degrade
   gracefully under this real failure (Home shows "No organization
   context available" rather than crashing) — but the underlying gap is
   a backend capability that needs to be added (a `CORSMiddleware`
   registration naming the frontend's real origin(s)) before this
   frontend — or any browser-based SIE frontend — can use real data
   end-to-end outside of same-origin deployment.
3. **No endpoint to resolve a user's effective permission set.** Only
   role (`OrganizationMembership.role`) is exposed; turning a role into
   permissions requires `app/services/permissions.py::ROLE_PERMISSIONS`,
   which has no API surface. See §3.
4. **No production login/session endpoint.** Confirmed in
   `backend/app/api/deps_auth.py`'s own docstring.
5. **No Actions/Reports/Knowledge-browse/Administration backend
   capability** beyond what already existed — unchanged from the
   implementation map produced before this milestone; not re-verified
   here since those screens are explicitly out of scope this milestone.

## 8. Verification performed this milestone

- `npm run build`, `npm run lint` (`tsc --noEmit`), and `npm run test`
  (Vitest) all actually run, against the final code, with zero errors —
  see the milestone's own completion report for exact output.
- The dev server was run standalone (`npm run dev`) and inspected in a
  real headless Chromium browser (Playwright, temporarily installed for
  this verification only, then removed — not part of the delivered
  dependency set) across `/`, `/events`, `/events/:id` (existing and
  non-existent ids), and an out-of-scope path (`/actions`, confirmed to
  redirect to Home). Screenshots were visually reviewed for layout and
  visual-language correctness.
- A real backend instance was started locally (PostgreSQL 16 +
  `uvicorn`, migrated to head) and a real organization/user/membership
  seeded through the backend's own existing service layer (not through
  any code added or changed by this milestone) specifically to exercise
  Home's real API integration end-to-end, which is how the CORS gap
  above was discovered and confirmed.
