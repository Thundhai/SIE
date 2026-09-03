import { useMemo } from 'react';
import { FixtureEventRepository } from './fixtureEventRepository';
import type { EventRepository } from './eventRepository';

/**
 * The one place that decides which `EventRepository` implementation the
 * Events/Event Detail screens use. Today it always returns the fixture
 * repository (the backend has no read endpoint yet — see
 * `src/fixtures/README.md`). Once `GET /events`/`GET /events/{id}`
 * exist, this becomes the only function that changes to switch the
 * whole feature over to live data.
 */
export function useEventRepository(): EventRepository {
  return useMemo(() => new FixtureEventRepository(), []);
}
