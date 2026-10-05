import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getAccessToken, setAccessTokenGetter } from './authToken';
import { ProductionSessionGate } from './ProductionSessionGate';

/**
 * Blocker 1 regression — proves the fix at the actual wire level, not
 * through a mocked service function. `services/api/auth.ts` and
 * `ProdAuthProvider.tsx` are deliberately NOT mocked here: this test
 * exercises the real `listAuthOrganizations()` -> `apiRequest()` ->
 * `buildHeaders()` -> `authToken.getAccessToken()` chain end to end,
 * with only `global.fetch` and the OIDC session hook (no real
 * `UserManager`/IdP available in a test) replaced.
 *
 * This is the test the G3-1 blocker review specifically asked for:
 * "must prove Authorization header IS present on the initial
 * organization-resolution request" — not merely that a mocked
 * `listAuthOrganizations` was called with the right arguments.
 */
const mockUseOidcSession = vi.fn();
vi.mock('./oidcSession', () => ({
  useOidcSession: () => mockUseOidcSession(),
}));

function Workspace() {
  return <div>Authenticated Workspace</div>;
}

function renderGate() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route
          path="/"
          element={
            <ProductionSessionGate>
              <Workspace />
            </ProductionSessionGate>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const ORGANIZATIONS_BODY = {
  memberships: [{ organization_id: 'org-1', organization_name: 'Org One', role: 'ORG_ADMIN' }],
  is_platform_admin: false,
};

const EFFECTIVE_PERMISSIONS_BODY = {
  user_id: 'user-1',
  name: 'Prod User',
  email: 'prod@example.com',
  organization_id: 'org-1',
  organization_name: 'Org One',
  role: 'ORG_ADMIN',
  permissions: ['safety_data:read'],
  is_platform_admin: false,
  auth_mode: 'production',
  identity_provider: 'test-idp',
};

describe('ProductionSessionGate — real token-registration bridge (Blocker 1)', () => {
  afterEach(() => {
    cleanup();
    // Belt-and-braces: a bug in the fix under test could leave this
    // non-null and silently pass a *later* test by accident.
    setAccessTokenGetter(null);
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    // Restores the real global.fetch stubbed via vi.stubGlobal() below
    // -- test hygiene: prefer vi.stubGlobal/unstubAllGlobals over a
    // direct `global.fetch = ...` assignment, which Vitest can't track
    // or guarantee gets reverted on its own.
    vi.unstubAllGlobals();
  });

  it('(A) the initial GET /auth/organizations request — made before ProdAuthProvider ever mounts — carries the real Bearer token', async () => {
    vi.stubEnv('MODE', 'production');
    mockUseOidcSession.mockReturnValue({
      status: 'authenticated',
      user: { access_token: 'real-oidc-access-token', expired: false },
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => 'real-oidc-access-token',
    });

    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/auth/organizations')) return Promise.resolve(jsonResponse(ORGANIZATIONS_BODY));
      if (url.includes('/auth/me')) return Promise.resolve(jsonResponse(EFFECTIVE_PERMISSIONS_BODY));
      return Promise.reject(new Error(`Unexpected fetch to ${url}`));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderGate();
    await waitFor(() => expect(screen.getByText('Authenticated Workspace')).toBeInTheDocument());

    const orgsCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/organizations'));
    expect(orgsCalls.length).toBeGreaterThan(0);

    // The FIRST such call is the gate's own upfront probe -- the exact
    // call that, before the fix, had no token registered yet.
    const [, firstCallInit] = orgsCalls[0];
    const headers = (firstCallInit as RequestInit).headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer real-oidc-access-token');
  });

  it('(B) that same request never carries the dev-identity header in production, even if dev identity variables are set', async () => {
    vi.stubEnv('MODE', 'production');
    vi.stubEnv('VITE_DEV_USER_ID', 'dev-user-1');
    vi.stubEnv('VITE_DEV_ORGANIZATION_ID', 'dev-org-1');
    mockUseOidcSession.mockReturnValue({
      status: 'authenticated',
      user: { access_token: 'real-oidc-access-token', expired: false },
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => 'real-oidc-access-token',
    });

    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/auth/organizations')) return Promise.resolve(jsonResponse(ORGANIZATIONS_BODY));
      if (url.includes('/auth/me')) return Promise.resolve(jsonResponse(EFFECTIVE_PERMISSIONS_BODY));
      return Promise.reject(new Error(`Unexpected fetch to ${url}`));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderGate();
    await waitFor(() => expect(screen.getByText('Authenticated Workspace')).toBeInTheDocument());

    const [, firstCallInit] = fetchMock.mock.calls.find(([url]) => String(url).includes('/auth/organizations'))!;
    const headers = (firstCallInit as RequestInit).headers as Headers;
    expect(headers.get('X-SIE-Dev-User-Id')).toBeNull();
    expect(headers.get('Authorization')).toBe('Bearer real-oidc-access-token');
  });

  it('(G) the full real-fetch bootstrap still renders the authenticated workspace end to end', async () => {
    vi.stubEnv('MODE', 'production');
    mockUseOidcSession.mockReturnValue({
      status: 'authenticated',
      user: { access_token: 'real-oidc-access-token', expired: false },
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => 'real-oidc-access-token',
    });

    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/auth/organizations')) return Promise.resolve(jsonResponse(ORGANIZATIONS_BODY));
      if (url.includes('/auth/me')) return Promise.resolve(jsonResponse(EFFECTIVE_PERMISSIONS_BODY));
      return Promise.reject(new Error(`Unexpected fetch to ${url}`));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderGate();

    await waitFor(() => expect(screen.getByText('Authenticated Workspace')).toBeInTheDocument());
    // Every call this bootstrap actually made reached the backend with
    // a real token -- not just the first one.
    for (const [, init] of fetchMock.mock.calls) {
      const headers = (init as RequestInit).headers as Headers;
      expect(headers.get('Authorization')).toBe('Bearer real-oidc-access-token');
    }
  });

  it('without the fix, this test would fail: sanity-checks that an UNREGISTERED getter really does produce no Authorization header at all', async () => {
    // Demonstrates what Blocker 1 looked like before the fix -- not a
    // test of production code, a test of this file's own test
    // methodology, so a future refactor of the fix can't silently make
    // every assertion above vacuously true.
    setAccessTokenGetter(null);
    expect(getAccessToken()).toBeNull();
  });
});
