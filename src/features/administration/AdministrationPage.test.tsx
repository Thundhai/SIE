import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../../auth/AuthContext';
import type { AuthContextValue } from '../../auth/types';
import { AdministrationPage } from './AdministrationPage';

vi.mock('../../services/api/organizations', () => ({
  getOrganization: vi.fn(),
}));
vi.mock('../../services/api/administration', () => ({
  listSites: vi.fn(),
  listMembers: vi.fn(),
  listActiveGoverningStandards: vi.fn(),
  listApiClients: vi.fn(),
}));

import { getOrganization } from '../../services/api/organizations';
import { listActiveGoverningStandards, listApiClients, listMembers, listSites } from '../../services/api/administration';

const ORGANIZATION = { id: 'org-1', name: 'Test Org', industry: 'manufacturing', country: 'US', status: 'active' };

function renderWithAuth(permissions: string[]) {
  const value: AuthContextValue = {
    isAuthenticated: true,
    isDevIdentity: true,
    user: { id: 'u1', name: 'Test User', email: 'u@example.com' },
    organization: { id: 'org-1', name: 'Test Org' },
    memberships: [],
    permissions,
    hasPermission: (permission) => permissions.includes(permission),
  };
  return render(
    <AuthContext.Provider value={value}>
      <AdministrationPage />
    </AuthContext.Provider>,
  );
}

describe('AdministrationPage', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('shows the Organization section for any organization member, regardless of other permissions', async () => {
    vi.mocked(getOrganization).mockResolvedValue(ORGANIZATION);
    vi.mocked(listSites).mockRejectedValue(new Error('should not be called'));
    vi.mocked(listMembers).mockRejectedValue(new Error('should not be called'));
    vi.mocked(listActiveGoverningStandards).mockRejectedValue(new Error('should not be called'));
    vi.mocked(listApiClients).mockRejectedValue(new Error('should not be called'));

    renderWithAuth([]); // no admin-section permissions at all

    await waitFor(() => expect(screen.getByText('Test Org')).toBeInTheDocument());
    // None of the gated sections' own fetches ever fired.
    expect(listSites).not.toHaveBeenCalled();
    expect(listMembers).not.toHaveBeenCalled();
    expect(listActiveGoverningStandards).not.toHaveBeenCalled();
    expect(listApiClients).not.toHaveBeenCalled();
  });

  it('shows only the sections the signed-in account actually has permission for', async () => {
    vi.mocked(getOrganization).mockResolvedValue(ORGANIZATION);
    vi.mocked(listMembers).mockResolvedValue([{ id: 'm1', user_id: 'user-1', organization_id: 'org-1', role: 'VIEWER', status: 'ACTIVE' }]);

    // Has users:read (sees Members) but not site:read/standards:read/users:manage.
    renderWithAuth(['organization:read', 'users:read']);

    await waitFor(() => expect(screen.getByText('user-1')).toBeInTheDocument());
    expect(screen.queryByText('Sites')).not.toBeInTheDocument();
    expect(screen.queryByText('Governing standards')).not.toBeInTheDocument();
    expect(screen.queryByText('API clients')).not.toBeInTheDocument();
    expect(listSites).not.toHaveBeenCalled();
    expect(listActiveGoverningStandards).not.toHaveBeenCalled();
    expect(listApiClients).not.toHaveBeenCalled();
  });

  it('a failure in one section does not blank out a different, independently-successful section (the defect this milestone fixes)', async () => {
    vi.mocked(getOrganization).mockResolvedValue(ORGANIZATION);
    vi.mocked(listSites).mockRejectedValue(new Error('Service unavailable'));
    vi.mocked(listMembers).mockResolvedValue([{ id: 'm1', user_id: 'user-1', organization_id: 'org-1', role: 'VIEWER', status: 'ACTIVE' }]);
    vi.mocked(listActiveGoverningStandards).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(listApiClients).mockResolvedValue([]);

    renderWithAuth(['organization:read', 'site:read', 'users:read', 'standards:read', 'users:manage']);

    await waitFor(() => expect(screen.getByText('Service unavailable')).toBeInTheDocument());
    // Members (a different section) still rendered its real data,
    // unaffected by Sites' own failure.
    expect(screen.getByText('user-1')).toBeInTheDocument();
    expect(screen.getByText('No governing standards selected')).toBeInTheDocument();
    expect(screen.getByText('No API clients')).toBeInTheDocument();
  });

  it('shows API clients only with users:manage — not a separate "read" permission (matches the actual backend route)', async () => {
    vi.mocked(getOrganization).mockResolvedValue(ORGANIZATION);
    vi.mocked(listApiClients).mockResolvedValue([
      { id: 'c1', organization_id: 'org-1', name: 'Ingestion Bot', client_id: 'client-1', secret_prefix: 'sk_', scopes: ['safety_data:write'], status: 'ACTIVE', created_at: '2026-01-01T00:00:00Z', last_used_at: null, rotated_at: null, revoked_at: null, expires_at: null },
    ]);

    renderWithAuth(['organization:read', 'users:manage']);

    await waitFor(() => expect(screen.getByText('Ingestion Bot')).toBeInTheDocument());
  });

  it('every section eventually renders together when the account has every relevant permission', async () => {
    vi.mocked(getOrganization).mockResolvedValue(ORGANIZATION);
    vi.mocked(listSites).mockResolvedValue([{ id: 's1', organization_id: 'org-1', name: 'Main Plant', location: null, country: null, status: 'active', created_at: '', updated_at: '' }]);
    vi.mocked(listMembers).mockResolvedValue([]);
    vi.mocked(listActiveGoverningStandards).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(listApiClients).mockResolvedValue([]);

    renderWithAuth(['organization:read', 'site:read', 'users:read', 'standards:read', 'users:manage']);

    await waitFor(() => expect(screen.getByText('Main Plant')).toBeInTheDocument());
    expect(screen.getByText('Sites')).toBeInTheDocument();
    expect(screen.getByText('Users & membership')).toBeInTheDocument();
    expect(screen.getByText('Governing standards')).toBeInTheDocument();
    expect(screen.getByText('API clients')).toBeInTheDocument();
  });
});
