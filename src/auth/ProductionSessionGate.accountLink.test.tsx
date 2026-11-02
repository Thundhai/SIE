import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../services/api/errors';
import { ProductionSessionGate } from './ProductionSessionGate';

// The real API client and redemption service run here; only the OIDC
// session, the bootstrap calls and `fetch` itself are stand-ins, so the
// test sees the Authorization header the redemption request really carries.
const mockUseOidcSession = vi.fn();
vi.mock('./oidcSession', () => ({
  useOidcSession: () => mockUseOidcSession(),
}));

vi.mock('../services/api/auth', () => ({
  getEffectivePermissions: vi.fn(),
  listAuthOrganizations: vi.fn(),
}));

import { getEffectivePermissions, listAuthOrganizations } from '../services/api/auth';

const CODE = `sie_link_${'Z9y8X7w6'.repeat(5)}`;
const getAccessTokenLive = () => 'live-token';
const signOutLocally = vi.fn().mockResolvedValue(undefined);

function session(accessToken: string) {
  return {
    status: 'authenticated' as const,
    user: { access_token: accessToken, expired: false },
    error: null,
    signIn: vi.fn(),
    signOutLocally,
    getAccessTokenLive,
  };
}

function tree() {
  return (
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route
          path="/"
          element={
            <ProductionSessionGate>
              <div>Authenticated Workspace</div>
            </ProductionSessionGate>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('ProductionSessionGate: a sign-in that becomes unlinked mid-session', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.resetAllMocks();
    window.sessionStorage.clear();
  });

  it('still sends the Bearer token when the code is redeemed', async () => {
    mockUseOidcSession.mockReturnValue(session('first-token'));
    vi.mocked(listAuthOrganizations).mockResolvedValue({
      memberships: [{ organization_id: 'org-1', organization_name: 'Org One', role: 'ORG_ADMIN' }],
      is_platform_admin: false,
    });
    vi.mocked(getEffectivePermissions).mockResolvedValue({
      user_id: 'user-1',
      name: 'Prod User',
      email: 'prod@example.com',
      organization_id: 'org-1',
      organization_name: 'Org One',
      role: 'ORG_ADMIN',
      permissions: [],
      is_platform_admin: false,
      auth_mode: 'production',
      identity_provider: 'test-idp',
    });
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ user_id: 'user-1', kind: 'ACCOUNT_LINK', organization_id: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { rerender } = render(tree());
    expect(await screen.findByText('Authenticated Workspace')).toBeInTheDocument();

    // A silent renewal re-runs the bootstrap; the identity is no longer linked.
    vi.mocked(listAuthOrganizations).mockRejectedValue(new ApiError('not linked', { status: 403 }));
    mockUseOidcSession.mockReturnValue(session('renewed-token'));
    await act(async () => {
      rerender(tree());
    });
    expect(await screen.findByRole('heading', { name: 'Link your account' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Account-link code'), { target: { value: CODE } });
    fireEvent.click(screen.getByRole('button', { name: 'Link account' }));
    expect(await screen.findByText('Your account is linked')).toBeInTheDocument();

    const redeemCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/auth/identity-links/redeem'));
    expect(redeemCall).toBeDefined();
    const [url, init] = redeemCall as [RequestInfo | URL, RequestInit];
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer live-token');
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ code: CODE }));
    expect(String(url)).not.toContain(CODE);
    expect(signOutLocally).not.toHaveBeenCalled();
  });
});
