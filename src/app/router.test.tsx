import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppRoutes } from './router';

/**
 * Dev-mode routing (unchanged behavior) — `<AppRoutes/>` now manages its
 * own auth provider internally via `AuthGate` (SIE Milestone G3-1), so
 * these no longer need (or should use) an outer `AuthContext.Provider`
 * stub: under the test runner's default auth mode ("dev" — see
 * `authMode.ts`), `AuthGate` mounts `DevAuthProvider`, which resolves to
 * its own real not-authenticated default with no dev identity
 * configured — exactly the state these tests exercise.
 */
function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('AppRoutes (dev mode)', () => {
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

  it('renders Knowledge at /knowledge', () => {
    renderAt('/knowledge');
    expect(screen.getByRole('heading', { name: 'Knowledge' })).toBeInTheDocument();
  });

  it('renders Reports at /reports', () => {
    renderAt('/reports');
    expect(screen.getByRole('heading', { name: 'Reports' })).toBeInTheDocument();
  });

  it('renders Administration at /administration', () => {
    renderAt('/administration');
    expect(screen.getByRole('heading', { name: 'Administration' })).toBeInTheDocument();
  });

  it('renders Actions at /actions (SIE Milestone 18)', async () => {
    renderAt('/actions');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Actions' })).toBeInTheDocument());
  });

  it('renders Action Detail for a known fixture id at /actions/:actionId', async () => {
    renderAt('/actions/ACT-2001');
    await waitFor(() => expect(screen.getByRole('heading', { name: /Review reversing procedure/ })).toBeInTheDocument());
  });

  it('renders Intelligence at /intelligence (SIE Milestone UI-01)', () => {
    renderAt('/intelligence');
    expect(screen.getByRole('heading', { name: 'Intelligence' })).toBeInTheDocument();
  });

  it('renders Risk Assessments at /risk-assessments (SIE Milestone UI-01)', () => {
    renderAt('/risk-assessments');
    expect(screen.getByRole('heading', { name: 'Risk Assessments' })).toBeInTheDocument();
  });

  it('renders Risk Assessment Detail at /risk-assessments/:assessmentId (SIE Milestone UI-01)', () => {
    renderAt('/risk-assessments/RA-1001');
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument();
  });

  it('renders the Login page at /login without requiring any auth provider', () => {
    renderAt('/login');
    // Dev mode redirects /login straight back to "/" (see LoginPage's
    // own docstring: there is no login step in dev mode at all) --
    // Home is exactly the correct, intended behavior here.
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  });
});

/**
 * Production-mode routing (SIE Milestone G3-1) — the authentication
 * boundary itself. `AuthGate` dispatches to `ProductionSessionGate` once
 * `MODE === 'production'`; its own, deeper state machine (loading,
 * organization resolution, 401 handling, ...) is covered exhaustively by
 * `src/auth/ProductionSessionGate.test.tsx` — these tests only confirm
 * the wiring: that the right provider is reached, and the two public
 * routes bypass it.
 */
const mockUseOidcSession = vi.fn();
vi.mock('../auth/oidcSession', () => ({
  useOidcSession: () => mockUseOidcSession(),
  getOidcUserManager: () => null,
}));

describe('AppRoutes (production mode)', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('redirects an unauthenticated visit to / to /login', async () => {
    vi.stubEnv('MODE', 'production');
    mockUseOidcSession.mockReturnValue({
      status: 'unauthenticated',
      user: null,
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderAt('/');

    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument());
  });

  it('redirects an unauthenticated visit to a non-root application route to /login too', async () => {
    vi.stubEnv('MODE', 'production');
    mockUseOidcSession.mockReturnValue({
      status: 'unauthenticated',
      user: null,
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderAt('/events');

    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument());
  });

  it('does not require any OIDC session to render /login itself', () => {
    vi.stubEnv('MODE', 'production');
    mockUseOidcSession.mockReturnValue({
      status: 'loading',
      user: null,
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderAt('/login');

    expect(screen.getByText(/Checking your session/)).toBeInTheDocument();
  });
});
