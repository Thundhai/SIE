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
    vi.mocked(listAuthOrganizations).mockResolvedValue({
      memberships: [{ organization_id: 'org-1', organization_name: 'Org One', role: 'ORG_ADMIN' }],
      is_platform_admin: false,
    });
    vi.mocked(getEffectivePermissions).mockResolvedValue(EFFECTIVE_PERMISSIONS);

    renderGate();

    await waitFor(() => expect(screen.getByText('Authenticated Workspace')).toBeInTheDocument());
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
});
