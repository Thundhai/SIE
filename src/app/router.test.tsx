import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../auth/AuthContext';
import type { AuthContextValue } from '../auth/types';
import { AppRoutes } from './router';

/**
 * A fully-authorized dev context (see below) makes several routes'
 * pages genuinely call the real API client (e.g. a site-options filter
 * fetched independently of the data this file's own assertions check —
 * `ApiActionRepository.listSiteOptions`/`ApiEventRepository`'s own
 * equivalent). jsdom has no real network, so an unstubbed `fetch`
 * rejects as a genuine network error; stubbing it to a bland, valid
 * empty response keeps that background noise from surfacing as an
 * unhandled rejection in an unrelated test — none of this file's
 * assertions depend on what any of these calls actually return.
 */
beforeEach(() => {
  // `[]` (not `{}`): several of these background calls (e.g.
  // `listSites()`) expect a bare array, not an object -- a generic
  // empty list is a valid response shape for every one of them.
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * Dev-mode routing. `<AppRoutes/>` manages its own auth provider
 * internally via `AuthGate` (SIE Milestone G3-1); under the test
 * runner's default auth mode ("dev" — see `authMode.ts`), that's
 * `DevAuthProvider`.
 *
 * **SIE Milestone G3-2.** Every non-Home route is now also wrapped in
 * `PermissionRoute` (see `router.tsx`'s own docstring), so these tests
 * mock `DevAuthProvider` itself to supply a fully-authorized context —
 * DevAuthProvider's own real identity-resolution logic has its own
 * dedicated test file (`DevAuthProvider.test.tsx`) and is not what this
 * file is about. `authorizedDevAuthValue` can be overridden per test
 * (see the dedicated "authorization" describe block below) to exercise
 * the denied path for a direct URL/deep link.
 */
const mockDevAuthValue = vi.fn<() => AuthContextValue>();

vi.mock('../auth/DevAuthProvider', () => ({
  DevAuthProvider: ({ children }: { children: ReactNode }) => (
    <AuthContext.Provider value={mockDevAuthValue()}>{children}</AuthContext.Provider>
  ),
}));

const FULLY_AUTHORIZED_DEV_VALUE: AuthContextValue = {
  isAuthenticated: true,
  isDevIdentity: true,
  user: { id: 'dev-user-1', name: 'Dev User', email: 'dev@example.com' },
  organization: { id: 'dev-org-1', name: 'Dev Organization' },
  memberships: [{ organizationId: 'dev-org-1', organizationName: 'Dev Organization', role: 'ORG_ADMIN' }],
  permissions: [],
  // Mirrors an ORG_ADMIN, whose real ROLE_PERMISSIONS set is every
  // permission -- exactly what lets every route in these tests render.
  hasPermission: () => true,
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('AppRoutes (dev mode, fully authorized)', () => {
  beforeEach(() => {
    mockDevAuthValue.mockReturnValue(FULLY_AUTHORIZED_DEV_VALUE);
  });

  it('renders Home at /', () => {
    renderAt('/');
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  });

  it('renders Events at /events', () => {
    renderAt('/events');
    expect(screen.getByRole('heading', { name: 'Events' })).toBeInTheDocument();
  });

  it('renders Event Detail for a known fixture id at /events/:eventId', async () => {
    // Exercises the fixture-backed fallback (useEventRepository.ts picks
    // FixtureEventRepository specifically when no organization is
    // established) -- unrelated to this describe block's permission
    // grant, which still applies (hasPermission stays true, so
    // PermissionRoute still passes); only the repository choice differs.
    mockDevAuthValue.mockReturnValue({ ...FULLY_AUTHORIZED_DEV_VALUE, organization: null });
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
    // Same rationale as the Event Detail test above -- exercises
    // FixtureActionRepository's own fallback, unrelated to this block's
    // permission grant.
    mockDevAuthValue.mockReturnValue({ ...FULLY_AUTHORIZED_DEV_VALUE, organization: null });
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
 * SIE Milestone G3-2 — direct URL/deep-link authorization. Proves the
 * route guard itself, not merely that Sidebar hides a link: an
 * authenticated user who lacks the required permission is denied even
 * when navigating straight to the URL, with no Sidebar link involved at
 * all. Home has no permission requirement (see `routePermissions.ts`),
 * so it is deliberately excluded from this matrix.
 */
describe('AppRoutes (dev mode, insufficient permission)', () => {
  beforeEach(() => {
    mockDevAuthValue.mockReturnValue({
      isAuthenticated: true,
      isDevIdentity: true,
      user: { id: 'dev-user-1', name: 'Dev User', email: 'dev@example.com' },
      organization: { id: 'dev-org-1', name: 'Dev Organization' },
      memberships: [{ organizationId: 'dev-org-1', organizationName: 'Dev Organization', role: 'VIEWER' }],
      permissions: [],
      // A VIEWER-shaped stub missing every permission these routes
      // require -- direct evidence, not an assumption, that each one
      // actually enforces its own gate.
      hasPermission: () => false,
    });
  });

  it.each([
    ['/events', 'Events'],
    ['/actions', 'Actions'],
    ['/risk-assessments', 'Risk Assessments'],
    ['/intelligence', 'Intelligence'],
    ['/knowledge', 'Knowledge'],
    ['/reports', 'Reports'],
    ['/administration', 'Administration'],
  ])('denies direct navigation to %s (%s) with Access Denied, not the page content', (path, pageName) => {
    renderAt(path);
    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: pageName })).not.toBeInTheDocument();
  });

  it('manually typing the URL (no Sidebar link involved) still produces Access Denied', () => {
    // renderAt() never clicks a Sidebar link -- MemoryRouter's
    // initialEntries is the direct-URL-entry equivalent for a test.
    renderAt('/administration');
    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  });

  it('still renders Home, which has no permission requirement', () => {
    renderAt('/');
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
