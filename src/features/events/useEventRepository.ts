import { useMemo } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { ApiEventRepository } from './apiEventRepository';
import { FixtureEventRepository } from './fixtureEventRepository';
import type { EventRepository } from './eventRepository';

/**
 * The one place that decides which `EventRepository` implementation the
 * Events/Event Detail screens use — SIE Enterprise Read API & Browser
 * Integration Foundation v0.1. When a real organization is established
 * (`useAuth().organization`, resolved against the real backend — see
 * `auth/DevAuthProvider.tsx`), the screens talk to the real
 * `GET /events`/`GET /events/{id}` endpoints through `ApiEventRepository`.
 * Only when no organization is established (no dev identity configured,
 * or it failed to resolve) do the screens fall back to
 * `FixtureEventRepository`, so local development without a running
 * backend still has something to look at — see `EventsPage`'s own
 * fixture-disclosure banner, which reads `isFixtureBacked` off whichever
 * repository this returns rather than guessing.
 */
export function useEventRepository(): EventRepository {
  const { organization } = useAuth();
  return useMemo<EventRepository>(
    () => (organization ? new ApiEventRepository(organization.id) : new FixtureEventRepository()),
    [organization],
  );
}
