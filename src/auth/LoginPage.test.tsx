import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LoginPage } from './LoginPage';

const mockUseOidcSession = vi.fn();
vi.mock('./oidcSession', () => ({
  useOidcSession: () => mockUseOidcSession(),
}));

function renderLoginPage(initialEntries: string[] = ['/login']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>Home</div>} />
        <Route path="/events" element={<div>Events</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LoginPage', () => {
  beforeEach(() => {
    mockUseOidcSession.mockReturnValue({
      status: 'unauthenticated',
      user: null,
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
  });

  it('redirects to the application immediately in dev mode — there is no login step there', () => {
    renderLoginPage();
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.queryByText('Sign in')).not.toBeInTheDocument();
  });

  it('shows a checking-session state while the OIDC session is resolving', () => {
    vi.stubEnv('MODE', 'production');
    mockUseOidcSession.mockReturnValue({
      status: 'loading',
      user: null,
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderLoginPage();

    expect(screen.getByText(/Checking your session/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument();
  });

  it('shows a single "Sign in" action when unauthenticated, and clicking it calls signIn()', async () => {
    vi.stubEnv('MODE', 'production');
    const signIn = vi.fn().mockResolvedValue(undefined);
    mockUseOidcSession.mockReturnValue({
      status: 'unauthenticated',
      user: null,
      error: null,
      signIn,
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderLoginPage();
    const button = screen.getByRole('button', { name: 'Sign in' });
    expect(button).toHaveFocus();

    await userEvent.click(button);

    expect(signIn).toHaveBeenCalledTimes(1);
  });

  it('shows a deterministic failure message when signIn() itself rejects', async () => {
    vi.stubEnv('MODE', 'production');
    const signIn = vi.fn().mockRejectedValue(new Error('popup blocked'));
    mockUseOidcSession.mockReturnValue({
      status: 'unauthenticated',
      user: null,
      error: null,
      signIn,
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => null,
    });

    renderLoginPage();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('popup blocked'));
  });

  it('redirects an already-authenticated user straight into the application', () => {
    vi.stubEnv('MODE', 'production');
    mockUseOidcSession.mockReturnValue({
      status: 'authenticated',
      user: { access_token: 'tok', expired: false },
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => 'tok',
    });

    renderLoginPage();

    expect(screen.getByText('Home')).toBeInTheDocument();
  });

  it('redirects back to the originally-requested route when one was recorded', () => {
    vi.stubEnv('MODE', 'production');
    mockUseOidcSession.mockReturnValue({
      status: 'authenticated',
      user: { access_token: 'tok', expired: false },
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn(),
      getAccessTokenLive: () => 'tok',
    });

    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/login', state: { from: { pathname: '/events' } } }]}
      >
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/events" element={<div>Events</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Events')).toBeInTheDocument();
  });

  it('never renders any development-identity control', () => {
    vi.stubEnv('MODE', 'production');
    renderLoginPage();
    expect(screen.queryByText(/development/i)).not.toBeInTheDocument();
  });
});
