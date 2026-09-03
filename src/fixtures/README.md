# Fixtures

Everything in this directory is **fictional, isolated placeholder data**
used only where a real backend capability does not exist, or where no
real identity/organization is currently established. Nothing here is
loaded from, or represents, real enterprise data.

## The rule this milestone follows

- Use a **real backend API** wherever one actually exists (see
  `src/services/api/`) — Home's analytics/signals data, Events and Event
  Detail (`GET /events`/`GET /events/{id}` — see `docs/ENTERPRISE_API.md`),
  and, as of SIE Milestone 18, Actions and Action Detail
  (`/api/v1/actions` — see `docs/ACTIONS_DOMAIN.md` and
  `docs/FRONTEND_ARCHITECTURE.md` §9), are all real.
- Fall back to a **fixture** only when no real organization is currently
  established (no dev identity configured, or it failed to resolve
  against the backend — see `src/auth/DevAuthProvider.tsx`) — never as a
  standing substitute for a real endpoint that exists.
- **Never** present fixture data as if it were live: no fake "Live"
  badges, no fake current timestamps, no fake sync/response metadata.
  Nothing in this codebase does that — verify before adding new fixture
  UI that it doesn't either. `EventsPage`/`EventDetailPage` only render
  their "showing example event data" disclosure when the active
  repository actually reports itself as fixture-backed
  (`EventRepository.isFixtureBacked`), never unconditionally.
- Fixtures are consumed **only** through a repository interface
  (`src/features/events/eventRepository.ts`'s `EventRepository`,
  `src/features/actions/actionRepository.ts`'s `ActionRepository`), never
  imported directly into a page/feature component. `useEventRepository()`/
  `useActionRepository()` are the one place each decides its fixture vs.
  real-API implementation — no screen component changes based on which is
  active.

## What's here

- `events.ts` — fictional `SafetyEventSummary`/`SafetyEventDetail`
  records used by `FixtureEventRepository`, for local development without
  a running backend and for tests that want deterministic, offline data.
- `actions.ts` — fictional `SafetyAction` records used by
  `FixtureActionRepository` for the same purpose. Some entries reference
  `events.ts`'s own fixture event ids as their `sourceEventId`
  (e.g. `EVT-1001`), so Event Detail's "Related action" area has
  something real to show end-to-end even without a backend.
