import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, useAuth } from './AuthContext';
import { OrganizationSwitchProvider, useOrganizationSwitch } from './OrganizationSwitchProvider';
import { readPersistedOrganizationId } from './organizationPersistence';
import { ApiError } from '../services/api/errors';
import type { AuthContextValue } from './types';

const mockGetEffectivePermissions = vi.fn();
vi.mock('../services/api/auth', () => ({
  getEffectivePermissions: (organizationId: string, signal?: AbortSignal) =>
    mockGetEffectivePermissions(organizationId, signal),
  listAuthOrganizations: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  window.sessionStorage.clear();
});

const MULTI_ORG_BASE: AuthContextValue = {
  isAuthenticated: true,
  isDevIdentity: false,
  user: { id: 'u1', name: 'Jordan Casey', email: 'jordan@example.com' },
  organization: { id: 'org-a', name: 'Org A' },
  memberships: [
    { organizationId: 'org-a', organizationName: 'Org A', role: 'ORG_ADMIN' },
    { organizationId: 'org-b', organizationName: 'Org B', role: 'VIEWER' },
    { organizationId: 'org-c', organizationName: 'Org C', role: 'VIEWER' },
  ],
  permissions: ['safety_data:read', 'safety_data:manage'],
  hasPermission: (p) => ['safety_data:read', 'safety_data:manage'].includes(p),
};

function effectivePermissionsFor(organizationId: string, organizationName: string, permissions: string[]) {
  return {
    user_id: 'u1',
    name: 'Jordan Casey',
    email: 'jordan@example.com',
    organization_id: organizationId,
    organization_name: organizationName,
    role: 'VIEWER',
    permissions,
    is_platform_admin: false,
    auth_mode: 'production',
    identity_provider: 'test-idp',
  };
}

/** Deliberately reads/exercises the real public surface -- `useAuth()`
 * for the organization context every existing consumer already reads,
 * `useOrganizationSwitch()` for the switch action this milestone adds —
 * never a private implementation detail. */
function Probe() {
  const auth = useAuth();
  const { switchState, switchingToOrganizationId, switchErrorMessage, switchOrganization } = useOrganizationSwitch();
  return (
    <div>
      <p data-testid="org-id">{auth.organization?.id ?? 'none'}</p>
      <p data-testid="org-name">{auth.organization?.name ?? 'none'}</p>
      <p data-testid="permissions">{auth.permissions.join(',')}</p>
      <p data-testid="switch-state">{switchState}</p>
      <p data-testid="switching-to">{switchingToOrganizationId ?? 'none'}</p>
      <p data-testid="switch-error">{switchErrorMessage ?? 'none'}</p>
      <button onClick={() => void switchOrganization('org-b')}>Switch to B</button>
      <button onClick={() => void switchOrganization('org-nonexistent')}>Switch to nonexistent</button>
    </div>
  );
}

function renderWithBase(base: AuthContextValue) {
  return render(
    <AuthContext.Provider value={base}>
      <OrganizationSwitchProvider>
        <Probe />
      </OrganizationSwitchProvider>
    </AuthContext.Provider>,
  );
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  promise.catch(() => {});
  return { promise, resolve, reject };
}

describe('OrganizationSwitchProvider — one authoritative active-organization state', () => {
  it('passes the base AuthContextValue through unchanged when no switch has occurred', () => {
    renderWithBase(MULTI_ORG_BASE);
    expect(screen.getByTestId('org-id')).toHaveTextContent('org-a');
    expect(screen.getByTestId('permissions')).toHaveTextContent('safety_data:read,safety_data:manage');
    expect(screen.getByTestId('switch-state')).toHaveTextContent('idle');
  });

  it('(core proof) Org A active -> switch B -> GET /auth/me?organization_id=B -> permissions change -> B becomes active', async () => {
    mockGetEffectivePermissions.mockResolvedValue(effectivePermissionsFor('org-b', 'Org B', ['knowledge:read']));
    renderWithBase(MULTI_ORG_BASE);

    await userEvent.click(screen.getByText('Switch to B'));

    await waitFor(() => expect(screen.getByTestId('org-id')).toHaveTextContent('org-b'));
    expect(mockGetEffectivePermissions).toHaveBeenCalledWith('org-b', expect.anything());
    expect(screen.getByTestId('org-name')).toHaveTextContent('Org B');
    // Org B's permissions, not Org A's -- never a carried-over or
    // unioned set.
    expect(screen.getByTestId('permissions')).toHaveTextContent('knowledge:read');
    expect(screen.getByTestId('permissions')).not.toHaveTextContent('safety_data:read');
  });

  it('previous organization permissions are never reused for the new organization', async () => {
    mockGetEffectivePermissions.mockResolvedValue(effectivePermissionsFor('org-b', 'Org B', []));
    renderWithBase(MULTI_ORG_BASE);

    await userEvent.click(screen.getByText('Switch to B'));

    await waitFor(() => expect(screen.getByTestId('org-id')).toHaveTextContent('org-b'));
    // Org B's real response carries NO permissions -- confirms this
    // isn't a union/merge with Org A's permissions, which were non-empty.
    expect(screen.getByTestId('permissions')).toHaveTextContent('');
  });

  it('switching refreshes organization-scoped data: a fresh `organization` object reference lets existing useEffect/useMemo([organization]) consumers refetch', async () => {
    mockGetEffectivePermissions.mockResolvedValue(effectivePermissionsFor('org-b', 'Org B', []));
    let latestOrg: unknown;
    function OrgIdentityProbe() {
      const auth = useAuth();
      latestOrg = auth.organization;
      return null;
    }
    render(
      <AuthContext.Provider value={MULTI_ORG_BASE}>
        <OrganizationSwitchProvider>
          <Probe />
          <OrgIdentityProbe />
        </OrganizationSwitchProvider>
      </AuthContext.Provider>,
    );
    const firstOrgRef = latestOrg;

    await userEvent.click(screen.getByText('Switch to B'));
    await waitFor(() => expect(screen.getByTestId('org-id')).toHaveTextContent('org-b'));

    expect(latestOrg).not.toBe(firstOrgRef);
  });

  it('persists the switched-to organization id for restoration on reload', async () => {
    mockGetEffectivePermissions.mockResolvedValue(effectivePermissionsFor('org-b', 'Org B', []));
    renderWithBase(MULTI_ORG_BASE);

    await userEvent.click(screen.getByText('Switch to B'));

    await waitFor(() => expect(readPersistedOrganizationId()).toBe('org-b'));
  });

  describe('SECURITY — tenant safety', () => {
    it('an organization id absent from the authenticated memberships list is never activated, and no request is made', async () => {
      renderWithBase(MULTI_ORG_BASE);

      await userEvent.click(screen.getByText('Switch to nonexistent'));

      expect(mockGetEffectivePermissions).not.toHaveBeenCalled();
      expect(screen.getByTestId('org-id')).toHaveTextContent('org-a');
      expect(screen.getByTestId('switch-state')).toHaveTextContent('error');
    });

    it('a 403 switching to an authorized-looking but backend-forbidden organization does not activate it', async () => {
      mockGetEffectivePermissions.mockRejectedValue(new ApiError('Forbidden', { status: 403 }));
      renderWithBase(MULTI_ORG_BASE);

      await userEvent.click(screen.getByText('Switch to B'));

      await waitFor(() => expect(screen.getByTestId('switch-state')).toHaveTextContent('error'));
      expect(screen.getByTestId('org-id')).toHaveTextContent('org-a');
      expect(screen.getByTestId('switch-error')).toHaveTextContent('You do not have access');
    });

    it('a 403 during switch does NOT log the user out — isAuthenticated remains true', async () => {
      mockGetEffectivePermissions.mockRejectedValue(new ApiError('Forbidden', { status: 403 }));
      function AuthenticatedProbe() {
        const auth = useAuth();
        return <p data-testid="is-authenticated">{String(auth.isAuthenticated)}</p>;
      }
      render(
        <AuthContext.Provider value={MULTI_ORG_BASE}>
          <OrganizationSwitchProvider>
            <Probe />
            <AuthenticatedProbe />
          </OrganizationSwitchProvider>
        </AuthContext.Provider>,
      );

      await userEvent.click(screen.getByText('Switch to B'));

      await waitFor(() => expect(screen.getByTestId('switch-state')).toHaveTextContent('error'));
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('true');
    });

    it('a 401 during switch does not activate the target organization and clears to the (already global) session-invalidation path rather than showing a switch-failed banner', async () => {
      mockGetEffectivePermissions.mockRejectedValue(new ApiError('Unauthorized', { status: 401 }));
      renderWithBase(MULTI_ORG_BASE);

      await userEvent.click(screen.getByText('Switch to B'));

      await waitFor(() => expect(screen.getByTestId('switch-state')).toHaveTextContent('idle'));
      expect(screen.getByTestId('org-id')).toHaveTextContent('org-a');
      expect(screen.getByTestId('switch-error')).toHaveTextContent('none');
    });

    it('a network/other failure retains the previous organization and allows retry', async () => {
      mockGetEffectivePermissions.mockRejectedValueOnce(new Error('network down'));
      renderWithBase(MULTI_ORG_BASE);

      await userEvent.click(screen.getByText('Switch to B'));
      await waitFor(() => expect(screen.getByTestId('switch-state')).toHaveTextContent('error'));
      expect(screen.getByTestId('org-id')).toHaveTextContent('org-a');

      mockGetEffectivePermissions.mockResolvedValueOnce(effectivePermissionsFor('org-b', 'Org B', []));
      await userEvent.click(screen.getByText('Switch to B'));
      await waitFor(() => expect(screen.getByTestId('org-id')).toHaveTextContent('org-b'));
    });
  });

  describe('switching state / race safety', () => {
    it('models idle -> switching -> idle across a successful switch', async () => {
      const deferred = createDeferred<ReturnType<typeof effectivePermissionsFor>>();
      mockGetEffectivePermissions.mockReturnValue(deferred.promise);
      renderWithBase(MULTI_ORG_BASE);

      expect(screen.getByTestId('switch-state')).toHaveTextContent('idle');

      const user = userEvent.setup();
      void user.click(screen.getByText('Switch to B'));
      await waitFor(() => expect(screen.getByTestId('switch-state')).toHaveTextContent('switching'));
      expect(screen.getByTestId('switching-to')).toHaveTextContent('org-b');

      await act(async () => {
        deferred.resolve(effectivePermissionsFor('org-b', 'Org B', []));
        await deferred.promise;
      });

      await waitFor(() => expect(screen.getByTestId('switch-state')).toHaveTextContent('idle'));
      expect(screen.getByTestId('org-id')).toHaveTextContent('org-b');
    });

    it('rapid repeated switching cannot leave the context inconsistent: a second switch call while one is in flight is a no-op', async () => {
      const deferred = createDeferred<ReturnType<typeof effectivePermissionsFor>>();
      mockGetEffectivePermissions.mockReturnValue(deferred.promise);
      renderWithBase(MULTI_ORG_BASE);

      const user = userEvent.setup();
      void user.click(screen.getByText('Switch to B'));
      await waitFor(() => expect(screen.getByTestId('switch-state')).toHaveTextContent('switching'));

      // A second, rapid click while the first switch is still in flight.
      await user.click(screen.getByText('Switch to B'));
      // Only the first call should ever have reached the API.
      expect(mockGetEffectivePermissions).toHaveBeenCalledTimes(1);

      await act(async () => {
        deferred.resolve(effectivePermissionsFor('org-b', 'Org B', []));
        await deferred.promise;
      });
      await waitFor(() => expect(screen.getByTestId('org-id')).toHaveTextContent('org-b'));
    });

    it('CONCURRENCY: two switchOrganization() calls issued in the same tick, before any React state commits, still only let the first one through', async () => {
      // Deliberately does NOT go through userEvent -- a click handler's
      // own dispatch already has scheduling between the two events that
      // would hide the exact bug this test exists to catch (two calls
      // genuinely interleaved before `switchState` has had a chance to
      // commit "switching"). Capturing `switchOrganization` itself and
      // calling it twice back to back, synchronously, with no `await`
      // between the two calls, is the only way to reproduce that.
      const switchRef: { current: ((organizationId: string) => Promise<void>) | null } = { current: null };
      function CaptureSwitch() {
        const { switchOrganization } = useOrganizationSwitch();
        switchRef.current = switchOrganization;
        return null;
      }

      const deferredB = createDeferred<ReturnType<typeof effectivePermissionsFor>>();
      const deferredC = createDeferred<ReturnType<typeof effectivePermissionsFor>>();
      mockGetEffectivePermissions.mockImplementation((organizationId: string) =>
        organizationId === 'org-b' ? deferredB.promise : deferredC.promise,
      );

      render(
        <AuthContext.Provider value={MULTI_ORG_BASE}>
          <OrganizationSwitchProvider>
            <Probe />
            <CaptureSwitch />
          </OrganizationSwitchProvider>
        </AuthContext.Provider>,
      );

      let first!: Promise<void>;
      let second!: Promise<void>;
      act(() => {
        // Same synchronous tick, no `await` between these two calls --
        // exactly the scenario a React-state-only guard cannot defend
        // against (both would observe `switchState.status === 'idle'`),
        // and exactly what the synchronous `switchInFlightRef` guard
        // must defend against instead.
        first = switchRef.current!('org-b');
        second = switchRef.current!('org-c');
      });

      // Only the first call's request was ever made -- the second was
      // rejected before it could reach the API at all.
      expect(mockGetEffectivePermissions).toHaveBeenCalledTimes(1);
      expect(mockGetEffectivePermissions).toHaveBeenCalledWith('org-b', expect.anything());

      await act(async () => {
        deferredB.resolve(effectivePermissionsFor('org-b', 'Org B', ['safety_data:read']));
        await first;
        await second;
      });

      // The eventual active organization is the first accepted target,
      // never the second (which was ignored, not queued) -- and the
      // override is the real, single, consistent one the first call's
      // own backend response produced, not a hybrid of the two.
      expect(screen.getByTestId('org-id')).toHaveTextContent('org-b');
      expect(screen.getByTestId('permissions')).toHaveTextContent('safety_data:read');
      expect(screen.getByTestId('switch-state')).toHaveTextContent('idle');
      // deferredC's own promise is simply left unsettled forever (the
      // second call returned before ever awaiting it) -- confirmed by
      // the single call count above, not by resolving it.
    });

    it('selecting the already-active organization is a no-op (no request, no state change)', async () => {
      renderWithBase(MULTI_ORG_BASE);
      function SwitchToA() {
        const { switchOrganization } = useOrganizationSwitch();
        return <button onClick={() => void switchOrganization('org-a')}>Switch to A</button>;
      }
      render(
        <AuthContext.Provider value={MULTI_ORG_BASE}>
          <OrganizationSwitchProvider>
            <Probe />
            <SwitchToA />
          </OrganizationSwitchProvider>
        </AuthContext.Provider>,
      );

      await userEvent.click(screen.getAllByText('Switch to A')[0]);
      expect(mockGetEffectivePermissions).not.toHaveBeenCalled();
    });
  });

  describe('base-session invalidation discards a stale override', () => {
    it('signing out (base becomes unauthenticated) clears any active switch override', async () => {
      mockGetEffectivePermissions.mockResolvedValue(effectivePermissionsFor('org-b', 'Org B', []));
      const { rerender } = render(
        <AuthContext.Provider value={MULTI_ORG_BASE}>
          <OrganizationSwitchProvider>
            <Probe />
          </OrganizationSwitchProvider>
        </AuthContext.Provider>,
      );

      await userEvent.click(screen.getByText('Switch to B'));
      await waitFor(() => expect(screen.getByTestId('org-id')).toHaveTextContent('org-b'));

      rerender(
        <AuthContext.Provider
          value={{
            isAuthenticated: false,
            isDevIdentity: false,
            user: null,
            organization: null,
            memberships: [],
            permissions: [],
            hasPermission: () => false,
          }}
        >
          <OrganizationSwitchProvider>
            <Probe />
          </OrganizationSwitchProvider>
        </AuthContext.Provider>,
      );

      expect(screen.getByTestId('org-id')).toHaveTextContent('none');
    });
  });
});
