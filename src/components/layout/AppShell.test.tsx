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
            <Route path="intelligence" element={<h1>Intelligence content</h1>} />
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

  it('renders Knowledge, Reports, and Administration as real navigable links, not "Coming later" placeholders', () => {
    renderShell();
    expect(screen.getByRole('link', { name: 'Knowledge' })).toHaveAttribute('href', '/knowledge');
    expect(screen.getByRole('link', { name: 'Reports' })).toHaveAttribute('href', '/reports');
    expect(screen.getByRole('link', { name: 'Administration' })).toHaveAttribute('href', '/administration');
    expect(screen.queryByText('Coming later')).not.toBeInTheDocument();
  });

  it('gives the active Intelligence link the teal intelligence accent (SIE Milestone UI-DESIGN-01)', () => {
    renderShell('/intelligence');
    expect(screen.getByRole('link', { name: 'Intelligence' }).className).toMatch(/bg-teal-50/);
    expect(screen.getByRole('link', { name: 'Intelligence' }).className).not.toMatch(/bg-navy-50/);
  });

  it('gives other active links (e.g. Events) the navy structural accent, not teal — teal stays reserved for Intelligence (SIE Milestone UI-DESIGN-01)', () => {
    renderShell('/events');
    expect(screen.getByRole('link', { name: 'Events' }).className).toMatch(/bg-navy-50/);
    expect(screen.getByRole('link', { name: 'Events' }).className).not.toMatch(/bg-teal-50/);
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
