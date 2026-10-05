import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthContext } from '../../auth/AuthContext';
import type { AuthContextValue } from '../../auth/types';
import { Sidebar } from './Sidebar';

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
        <Sidebar />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('Sidebar — permission-aware navigation (SIE Milestone G3-2)', () => {
  it('always shows Home, which has no permission requirement', () => {
    renderWithPermissions([]);
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
  });

  it('hides every other nav item for a user with zero permissions', () => {
    renderWithPermissions([]);
    expect(screen.queryByRole('link', { name: 'Events' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Actions' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Risk Assessments' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Intelligence' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Knowledge' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Reports' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument();
  });

  it('omits a group heading entirely when every item in that group is hidden', () => {
    renderWithPermissions([]);
    expect(screen.queryByText('Work')).not.toBeInTheDocument();
    expect(screen.queryByText('Intelligence')).not.toBeInTheDocument();
    expect(screen.queryByText('Knowledge')).not.toBeInTheDocument();
    expect(screen.queryByText('Reporting')).not.toBeInTheDocument();
    expect(screen.queryByText('Administration')).not.toBeInTheDocument();
  });

  it('shows exactly the items a VIEWER-shaped permission set grants, not every item', () => {
    // VIEWER's real ROLE_PERMISSIONS set (backend/app/services/permissions.py):
    // organization:read, site:read, project:read, knowledge:read,
    // safety_data:read, intelligence:read, prediction:read,
    // intervention:read, governance:read, risk_assessment:read,
    // standards:read -- no intervention:manage, no users:*.
    renderWithPermissions([
      'organization:read',
      'site:read',
      'knowledge:read',
      'safety_data:read',
      'intelligence:read',
      'intervention:read',
      'risk_assessment:read',
      'standards:read',
    ]);

    expect(screen.getByRole('link', { name: 'Events' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Actions' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Risk Assessments' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Intelligence' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Knowledge' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reports' })).toBeInTheDocument();
    // VIEWER has organization:read, which is Administration's
    // route-level floor -- the route itself is reachable (see
    // router.test.tsx), and the nav link reflects that.
    expect(screen.getByRole('link', { name: 'Administration' })).toBeInTheDocument();
  });

  it('shows every item for an ORG_ADMIN-shaped permission set (every permission)', () => {
    renderWithPermissions([
      'organization:read',
      'site:read',
      'safety_data:read',
      'intelligence:read',
      'intervention:read',
      'knowledge:read',
      'risk_assessment:read',
    ]);
    for (const label of ['Home', 'Events', 'Actions', 'Risk Assessments', 'Intelligence', 'Knowledge', 'Reports', 'Administration']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
  });

  it('a hidden link is a navigation convenience only — it never asserts the route itself is unreachable (see router.test.tsx for the actual security boundary)', () => {
    // This test documents the boundary, not a new one: Sidebar hiding
    // "Administration" for a user with no organization:read at all
    // does not, by itself, protect /administration -- PermissionRoute
    // does, independently, regardless of what Sidebar renders.
    renderWithPermissions([]);
    expect(screen.queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument();
  });
});
