import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthContext } from './AuthContext';
import type { AuthContextValue } from './types';
import { PermissionRoute } from './PermissionRoute';

function renderWithPermissions(permissions: string[]) {
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
      <MemoryRouter>
        <PermissionRoute permission="intelligence:read">
          <div>Protected content</div>
        </PermissionRoute>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('PermissionRoute', () => {
  it('renders its children when the user has the required permission', () => {
    renderWithPermissions(['intelligence:read']);
    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });

  it('renders Access Denied, never the children, when the permission is missing', () => {
    renderWithPermissions(['safety_data:read']);
    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('denies a user with zero permissions at all', () => {
    renderWithPermissions([]);
    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  });

  it('never names the specific missing permission in the denied UI', () => {
    renderWithPermissions([]);
    expect(screen.queryByText(/intelligence:read/)).not.toBeInTheDocument();
  });
});
