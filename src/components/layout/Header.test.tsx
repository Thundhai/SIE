import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AuthContext } from '../../auth/AuthContext';
import type { AuthContextValue } from '../../auth/types';
import { Header } from './Header';

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
      <Header />
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
