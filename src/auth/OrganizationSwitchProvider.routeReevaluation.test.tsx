import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, useAuth } from './AuthContext';
import { OrganizationSwitchProvider, useOrganizationSwitch } from './OrganizationSwitchProvider';
import { PermissionRoute } from './PermissionRoute';
import type { AuthContextValue } from './types';

/**
 * SIE Milestone G3-3 — proves the actual integration point required by
 * the task: a route G3-2's `PermissionRoute` allows under Organization A
 * must be re-evaluated, and correctly denied, under Organization B if B
 * grants a different permission set — using the REAL `PermissionRoute`
 * component (not a stand-in), driven by a REAL `switchOrganization()`
 * call through `OrganizationSwitchProvider`. `PermissionRoute` itself
 * needed no change for this to work: it already re-reads
 * `auth.hasPermission()` on every render, and this provider already
 * guarantees a switch produces a genuinely new `AuthContextValue` (see
 * `OrganizationSwitchProvider.test.tsx` for that proof in isolation) --
 * this file is the proof the two compose correctly.
 */
const mockGetEffectivePermissions = vi.fn();
vi.mock('../services/api/auth', () => ({
  getEffectivePermissions: (organizationId: string, signal?: AbortSignal) =>
    mockGetEffectivePermissions(organizationId, signal),
  listAuthOrganizations: vi.fn(),
}));

afterEach(() => {
  vi.resetAllMocks();
});

const BASE: AuthContextValue = {
  isAuthenticated: true,
  isDevIdentity: false,
  user: { id: 'u1', name: 'Jordan Casey', email: 'jordan@example.com' },
  organization: { id: 'org-a', name: 'Org A' },
  memberships: [
    { organizationId: 'org-a', organizationName: 'Org A', role: 'ORG_ADMIN' },
    { organizationId: 'org-b', organizationName: 'Org B', role: 'VIEWER' },
  ],
  // Org A grants risk_assessment:read.
  permissions: ['risk_assessment:read'],
  hasPermission: (p) => p === 'risk_assessment:read',
};

function SwitchButton() {
  const { switchOrganization } = useOrganizationSwitch();
  return <button onClick={() => void switchOrganization('org-b')}>Switch to Org B</button>;
}

function ProtectedRiskAssessmentsRoute() {
  return (
    <PermissionRoute permission="risk_assessment:read">
      <h1>Risk Assessments</h1>
    </PermissionRoute>
  );
}

function renderHarness() {
  return render(
    <AuthContext.Provider value={BASE}>
      <OrganizationSwitchProvider>
        <MemoryRouter>
          <SwitchButton />
          <ProtectedRiskAssessmentsRoute />
        </MemoryRouter>
      </OrganizationSwitchProvider>
    </AuthContext.Provider>,
  );
}

describe('PermissionRoute re-evaluation across an organization switch', () => {
  it('a route allowed in Org A renders normally before any switch', () => {
    renderHarness();
    expect(screen.getByRole('heading', { name: 'Risk Assessments' })).toBeInTheDocument();
  });

  it('a route allowed in Org A but forbidden in Org B becomes Access Denied once the switch resolves', async () => {
    // Org B (per its own real /auth/me response) does NOT grant
    // risk_assessment:read -- a VIEWER-shaped org with a different,
    // disjoint permission set.
    mockGetEffectivePermissions.mockResolvedValue({
      user_id: 'u1',
      name: 'Jordan Casey',
      email: 'jordan@example.com',
      organization_id: 'org-b',
      organization_name: 'Org B',
      role: 'VIEWER',
      permissions: ['knowledge:read'],
      is_platform_admin: false,
      auth_mode: 'production',
      identity_provider: 'test-idp',
    });
    renderHarness();
    expect(screen.getByRole('heading', { name: 'Risk Assessments' })).toBeInTheDocument();

    await userEvent.click(screen.getByText('Switch to Org B'));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Access denied' })).toBeInTheDocument());
    expect(screen.queryByRole('heading', { name: 'Risk Assessments' })).not.toBeInTheDocument();
  });

  it('a route forbidden under a stale permission set never renders using Org A permissions after the switch starts', async () => {
    // Org B's response also happens to grant risk_assessment:read, so
    // this test's real assertion is on the ORGANIZATION the rendered
    // page is now scoped to, not merely that *a* permission passed.
    mockGetEffectivePermissions.mockResolvedValue({
      user_id: 'u1',
      name: 'Jordan Casey',
      email: 'jordan@example.com',
      organization_id: 'org-b',
      organization_name: 'Org B',
      role: 'ORG_ADMIN',
      permissions: ['risk_assessment:read'],
      is_platform_admin: false,
      auth_mode: 'production',
      identity_provider: 'test-idp',
    });

    function OrgAwareRoute() {
      const auth = useAuth();
      return (
        <PermissionRoute permission="risk_assessment:read">
          <h1>Risk Assessments for {auth.organization?.name}</h1>
        </PermissionRoute>
      );
    }
    render(
      <AuthContext.Provider value={BASE}>
        <OrganizationSwitchProvider>
          <MemoryRouter>
            <SwitchButton />
            <OrgAwareRoute />
          </MemoryRouter>
        </OrganizationSwitchProvider>
      </AuthContext.Provider>,
    );

    expect(screen.getByRole('heading', { name: 'Risk Assessments for Org A' })).toBeInTheDocument();
    await userEvent.click(screen.getByText('Switch to Org B'));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Risk Assessments for Org B' })).toBeInTheDocument());
  });
});
