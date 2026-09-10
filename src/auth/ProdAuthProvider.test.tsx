import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from './AuthContext';
import { ProdAuthProvider } from './ProdAuthProvider';
import { getAccessToken } from './authToken';

vi.mock('../services/api/auth', () => ({
  getEffectivePermissions: vi.fn(),
  listAuthOrganizations: vi.fn(),
}));

import { getEffectivePermissions, listAuthOrganizations } from '../services/api/auth';
import { setAccessTokenGetter } from './authToken';

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <p>authenticated: {String(auth.isAuthenticated)}</p>
      <p>isDevIdentity: {String(auth.isDevIdentity)}</p>
      <p>org: {auth.organization?.name ?? 'none'}</p>
      <p>role: {auth.memberships[0]?.role ?? 'none'}</p>
      <p>membershipCount: {auth.memberships.length}</p>
      <p>hasSafetyDataRead: {String(auth.hasPermission('safety_data:read'))}</p>
    </div>
  );
}

const EFFECTIVE_PERMISSIONS = {
  user_id: 'user-1',
  name: 'Production User',
  email: 'prod.user@example.com',
  organization_id: 'org-1',
  organization_name: 'Real Org',
  role: 'ORG_ADMIN',
  permissions: ['safety_data:read'],
  is_platform_admin: false,
  auth_mode: 'production',
  identity_provider: 'test-idp',
};

const ORGANIZATIONS = {
  memberships: [{ organization_id: 'org-1', organization_name: 'Real Org', role: 'ORG_ADMIN' }],
  is_platform_admin: false,
};

describe('ProdAuthProvider', () => {
  afterEach(() => {
    vi.clearAllMocks();
    // Belt-and-braces reset of the shared module-level registration
    // between tests (component-unmount cleanup is covered by its own
    // dedicated test below) so an un-unmounted provider from one test
    // never leaks its token getter into the next.
    setAccessTokenGetter(null);
  });

  it('is not authenticated with no access token — never fabricates a user/org', async () => {
    render(
      <ProdAuthProvider getAccessToken={() => null} organizationId={null}>
        <Probe />
      </ProdAuthProvider>,
    );
    expect(await screen.findByText('authenticated: false')).toBeInTheDocument();
    expect(screen.getByText('isDevIdentity: false')).toBeInTheDocument();
    expect(getEffectivePermissions).not.toHaveBeenCalled();
  });

  it('is not authenticated with a token but no organization selected yet', async () => {
    render(
      <ProdAuthProvider getAccessToken={() => 'a-real-token'} organizationId={null}>
        <Probe />
      </ProdAuthProvider>,
    );
    expect(await screen.findByText('authenticated: false')).toBeInTheDocument();
    expect(getEffectivePermissions).not.toHaveBeenCalled();
  });

  it('resolves a real identity once a token and organization are both present', async () => {
    vi.mocked(getEffectivePermissions).mockResolvedValue(EFFECTIVE_PERMISSIONS);
    vi.mocked(listAuthOrganizations).mockResolvedValue(ORGANIZATIONS);

    render(
      <ProdAuthProvider getAccessToken={() => 'a-real-token'} organizationId="org-1">
        <Probe />
      </ProdAuthProvider>,
    );

    await waitFor(() => expect(screen.getByText('authenticated: true')).toBeInTheDocument());
    expect(screen.getByText('org: Real Org')).toBeInTheDocument();
    expect(screen.getByText('role: ORG_ADMIN')).toBeInTheDocument();
    expect(screen.getByText('membershipCount: 1')).toBeInTheDocument();
    expect(screen.getByText('hasSafetyDataRead: true')).toBeInTheDocument();
  });

  it('falls back to a clean not-authenticated state on a 401/unauthenticated API response', async () => {
    vi.mocked(getEffectivePermissions).mockRejectedValue(new Error('Unauthorized'));
    vi.mocked(listAuthOrganizations).mockResolvedValue(ORGANIZATIONS);

    render(
      <ProdAuthProvider getAccessToken={() => 'an-expired-token'} organizationId="org-1">
        <Probe />
      </ProdAuthProvider>,
    );

    await waitFor(() => expect(screen.getByText('authenticated: false')).toBeInTheDocument());
  });

  it('registers its token getter with the shared API client while mounted', async () => {
    vi.mocked(getEffectivePermissions).mockResolvedValue(EFFECTIVE_PERMISSIONS);
    vi.mocked(listAuthOrganizations).mockResolvedValue(ORGANIZATIONS);

    const { unmount } = render(
      <ProdAuthProvider getAccessToken={() => 'a-real-token'} organizationId="org-1">
        <Probe />
      </ProdAuthProvider>,
    );

    await waitFor(() => expect(getAccessToken()).toBe('a-real-token'));
    unmount();
    expect(getAccessToken()).toBeNull();
  });
});
