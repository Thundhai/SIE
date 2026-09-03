# SIE Frontend Architecture

Originally written for **SIE Frontend Foundation & Core UX Implementation
v0.1** — the *new* SIE frontend (Home, Events, Event Detail), its
architecture, design tokens, and the legacy-vs-new boundary. §3, §5, and
§7 below were updated for the **SIE Enterprise Read API & Browser
Integration Foundation v0.1** milestone, which resolved the backend gaps
§7 originally documented (real Events API, effective permissions, CORS)
— see `docs/ENTERPRISE_API.md` for that milestone's own backend-side
documentation, including its architecture diagram and CORS
verification. This document does not cover the backend itself (see
`backend/README.md`).

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
                            (interface), apiEventRepository.ts (real API),
                            fixtureEventRepository.ts (example-data fallback)
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
- `permissions`/`hasPermission()` are backed by the real
  `GET /api/v1/auth/me` endpoint (SIE Enterprise Read API & Browser
  Integration Foundation v0.1 — `backend/app/api/v1/auth.py`), which
  serializes the backend's own already-computed, already-authoritative
  effective permission set. This frontend still carries no copy of
  `app/services/permissions.py::ROLE_PERMISSIONS` — see
  `docs/ENTERPRISE_API.md` §6. `hasPermission()` remains display-only:
  every real enforcement is still the backend's own 403 response,
  whether or not a screen also checks this first.

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
- `organizations.ts`, `analytics.ts`, `events.ts`, `auth.ts`, `sites.ts`
  — typed wrappers around the real endpoints actually used (`GET
  /organizations/{id}`, `GET /organizations/{id}/members/{user_id}`,
  `GET /intelligence/analytics/summary`, `GET
  /intelligence/analytics/signals`, `GET /events`, `GET /events/{id}`,
  `GET /auth/me`, `GET /organizations/{id}/sites`). Every field mirrors
  the backend's own Pydantic schemas (`backend/app/schemas/
  intelligence.py`, `organization*.py`, `events.py`, `auth.py`,
  `site.py`) exactly — nothing invented.

## 5. Fixtures vs. real data

See `src/fixtures/README.md` for the full rule. Home, Events, and Event
Detail all use real backend data now: Events/Event Detail talk to the
real `GET /api/v1/events`/`GET /api/v1/events/{id}` endpoints (SIE
Enterprise Read API & Browser Integration Foundation v0.1 — see
`docs/ENTERPRISE_API.md`) through `ApiEventRepository`
(`src/features/events/apiEventRepository.ts`), reached only through the
same `EventRepository` interface (`eventRepository.ts`) the fixture
implementation always used — no screen changed to adopt it.
`useEventRepository.ts` (`src/features/events/`) is the one place that
decides which implementation is active: `ApiEventRepository` once a real
organization is established (`useAuth().organization`), falling back to
`FixtureEventRepository` only when no dev identity is configured or it
failed to resolve (e.g. local development with no backend running).
`EventsPage`/`EventDetailPage` render their "showing example event
data" disclosure only when the active repository actually reports
`isFixtureBacked` — never unconditionally — so fixture data is still
never presented as live.

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

## 7. Known backend gaps

Gaps 1-3 below, discovered while building the original Frontend
Foundation v0.1 milestone, were resolved by the **SIE Enterprise Read
API & Browser Integration Foundation v0.1** milestone — kept here,
marked resolved, rather than deleted, so the history of what this
frontend had to work around is not lost. See `docs/ENTERPRISE_API.md`
for that milestone's own documentation of what it built and how it was
verified. Gaps 4-5 remain open.

1. ~~**No human-facing `GET /events` / `GET /events/{id}`.**~~
   **Resolved.** `backend/app/api/v1/events.py` now provides both,
   tenant-isolated, paginated, filtered, and searched server-side — see
   `docs/ENTERPRISE_API.md` §2-3. Events/Event Detail are real-data
   screens now (§5 above).
2. ~~**No CORS configuration.**~~ **Resolved.** `backend/app/main.py`
   now registers a configurable `CORSMiddleware`
   (`settings.CORS_ALLOWED_ORIGINS`), verified against a real running
   server (both real `curl` preflight requests and this repository's own
   `backend/tests/test_cors.py`) — see `docs/ENTERPRISE_API.md` §4.
3. ~~**No endpoint to resolve a user's effective permission set.**~~
   **Resolved.** `GET /api/v1/auth/me` (`backend/app/api/v1/auth.py`)
   serializes the backend's own real, already-computed permission set —
   see `docs/ENTERPRISE_API.md` §6 and §3 above.
4. **No production login/session endpoint.** Still open — a real
   OIDC/OAuth2 `TokenVerifier` implementation remains external
   infrastructure this milestone did not build; the seam it plugs into
   already exists and is documented in `docs/ENTERPRISE_API.md` §5's
   Implemented/seam-only/external-infrastructure table.
5. **No Actions/Reports/Knowledge-browse/Administration backend
   capability** beyond what already existed — unchanged; out of scope
   for both frontend milestones so far.

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
