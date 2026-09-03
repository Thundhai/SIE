import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from './AuthContext';
import { DevAuthProvider } from './DevAuthProvider';

vi.mock('../services/api/organizations', () => ({
  getOrganization: vi.fn(),
  getMembership: vi.fn(),
}));

import { getMembership, getOrganization } from '../services/api/organizations';

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <p>authenticated: {String(auth.isAuthenticated)}</p>
      <p>org: {auth.organization?.name ?? 'none'}</p>
      <p>role: {auth.memberships[0]?.role ?? 'none'}</p>
      <p>hasGovernanceManage: {String(auth.hasPermission('governance:manage'))}</p>
    </div>
  );
}

describe('DevAuthProvider', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it('is not authenticated when no dev identity is configured — never fabricates a user/org', async () => {
    render(
      <DevAuthProvider>
        <Probe />
      </DevAuthProvider>,
    );
    expect(await screen.findByText('authenticated: false')).toBeInTheDocument();
    expect(screen.getByText('org: none')).toBeInTheDocument();
    expect(getOrganization).not.toHaveBeenCalled();
  });

  it('resolves a configured dev identity against the real organizations/memberships service', async () => {
    vi.stubEnv('VITE_DEV_USER_ID', 'user-1');
    vi.stubEnv('VITE_DEV_ORGANIZATION_ID', 'org-1');
    vi.mocked(getOrganization).mockResolvedValue({ id: 'org-1', name: 'SIE Test Org', industry: null, country: null, status: 'active' });
    vi.mocked(getMembership).mockResolvedValue({ id: 'm1', user_id: 'user-1', organization_id: 'org-1', role: 'ORG_ADMIN', status: 'ACTIVE' });

    render(
      <DevAuthProvider>
        <Probe />
      </DevAuthProvider>,
    );

    await waitFor(() => expect(screen.getByText('authenticated: true')).toBeInTheDocument());
    expect(screen.getByText('org: SIE Test Org')).toBeInTheDocument();
    expect(screen.getByText('role: ORG_ADMIN')).toBeInTheDocument();
  });

  it('permission-sensitive UI: hasPermission() is always false (no backend endpoint resolves effective permissions — see this module\'s own docstring)', async () => {
    vi.stubEnv('VITE_DEV_USER_ID', 'user-1');
    vi.stubEnv('VITE_DEV_ORGANIZATION_ID', 'org-1');
    vi.mocked(getOrganization).mockResolvedValue({ id: 'org-1', name: 'SIE Test Org', industry: null, country: null, status: 'active' });
    vi.mocked(getMembership).mockResolvedValue({ id: 'm1', user_id: 'user-1', organization_id: 'org-1', role: 'ORG_ADMIN', status: 'ACTIVE' });

    render(
      <DevAuthProvider>
        <Probe />
      </DevAuthProvider>,
    );

    await waitFor(() => expect(screen.getByText('authenticated: true')).toBeInTheDocument());
    expect(screen.getByText('hasGovernanceManage: false')).toBeInTheDocument();
  });

  it('falls back to not-authenticated when the backend cannot resolve the configured identity', async () => {
    vi.stubEnv('VITE_DEV_USER_ID', 'user-1');
    vi.stubEnv('VITE_DEV_ORGANIZATION_ID', 'org-1');
    vi.mocked(getOrganization).mockRejectedValue(new Error('Not found'));
    vi.mocked(getMembership).mockRejectedValue(new Error('Not found'));

    render(
      <DevAuthProvider>
        <Probe />
      </DevAuthProvider>,
    );

    await waitFor(() => expect(screen.getByText('authenticated: false')).toBeInTheDocument());
  });
});
