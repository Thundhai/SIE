import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../services/api/errors';
import { ProductionSessionGate } from './ProductionSessionGate';

const mockUseOidcSession = vi.fn();
vi.mock('./oidcSession', () => ({
  useOidcSession: () => mockUseOidcSession(),
}));

vi.mock('../services/api/auth', () => ({
  getEffectivePermissions: vi.fn(),
  listAuthOrganizations: vi.fn(),
}));

import { getEffectivePermissions, listAuthOrganizations } from '../services/api/auth';

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

const EFFECTIVE_PERMISSIONS = {
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

function authenticatedOidcState(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    status: 'authenticated' as const,
    user: { access_token: 'tok-1', expired: false },
    error: null,
    signIn: vi.fn(),
    signOutLocally: vi.fn().mockResolvedValue(undefined),
    getAccessTokenLive: () => 'tok-1',
    ...overrides,
  };
}

const ORG_MEMBERSHIPS = {
  memberships: [{ organization_id: 'org-1', organization_name: 'Org One', role: 'ORG_ADMIN' }],
  is_platform_admin: false,
};

/** Manually-controlled promise — lets a test drive the exact
 * loading -> settled transition instead of racing a `waitFor` against
 * whichever microtask order a `mockResolvedValue`/`mockRejectedValue`
 * happens to produce. Used below to prove there is exactly one
 * authoritative `/auth/me` call driving the UI's transition, not two
 * that could independently disagree. */
function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  // Silences Node's unhandled-rejection warning for the window between
  // this promise being created and the component under test actually
  // awaiting it -- a harmless artifact of manually deferring resolution
  // in a test, not a real unhandled rejection in production code (the
  // component's own `await Promise.all(...)` still independently
  // receives the same rejection through its own subscription).
  promise.catch(() => {});
  return { promise, resolve, reject };
}

describe('ProductionSessionGate', () => {
  afterEach(() => {
    // Explicit, not relying on @testing-library/react's auto-cleanup
    // registration order relative to this file's own afterEach: a
    // mounted tree left over from the previous test (several below
    // deliberately leave a promise pending forever) must be fully
    // unmounted before the next test's assertions run.
    cleanup();
    // resetAllMocks (not clearAllMocks): also clears mockReturnValue/
    // mockResolvedValue implementations between tests.
    vi.resetAllMocks();
  });

  it('shows a loading state while the OIDC session itself is still resolving', () => {
    mockUseOidcSession.mockReturnValue({
      status: 'loading',
      user: null,
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderGate();

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('Authenticated Workspace')).not.toBeInTheDocument();
  });

  it('redirects to /login when there is no OIDC session', async () => {
    mockUseOidcSession.mockReturnValue({
      status: 'unauthenticated',
      user: null,
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderGate();

    await waitFor(() => expect(screen.getByText('Login Page')).toBeInTheDocument());
  });

  it('shows a deterministic error state when the OIDC layer itself reports an error', async () => {
    mockUseOidcSession.mockReturnValue({
      status: 'error',
      user: null,
      error: new Error('storage unavailable'),
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderGate();

    expect(screen.getByRole('alert')).toHaveTextContent('storage unavailable');
    expect(screen.queryByText('Authenticated Workspace')).not.toBeInTheDocument();
  });

  it('renders the authenticated workspace once the session, organization, and permissions all resolve', async () => {
    mockUseOidcSession.mockReturnValue(authenticatedOidcState());
    vi.mocked(listAuthOrganizations).mockResolvedValue(ORG_MEMBERSHIPS);
    vi.mocked(getEffectivePermissions).mockResolvedValue(EFFECTIVE_PERMISSIONS);

    renderGate();

    await waitFor(() => expect(screen.getByText('Authenticated Workspace')).toBeInTheDocument());
    // Exactly one /auth/me call drives this render -- there is no
    // second, independent probe that could have disagreed with it.
    expect(getEffectivePermissions).toHaveBeenCalledTimes(1);
  });

  it('never renders the authenticated workspace before ProdAuthProvider itself reports isAuthenticated', async () => {
    mockUseOidcSession.mockReturnValue(authenticatedOidcState());
    vi.mocked(listAuthOrganizations).mockResolvedValue({
      memberships: [{ organization_id: 'org-1', organization_name: 'Org One', role: 'ORG_ADMIN' }],
      is_platform_admin: false,
    });
    // getEffectivePermissions (called by the inner ProdAuthProvider)
    // never resolves in this test -- the workspace must stay hidden
    // behind a loading state for as long as that's true.
    vi.mocked(getEffectivePermissions).mockReturnValue(new Promise(() => {}));

    renderGate();

    await waitFor(() => expect(screen.getAllByRole('status').length).toBeGreaterThan(0));
    expect(screen.queryByText('Authenticated Workspace')).not.toBeInTheDocument();
  });

  it('shows "organization setup required" for an authenticated user with zero organization memberships', async () => {
    mockUseOidcSession.mockReturnValue(authenticatedOidcState());
    vi.mocked(listAuthOrganizations).mockResolvedValue({ memberships: [], is_platform_admin: false });

    renderGate();

    await waitFor(() => expect(screen.getByText('Organization setup required')).toBeInTheDocument());
    expect(getEffectivePermissions).not.toHaveBeenCalled();
  });

  it('treats a 401 from /auth/organizations as session expiration: signs out locally and returns to /login', async () => {
    const signOutLocally = vi.fn().mockResolvedValue(undefined);
    mockUseOidcSession.mockReturnValue(authenticatedOidcState({ signOutLocally }));
    vi.mocked(listAuthOrganizations).mockRejectedValue(new ApiError('Unauthorized', { status: 401 }));

    renderGate();

    await waitFor(() => expect(screen.getByText('Login Page')).toBeInTheDocument());
    expect(signOutLocally).toHaveBeenCalledTimes(1);
  });

  it('shows a deterministic error state for a non-401 failure resolving organizations', async () => {
    mockUseOidcSession.mockReturnValue(authenticatedOidcState());
    vi.mocked(listAuthOrganizations).mockRejectedValue(new ApiError('Service unavailable', { status: 503 }));

    renderGate();

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Service unavailable'));
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument();
  });

  // --- Blocker 2 regressions: a /auth/me failure must never look like ---
  // --- "still loading" forever -----------------------------------------

  it('(C, D) a 401 from /auth/me signs out locally and redirects to /login, never leaving an indefinite loading state', async () => {
    const signOutLocally = vi.fn().mockResolvedValue(undefined);
    mockUseOidcSession.mockReturnValue(authenticatedOidcState({ signOutLocally }));
    vi.mocked(listAuthOrganizations).mockResolvedValue({
      memberships: [{ organization_id: 'org-1', organization_name: 'Org One', role: 'ORG_ADMIN' }],
      is_platform_admin: false,
    });
    // The organizations probe succeeded (token was valid a moment ago),
    // but /auth/me itself now 401s -- e.g. the token expired in the
    // narrow window between the two calls.
    vi.mocked(getEffectivePermissions).mockRejectedValue(new ApiError('Unauthorized', { status: 401 }));

    renderGate();

    await waitFor(() => expect(screen.getByText('Login Page')).toBeInTheDocument());
    expect(signOutLocally).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('(E) a 503 from /auth/me produces a deterministic error state, distinct from "still loading" and from the 401 case', async () => {
    const signOutLocally = vi.fn().mockResolvedValue(undefined);
    mockUseOidcSession.mockReturnValue(authenticatedOidcState({ signOutLocally }));
    vi.mocked(listAuthOrganizations).mockResolvedValue({
      memberships: [{ organization_id: 'org-1', organization_name: 'Org One', role: 'ORG_ADMIN' }],
      is_platform_admin: false,
    });
    vi.mocked(getEffectivePermissions).mockRejectedValue(new ApiError('Service unavailable', { status: 503 }));

    renderGate();

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not load your workspace'));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument();
    // A non-auth failure must not be treated as a session expiration.
    expect(signOutLocally).not.toHaveBeenCalled();
  });

  // --- Blocker 1 regression: logout must actually clear the registered ---
  // --- token, not merely the UI's own belief about auth state -----------

  it('(F) signing out clears the registered token getter, not only the rendered auth state', async () => {
    const { getAccessToken } = await import('./authToken');
    mockUseOidcSession.mockReturnValue(authenticatedOidcState());
    vi.mocked(listAuthOrganizations).mockResolvedValue({
      memberships: [{ organization_id: 'org-1', organization_name: 'Org One', role: 'ORG_ADMIN' }],
      is_platform_admin: false,
    });
    vi.mocked(getEffectivePermissions).mockResolvedValue(EFFECTIVE_PERMISSIONS);

    const { rerender } = renderGate();
    await waitFor(() => expect(screen.getByText('Authenticated Workspace')).toBeInTheDocument());
    expect(getAccessToken()).toBe('tok-1');

    // Simulate what the OIDC hook reports once signOutLocally() has
    // actually fired its userUnloaded event -- the exact transition
    // Header.tsx's "Sign out" button triggers in the real app.
    mockUseOidcSession.mockReturnValue({
      status: 'unauthenticated',
      user: null,
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });
    rerender(
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

    await waitFor(() => expect(getAccessToken()).toBeNull());
  });

  // --- Blocker 2 hardening: ProdAuthProvider's own /auth/me call is the ---
  // --- single authoritative source -- no second, independent probe that --
  // --- could race against and disagree with it ----------------------------

  it('race-proof scenario 1: loading -> resolved renders the workspace exactly once the one authoritative call settles', async () => {
    const deferred = createDeferred<typeof EFFECTIVE_PERMISSIONS>();
    mockUseOidcSession.mockReturnValue(authenticatedOidcState());
    vi.mocked(listAuthOrganizations).mockResolvedValue(ORG_MEMBERSHIPS);
    vi.mocked(getEffectivePermissions).mockReturnValue(deferred.promise);

    renderGate();
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument());
    expect(screen.queryByText('Authenticated Workspace')).not.toBeInTheDocument();

    deferred.resolve(EFFECTIVE_PERMISSIONS);

    await waitFor(() => expect(screen.getByText('Authenticated Workspace')).toBeInTheDocument());
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(getEffectivePermissions).toHaveBeenCalledTimes(1);
  });

  it('race-proof scenario 2: loading -> 401 signs out and reaches /login, driven by the one authoritative call alone', async () => {
    const deferred = createDeferred<never>();
    const signOutLocally = vi.fn().mockResolvedValue(undefined);
    mockUseOidcSession.mockReturnValue(authenticatedOidcState({ signOutLocally }));
    vi.mocked(listAuthOrganizations).mockResolvedValue(ORG_MEMBERSHIPS);
    vi.mocked(getEffectivePermissions).mockReturnValue(deferred.promise);

    renderGate();
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument());

    deferred.reject(new ApiError('Unauthorized', { status: 401 }));

    await waitFor(() => expect(screen.getByText('Login Page')).toBeInTheDocument());
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(signOutLocally).toHaveBeenCalledTimes(1);
    expect(getEffectivePermissions).toHaveBeenCalledTimes(1);
  });

  it('race-proof scenario 3: loading -> 503 shows a deterministic error and never signs out, driven by the one authoritative call alone', async () => {
    const deferred = createDeferred<never>();
    const signOutLocally = vi.fn().mockResolvedValue(undefined);
    mockUseOidcSession.mockReturnValue(authenticatedOidcState({ signOutLocally }));
    vi.mocked(listAuthOrganizations).mockResolvedValue(ORG_MEMBERSHIPS);
    vi.mocked(getEffectivePermissions).mockReturnValue(deferred.promise);

    renderGate();
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument());

    deferred.reject(new ApiError('Service unavailable', { status: 503 }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not load your workspace'));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument();
    expect(signOutLocally).not.toHaveBeenCalled();
    expect(getEffectivePermissions).toHaveBeenCalledTimes(1);
  });
});
