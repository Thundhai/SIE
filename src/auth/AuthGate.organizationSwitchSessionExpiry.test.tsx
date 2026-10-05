import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthGate } from './AuthGate';
import { useOrganizationSwitch } from './OrganizationSwitchProvider';

/**
 * SIE Milestone G3-3 — the end-to-end security requirement the task
 * calls out explicitly: "session expiration during a switch returns to
 * /login". Renders through the REAL `AuthGate` -> `ProductionSessionGate`
 * -> `ProdAuthProvider` -> `OrganizationSwitchProvider` stack, with only
 * the OIDC hook mocked and `global.fetch` stubbed (not
 * `services/api/auth.ts` itself) so the REAL `apiRequest()`/`client.ts`
 * chain runs for real -- this is deliberate: that chain is exactly where
 * `notifySessionInvalidated()` is called on any 401
 * (`services/api/client.ts`), and this test exists specifically to prove
 * that mechanism actually fires for a 401 arising from the NEW switch
 * call, not only from `ProdAuthProvider`'s own bootstrap call:
 *
 *   OrganizationSwitchProvider's getEffectivePermissions(B) -> real
 *   apiRequest() -> fetch -> 401 -> notifySessionInvalidated()
 *     -> ProductionSessionGate's registered handler -> signOutLocally()
 *     -> oidc.status becomes 'unauthenticated' -> <Navigate to="/login">
 */
const mockUseOidcSession = vi.fn();
vi.mock('./oidcSession', () => ({
  useOidcSession: () => mockUseOidcSession(),
}));

afterEach(() => {
  vi.resetAllMocks();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function Workspace() {
  const { switchOrganization } = useOrganizationSwitch();
  return <button onClick={() => void switchOrganization('org-b')}>Switch to Org B</button>;
}

function appTree() {
  return (
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route
          path="/"
          element={
            <AuthGate>
              <Workspace />
            </AuthGate>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function renderApp() {
  return render(appTree());
}

const ORGANIZATIONS_BODY = {
  memberships: [
    { organization_id: 'org-a', organization_name: 'Org A', role: 'ORG_ADMIN' },
    { organization_id: 'org-b', organization_name: 'Org B', role: 'ORG_ADMIN' },
  ],
  is_platform_admin: false,
};

describe('session expiration during an organization switch (end to end, real fetch chain)', () => {
  it('a 401 switching organizations invalidates the session and returns to /login', async () => {
    vi.stubEnv('MODE', 'production');
    // Mirrors ProductionSessionGate.test.tsx's own test (F) pattern: the
    // real `useOidcSession()` hook flips its own `status` to
    // 'unauthenticated' as a side effect of `signOutLocally()` actually
    // firing the UserManager's `userUnloaded` event -- this mock
    // reproduces that same observable effect so the gate's `oidc.status`
    // dependency has something real to react to.
    const signOutLocally = vi.fn().mockImplementation(async () => {
      mockUseOidcSession.mockReturnValue({
        status: 'unauthenticated',
        user: null,
        error: null,
        signIn: vi.fn(),
        signOutLocally,
        getAccessTokenLive: () => null,
      });
    });
    mockUseOidcSession.mockReturnValue({
      status: 'authenticated',
      user: { access_token: 'tok-1', expired: false },
      error: null,
      signIn: vi.fn(),
      signOutLocally,
      getAccessTokenLive: () => 'tok-1',
    });

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/auth/organizations')) return Promise.resolve(jsonResponse(ORGANIZATIONS_BODY));
      if (url.includes('organization_id=org-a')) {
        return Promise.resolve(
          jsonResponse({
            user_id: 'u1',
            name: 'Jordan Casey',
            email: 'jordan@example.com',
            organization_id: 'org-a',
            organization_name: 'Org A',
            role: 'ORG_ADMIN',
            permissions: ['safety_data:read'],
            is_platform_admin: false,
            auth_mode: 'production',
            identity_provider: 'test-idp',
          }),
        );
      }
      if (url.includes('organization_id=org-b')) {
        // The switch target -- this specific request is the one that
        // has lost its session.
        return Promise.resolve(jsonResponse({ detail: 'Invalid or expired authentication token.' }, 401));
      }
      return Promise.reject(new Error(`Unexpected fetch to ${url}`));
    });
    vi.stubGlobal('fetch', fetchMock);

    const { rerender } = renderApp();
    await waitFor(() => expect(screen.getByText('Switch to Org B')).toBeInTheDocument());

    await userEvent.click(screen.getByText('Switch to Org B'));

    await waitFor(() => expect(signOutLocally).toHaveBeenCalled());
    // Forces the tree to re-read the now-updated mocked oidc status --
    // see this test's own comment on why a mocked hook needs this nudge
    // where a real one wouldn't.
    rerender(appTree());

    await waitFor(() => expect(screen.getByText('Login Page')).toBeInTheDocument());
  });
});
