import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthContext } from '../auth/AuthContext';
import type { AuthContextValue } from '../auth/types';
import { AppRoutes } from './router';

const UNAUTHENTICATED_VALUE: AuthContextValue = {
  isAuthenticated: false,
  isDevIdentity: true,
  user: null,
  organization: null,
  memberships: [],
  permissions: [],
  hasPermission: () => false,
};

function renderAt(path: string) {
  return render(
    <AuthContext.Provider value={UNAUTHENTICATED_VALUE}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('AppRoutes', () => {
  it('renders Home at /', () => {
    renderAt('/');
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  });

  it('renders Events at /events', () => {
    renderAt('/events');
    expect(screen.getByRole('heading', { name: 'Events' })).toBeInTheDocument();
  });

  it('renders Event Detail for a known fixture id at /events/:eventId', async () => {
    renderAt('/events/EVT-1001');
    await waitFor(() => expect(screen.getByRole('heading', { name: /Vehicle incident/ })).toBeInTheDocument());
  });

  it('redirects an unknown path back to Home (URL-based routing, not a 404 page)', () => {
    renderAt('/this-route-does-not-exist');
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  });

  it('does not route Intelligence/Knowledge/Reports/Administration to a fake page (§22) — falls back to Home', () => {
    renderAt('/intelligence');
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  });

  it('renders Actions at /actions (SIE Milestone 18)', async () => {
    renderAt('/actions');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Actions' })).toBeInTheDocument());
  });

  it('renders Action Detail for a known fixture id at /actions/:actionId', async () => {
    renderAt('/actions/ACT-2001');
    await waitFor(() => expect(screen.getByRole('heading', { name: /Review reversing procedure/ })).toBeInTheDocument());
  });
});
