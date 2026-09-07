import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthContext } from '../../auth/AuthContext';
import type { AuthContextValue } from '../../auth/types';
import { AppShell } from './AppShell';

const AUTHENTICATED_VALUE: AuthContextValue = {
  isAuthenticated: true,
  isDevIdentity: true,
  user: { id: 'u1', name: 'Frontend Dev', email: 'dev@example.com' },
  organization: { id: 'org1', name: 'SIE Test Organization' },
  memberships: [{ organizationId: 'org1', organizationName: 'SIE Test Organization', role: 'ORG_ADMIN' }],
  permissions: [],
  hasPermission: () => false,
};

function renderShell(initialPath = '/') {
  return render(
    <AuthContext.Provider value={AUTHENTICATED_VALUE}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<h1>Home content</h1>} />
            <Route path="events" element={<h1>Events content</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('AppShell', () => {
  it('renders Home, Events, Actions, Risk Assessments, and Intelligence as real navigable links', () => {
    renderShell();
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Events' })).toHaveAttribute('href', '/events');
    expect(screen.getByRole('link', { name: 'Actions' })).toHaveAttribute('href', '/actions');
    expect(screen.getByRole('link', { name: 'Risk Assessments' })).toHaveAttribute('href', '/risk-assessments');
    expect(screen.getByRole('link', { name: 'Intelligence' })).toHaveAttribute('href', '/intelligence');
  });

  it('renders Knowledge/Reports/Administration as disabled, non-navigating items (§9/§22) — SIE Milestone UI-01 promotes Intelligence and Risk Assessments to real routes', () => {
    renderShell();
    for (const label of ['Knowledge', 'Reports', 'Administration']) {
      // Not a link/button — no navigation target exists for it this milestone.
      expect(screen.queryByRole('link', { name: label })).not.toBeInTheDocument();
      // Some group headings share their single item's label verbatim (e.g.
      // "Knowledge"/"Administration" — the approved nav structure), so the
      // item row itself (a <span>, not the group's <p> heading) is what's
      // asserted here.
      expect(screen.getByText(label, { selector: 'span' })).toBeInTheDocument();
    }
    expect(screen.getAllByText('Coming later')).toHaveLength(3);
  });

  it('navigating from Home to Events swaps the routed content without a full page reload', async () => {
    renderShell();
    expect(screen.getByText('Home content')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Events' }));
    expect(screen.getByText('Events content')).toBeInTheDocument();
  });

  it('reads organization/user identity from AuthContext, never hardcoded', () => {
    renderShell();
    expect(screen.getByText('SIE Test Organization')).toBeInTheDocument();
    expect(screen.getByText('Frontend Dev')).toBeInTheDocument();
  });
});
