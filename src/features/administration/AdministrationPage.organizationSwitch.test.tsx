import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, useAuth } from '../../auth/AuthContext';
import { OrganizationSwitchProvider, useOrganizationSwitch } from '../../auth/OrganizationSwitchProvider';
import type { AuthContextValue } from '../../auth/types';
import { AdministrationPage } from './AdministrationPage';

/**
 * SIE Milestone G3-3 — the task's own "Administration is particularly
 * sensitive to organization context" requirement: after a switch,
 * Organization/Sites/Members/Standards/API Clients must all correspond
 * to the NEW organization, and the previous organization's data must
 * never remain visible under the new organization's heading.
 */
vi.mock('../../services/api/organizations', () => ({
  getOrganization: vi.fn(),
}));
vi.mock('../../services/api/administration', () => ({
  listSites: vi.fn(),
  listMembers: vi.fn(),
  listActiveGoverningStandards: vi.fn(),
  listApiClients: vi.fn(),
}));
vi.mock('../../services/api/auth', () => ({
  getEffectivePermissions: vi.fn(),
  listAuthOrganizations: vi.fn(),
}));

import { getOrganization } from '../../services/api/organizations';
import { listSites } from '../../services/api/administration';
import { getEffectivePermissions } from '../../services/api/auth';

const ORG_A = { id: 'org-a', name: 'Org A Holdings', industry: 'energy', country: 'US', status: 'active' };
const ORG_B = { id: 'org-b', name: 'Org B Resources', industry: 'manufacturing', country: 'CA', status: 'active' };

const BASE: AuthContextValue = {
  isAuthenticated: true,
  isDevIdentity: false,
  user: { id: 'u1', name: 'Jordan Casey', email: 'jordan@example.com' },
  organization: { id: 'org-a', name: 'Org A Holdings' },
  memberships: [
    { organizationId: 'org-a', organizationName: 'Org A Holdings', role: 'ORG_ADMIN' },
    { organizationId: 'org-b', organizationName: 'Org B Resources', role: 'ORG_ADMIN' },
  ],
  permissions: ['organization:read', 'site:read'],
  hasPermission: (p) => ['organization:read', 'site:read'].includes(p),
};

function SwitchButton() {
  const { switchOrganization } = useOrganizationSwitch();
  return <button onClick={() => void switchOrganization('org-b')}>Switch to Org B</button>;
}

function renderHarness() {
  return render(
    <AuthContext.Provider value={BASE}>
      <OrganizationSwitchProvider>
        <SwitchButton />
        <AdministrationPage />
      </OrganizationSwitchProvider>
    </AuthContext.Provider>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe('AdministrationPage across an organization switch', () => {
  it('shows Org A data before any switch', async () => {
    vi.mocked(getOrganization).mockImplementation((id: string) => Promise.resolve(id === 'org-a' ? ORG_A : ORG_B));
    vi.mocked(listSites).mockResolvedValue([]);

    renderHarness();

    await waitFor(() => expect(screen.getByText('Org A Holdings')).toBeInTheDocument());
    expect(getOrganization).toHaveBeenCalledWith('org-a', expect.anything());
  });

  it('after switching to Org B, Organization and Sites both correspond to Org B -- Org A data never remains', async () => {
    const userEvent = (await import('@testing-library/user-event')).default;
    vi.mocked(getOrganization).mockImplementation((id: string) => Promise.resolve(id === 'org-a' ? ORG_A : ORG_B));
    vi.mocked(listSites).mockImplementation((id: string) =>
      Promise.resolve(
        id === 'org-a'
          ? [{ id: 's1', organization_id: 'org-a', name: 'Org A Site', location: null, country: null, status: 'active', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }]
          : [{ id: 's2', organization_id: 'org-b', name: 'Org B Site', location: null, country: null, status: 'active', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }],
      ),
    );
    vi.mocked(getEffectivePermissions).mockResolvedValue({
      user_id: 'u1',
      name: 'Jordan Casey',
      email: 'jordan@example.com',
      organization_id: 'org-b',
      organization_name: 'Org B Resources',
      role: 'ORG_ADMIN',
      permissions: ['organization:read', 'site:read'],
      is_platform_admin: false,
      auth_mode: 'production',
      identity_provider: 'test-idp',
    });

    renderHarness();
    await waitFor(() => expect(screen.getByText('Org A Holdings')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Org A Site')).toBeInTheDocument());

    await userEvent.click(screen.getByText('Switch to Org B'));

    await waitFor(() => expect(screen.getByText('Org B Resources')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Org B Site')).toBeInTheDocument());

    // The defining assertion: Org A's data is gone, not merely that
    // Org B's data is present alongside it.
    expect(screen.queryByText('Org A Holdings')).not.toBeInTheDocument();
    expect(screen.queryByText('Org A Site')).not.toBeInTheDocument();
    expect(getOrganization).toHaveBeenLastCalledWith('org-b', expect.anything());
    expect(listSites).toHaveBeenLastCalledWith('org-b', expect.anything());
  });

  it('a route-level permission lost in Org B hides a previously-visible section rather than showing stale Org A data for it', async () => {
    const userEvent = (await import('@testing-library/user-event')).default;
    vi.mocked(getOrganization).mockImplementation((id: string) => Promise.resolve(id === 'org-a' ? ORG_A : ORG_B));
    vi.mocked(listSites).mockResolvedValue([
      { id: 's1', organization_id: 'org-a', name: 'Org A Site', location: null, country: null, status: 'active', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
    ]);
    // Org B's real, backend-authoritative permission set does NOT
    // include site:read -- the Sites section must disappear, never show
    // Org A's already-fetched site list under Org B's heading.
    vi.mocked(getEffectivePermissions).mockResolvedValue({
      user_id: 'u1',
      name: 'Jordan Casey',
      email: 'jordan@example.com',
      organization_id: 'org-b',
      organization_name: 'Org B Resources',
      role: 'VIEWER',
      permissions: ['organization:read'],
      is_platform_admin: false,
      auth_mode: 'production',
      identity_provider: 'test-idp',
    });

    renderHarness();
    await waitFor(() => expect(screen.getByText('Org A Site')).toBeInTheDocument());

    await userEvent.click(screen.getByText('Switch to Org B'));

    await waitFor(() => expect(screen.getByText('Org B Resources')).toBeInTheDocument());
    expect(screen.queryByText('Org A Site')).not.toBeInTheDocument();
    expect(screen.queryByText('Sites')).not.toBeInTheDocument();
  });
});
