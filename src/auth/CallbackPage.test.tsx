import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CallbackPage } from './CallbackPage';

const mockGetOidcUserManager = vi.fn();
vi.mock('./oidcSession', () => ({
  getOidcUserManager: () => mockGetOidcUserManager(),
}));

function renderCallbackPage() {
  return render(
    <MemoryRouter initialEntries={['/callback?code=abc&state=xyz']}>
      <Routes>
        <Route path="/callback" element={<CallbackPage />} />
        <Route path="/" element={<div>Home</div>} />
        <Route path="/login" element={<div>Login</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CallbackPage', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.stubEnv('MODE', 'production');
  });

  it('redirects to the application in dev mode — there is no OIDC callback there', () => {
    vi.stubEnv('MODE', 'test');
    renderCallbackPage();
    expect(screen.getByText('Home')).toBeInTheDocument();
  });

  it('shows an error state when OIDC is not configured at all', () => {
    mockGetOidcUserManager.mockReturnValue(null);
    renderCallbackPage();
    expect(screen.getByRole('alert')).toHaveTextContent('Sign-in is not configured');
  });

  it('processes a successful interactive callback and redirects to the application, clearing the ?code=... URL', async () => {
    const signinRedirectCallback = vi.fn().mockResolvedValue({ access_token: 'tok' });
    mockGetOidcUserManager.mockReturnValue({ signinRedirectCallback, signinSilentCallback: vi.fn() });

    renderCallbackPage();

    await waitFor(() => expect(screen.getByText('Home')).toBeInTheDocument());
    expect(signinRedirectCallback).toHaveBeenCalledTimes(1);
  });

  it('shows a deterministic error state, with a way back to /login, on callback failure', async () => {
    const signinRedirectCallback = vi.fn().mockRejectedValue(new Error('invalid state'));
    mockGetOidcUserManager.mockReturnValue({ signinRedirectCallback, signinSilentCallback: vi.fn() });

    renderCallbackPage();

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('invalid state'));
    expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/login');
    expect(screen.queryByText('Home')).not.toBeInTheDocument();
  });

  it('calls signinSilentCallback(), not signinRedirectCallback(), when loaded inside the silent-renew iframe, and renders nothing visible', async () => {
    const originalTop = window.top;
    Object.defineProperty(window, 'top', { value: {}, configurable: true });

    const signinRedirectCallback = vi.fn().mockResolvedValue(undefined);
    const signinSilentCallback = vi.fn().mockResolvedValue(undefined);
    mockGetOidcUserManager.mockReturnValue({ signinRedirectCallback, signinSilentCallback });

    const { container } = renderCallbackPage();

    await waitFor(() => expect(signinSilentCallback).toHaveBeenCalledTimes(1));
    expect(signinRedirectCallback).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();

    Object.defineProperty(window, 'top', { value: originalTop, configurable: true });
  });
});
