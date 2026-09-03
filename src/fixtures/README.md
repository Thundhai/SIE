# Fixtures

Everything in this directory is **fictional, isolated placeholder data**
used only where a real backend capability does not exist, or where no
real identity/organization is currently established. Nothing here is
loaded from, or represents, real enterprise data.

## The rule this milestone follows

- Use a **real backend API** wherever one actually exists (see
  `src/services/api/`) — Home's analytics/signals data, and, as of the
  Enterprise Read API & Browser Integration Foundation v0.1 milestone,
  Events and Event Detail (`GET /events`/`GET /events/{id}` — see
  `docs/ENTERPRISE_API.md`), are all real.
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
  (`src/features/events/eventRepository.ts`'s `EventRepository`), never
  imported directly into a page/feature component. `useEventRepository()`
  is the one place that decides `FixtureEventRepository` vs.
  `ApiEventRepository` — no screen component changes based on which is
  active.

## What's here

- `events.ts` — fictional `SafetyEventSummary`/`SafetyEventDetail`
  records used by `FixtureEventRepository`, for local development without
  a running backend and for tests that want deterministic, offline data.
