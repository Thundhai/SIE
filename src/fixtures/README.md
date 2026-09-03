# Fixtures

Everything in this directory is **fictional, isolated placeholder data**
used only where a real backend capability does not exist yet. Nothing
here is loaded from, or represents, real enterprise data.

## The rule this milestone follows (§12 of the spec)

- Use a **real backend API** wherever one actually exists (see
  `src/services/api/`) — Home's analytics/signals data is real.
- Use a **fixture** only where the backend capability does not exist yet
  (Events and Event Detail — the backend has no `GET /events` or
  `GET /events/{id}`; see `docs/FRONTEND_ARCHITECTURE.md`, "Known backend
  gaps").
- **Never** present fixture data as if it were live: no fake "Live"
  badges, no fake current timestamps, no fake sync/response metadata.
  Nothing in this codebase does that — verify before adding new fixture
  UI that it doesn't either.
- Fixtures are consumed **only** through a repository interface (e.g.
  `src/features/events/eventRepository.ts`'s `EventRepository`), never
  imported directly into a page/feature component. When the real
  endpoint exists, only the repository implementation changes
  (`FixtureEventRepository` → `ApiEventRepository`) — no screen
  component changes.

## What's here

- `events.ts` — fictional `SafetyEventSummary`/`SafetyEventDetail`
  records backing the Events and Event Detail screens.
