import { useMemo } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { ApiActionRepository } from './apiActionRepository';
import { FixtureActionRepository } from './fixtureActionRepository';
import type { ActionRepository } from './actionRepository';

/**
 * The one place that decides which `ActionRepository` implementation the
 * Actions/Action Detail screens use — mirrors `useEventRepository.ts`'s
 * own reasoning exactly. When a real organization is established
 * (`useAuth().organization`), the screens talk to the real
 * `/api/v1/actions` endpoints through `ApiActionRepository`. Only when
 * no organization is established do the screens fall back to
 * `FixtureActionRepository`, so local development without a running
 * backend still has something to look at — see `ActionsPage`'s own
 * fixture-disclosure banner, which reads `isFixtureBacked` off whichever
 * repository this returns rather than guessing.
 */
export function useActionRepository(): ActionRepository {
  const { organization } = useAuth();
  return useMemo<ActionRepository>(
    () => (organization ? new ApiActionRepository(organization.id) : new FixtureActionRepository()),
    [organization],
  );
}
