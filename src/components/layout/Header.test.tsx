import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../../auth/AuthContext';
import { OrganizationSwitchProvider } from '../../auth/OrganizationSwitchProvider';
import type { AuthContextValue } from '../../auth/types';
import { Header } from './Header';

const mockGetEffectivePermissions = vi.fn();
vi.mock('../../services/api/auth', () => ({
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
  organization: { id: 'org1', name: 'Acme Energy' },
  memberships: [{ organizationId: 'org1', organizationName: 'Acme Energy', role: 'ORG_ADMIN' }],
  permissions: [],
  hasPermission: () => true,
};

function renderHeader(value: AuthContextValue) {
  return render(
    <AuthContext.Provider value={value}>
      <OrganizationSwitchProvider>
        <Header />
      </OrganizationSwitchProvider>
    </AuthContext.Provider>,
  );
}

/**
 * SIE Milestone UI-DEV-01, item 10 (frontend): "development labeling is
 * visible where appropriate" — a restrained pill, never a loud banner
 * (§5's own "no loud banners or robotic/AI styling" instruction), shown
 * only when the resolved identity actually came from the development
 * mechanism (`isDevIdentity`), never for a real authenticated session.
 */
describe('Header — development identity labeling', () => {
  it('shows a restrained "Development identity" label when authenticated via the dev identity mechanism', () => {
    renderHeader({ ...BASE, isDevIdentity: true });
    expect(screen.getByText('Development identity')).toBeInTheDocument();
  });

  it('never shows the development label for a real (non-dev) authenticated session', () => {
    renderHeader({ ...BASE, isDevIdentity: false });
    expect(screen.queryByText('Development identity')).not.toBeInTheDocument();
  });

  it('never shows the development label when not authenticated at all', () => {
    renderHeader({ ...BASE, isAuthenticated: false, isDevIdentity: true, user: null, organization: null, memberships: [] });
    expect(screen.queryByText('Development identity')).not.toBeInTheDocument();
  });

  it('reads organization/user identity from AuthContext, never hardcoded', () => {
    renderHeader({ ...BASE, isDevIdentity: true });
    expect(screen.getByText('Acme Energy')).toBeInTheDocument();
    expect(screen.getByText('Jordan Casey')).toBeInTheDocument();
  });

  it('shows an honest "no organization" state rather than fabricating one', () => {
    renderHeader({ ...BASE, isAuthenticated: false, isDevIdentity: false, user: null, organization: null, memberships: [] });
    expect(screen.getByText('No organization context')).toBeInTheDocument();
    expect(screen.getByText('Not signed in')).toBeInTheDocument();
  });
});

const MULTI_ORG: AuthContextValue = {
  ...BASE,
  memberships: [
    { organizationId: 'org1', organizationName: 'Acme Energy', role: 'ORG_ADMIN' },
    { organizationId: 'org2', organizationName: 'Beta Resources', role: 'VIEWER' },
  ],
};

/**
 * SIE Milestone G3-3 — the organization switcher itself.
 */
describe('Header — organization switcher', () => {
  it('a single-organization identity shows the plain organization name, with no switch control at all', () => {
    renderHeader(BASE);
    expect(screen.getByText('Acme Energy')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('a multi-organization identity shows an accessible control (a native select) listing every authorized organization', () => {
    renderHeader(MULTI_ORG);
    const select = screen.getByRole('combobox', { name: 'Organization' });
    expect(select).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Acme Energy' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Beta Resources' })).toBeInTheDocument();
  });

  it('the current organization is visibly selected in the control', () => {
    renderHeader(MULTI_ORG);
    const select = screen.getByRole('combobox', { name: 'Organization' }) as HTMLSelectElement;
    expect(select.value).toBe('org1');
  });

  it('never shows a raw organization UUID as the primary label -- only the organization name', () => {
    const uuidShaped: AuthContextValue = {
      ...MULTI_ORG,
      organization: { id: '11111111-1111-4111-8111-111111111111', name: 'Acme Energy' },
      memberships: [
        { organizationId: '11111111-1111-4111-8111-111111111111', organizationName: 'Acme Energy', role: 'ORG_ADMIN' },
        { organizationId: '22222222-2222-4222-8222-222222222222', organizationName: 'Beta Resources', role: 'VIEWER' },
      ],
    };
    renderHeader(uuidShaped);
    expect(screen.queryByText(/11111111-1111/)).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Acme Energy' })).toBeInTheDocument();
  });

  it('selecting a different organization in the control triggers a real switch, via the keyboard-accessible native select', async () => {
    mockGetEffectivePermissions.mockResolvedValue({
      user_id: 'u1',
      name: 'Jordan Casey',
      email: 'jordan@example.com',
      organization_id: 'org2',
      organization_name: 'Beta Resources',
      role: 'VIEWER',
      permissions: [],
      is_platform_admin: false,
      auth_mode: 'production',
      identity_provider: 'test-idp',
    });
    renderHeader(MULTI_ORG);

    const select = screen.getByRole('combobox', { name: 'Organization' });
    await userEvent.selectOptions(select, 'org2');

    await waitFor(() => expect(mockGetEffectivePermissions).toHaveBeenCalledWith('org2', expect.anything()));
  });

  it('disables the control while a switch is in flight, preventing a second rapid change', async () => {
    let resolveSwitch!: (value: unknown) => void;
    mockGetEffectivePermissions.mockReturnValue(new Promise((resolve) => (resolveSwitch = resolve)));
    renderHeader(MULTI_ORG);

    const select = screen.getByRole('combobox', { name: 'Organization' }) as HTMLSelectElement;
    await userEvent.selectOptions(select, 'org2');

    await waitFor(() => expect(select).toBeDisabled());
    expect(screen.getByText('Switching…')).toBeInTheDocument();

    resolveSwitch({
      user_id: 'u1',
      name: 'Jordan Casey',
      email: 'jordan@example.com',
      organization_id: 'org2',
      organization_name: 'Beta Resources',
      role: 'VIEWER',
      permissions: [],
      is_platform_admin: false,
      auth_mode: 'production',
      identity_provider: 'test-idp',
    });
    await waitFor(() => expect(select).not.toBeDisabled());
  });
});
