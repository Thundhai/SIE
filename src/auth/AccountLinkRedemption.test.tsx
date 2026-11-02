import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../services/api/errors';
import { AccountLinkRedemption, redemptionErrorMessage } from './AccountLinkRedemption';
import { ProductionSessionGate } from './ProductionSessionGate';

const mockUseOidcSession = vi.fn();
vi.mock('./oidcSession', () => ({
  useOidcSession: () => mockUseOidcSession(),
}));

vi.mock('../services/api/auth', () => ({
  getEffectivePermissions: vi.fn(),
  listAuthOrganizations: vi.fn(),
}));

vi.mock('../services/api/identityLinks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api/identityLinks')>();
  return { ...actual, redeemAccountLinkCode: vi.fn() };
});

import { getEffectivePermissions, listAuthOrganizations } from '../services/api/auth';
import { redeemAccountLinkCode } from '../services/api/identityLinks';

// Built at runtime so no code-shaped literal sits in the source.
const CODE = `sie_link_${'A1b2C3d4'.repeat(5)}`;

function codeField(): HTMLInputElement {
  return screen.getByLabelText('Account-link code') as HTMLInputElement;
}

function enterAndSubmit(value: string) {
  fireEvent.change(codeField(), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: 'Link account' }));
}

function renderForm() {
  const onLinked = vi.fn();
  const onSignOut = vi.fn();
  render(<AccountLinkRedemption onLinked={onLinked} onSignOut={onSignOut} />);
  return { onLinked, onSignOut };
}

describe('AccountLinkRedemption', () => {
  const consoleSpies: ReturnType<typeof vi.spyOn>[] = [];

  beforeEach(() => {
    window.history.replaceState(null, '', '/');
    for (const method of ['log', 'info', 'warn', 'error', 'debug'] as const) {
      consoleSpies.push(vi.spyOn(console, method));
    }
  });

  afterEach(() => {
    // Nothing the component did may have written the code anywhere a
    // browser keeps it: the address bar, history, storage or the console.
    expect(window.location.href).not.toContain(CODE);
    expect(JSON.stringify(window.history.state ?? null)).not.toContain(CODE);
    for (const store of [window.sessionStorage, window.localStorage]) {
      for (let i = 0; i < store.length; i += 1) {
        expect(store.getItem(store.key(i) ?? '') ?? '').not.toContain(CODE);
      }
    }
    for (const spy of consoleSpies) {
      expect(JSON.stringify(spy.mock.calls)).not.toContain(CODE);
      spy.mockRestore();
    }
    consoleSpies.length = 0;
    cleanup();
    vi.resetAllMocks();
    window.sessionStorage.clear();
  });

  it('renders a code field the browser will not remember', () => {
    renderForm();
    const field = codeField();
    expect(field.getAttribute('autocomplete')).toBe('off');
    expect(field.getAttribute('spellcheck')).toBe('false');
    expect(field.getAttribute('autocapitalize')).toBe('none');
    expect(field.getAttribute('name')).toBeNull();
    expect(field.closest('form')?.getAttribute('action')).toBeNull();
  });

  it('redeems the code with the API, clears it, and shows success', async () => {
    vi.mocked(redeemAccountLinkCode).mockResolvedValue({ user_id: 'u-1', kind: 'ACCOUNT_LINK', organization_id: null });
    const { onLinked } = renderForm();

    enterAndSubmit(`  ${CODE}  `);

    expect(redeemAccountLinkCode).toHaveBeenCalledTimes(1);
    expect(vi.mocked(redeemAccountLinkCode).mock.calls[0][0]).toBe(CODE); // trimmed
    expect(await screen.findByText('Your account is linked')).toBeInTheDocument();
    expect(screen.queryByDisplayValue(CODE)).toBeNull();
    expect(onLinked).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Continue to SIE' }));
    expect(onLinked).toHaveBeenCalledTimes(1);
  });

  it.each([
    [404, 'This code is invalid, already used, or has expired. Ask your administrator for a new one.'],
    [422, "That isn't a valid account-link code. Check it and try again."],
    [401, 'Your sign-in has expired. Sign in again, then enter the code.'],
    [429, 'Too many attempts. Wait a minute, then try again.'],
    [500, 'Could not link your account. Try again, or contact your administrator.'],
  ])('a %i refusal shows a clear message, clears the field and allows another try', async (status, message) => {
    vi.mocked(redeemAccountLinkCode).mockRejectedValue(new ApiError('server text', { status }));
    renderForm();

    enterAndSubmit(CODE);

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(codeField().value).toBe('');
    expect(codeField()).not.toBeDisabled();
    expect(screen.queryByText('Your account is linked')).toBeNull();
  });

  it.each([
    [409, 'This sign-in is already linked to a SIE account.'],
    [403, 'This code cannot link a platform administrator account.'],
  ])("a %i shows the backend's fixed explanation", async (status, backendMessage) => {
    vi.mocked(redeemAccountLinkCode).mockRejectedValue(new ApiError(backendMessage, { status }));
    renderForm();

    enterAndSubmit(CODE);

    expect(await screen.findByText(backendMessage)).toBeInTheDocument();
  });

  it('a network failure says SIE could not be reached', async () => {
    vi.mocked(redeemAccountLinkCode).mockRejectedValue(new ApiError('Could not reach the SIE API: offline', { status: 0 }));
    renderForm();

    enterAndSubmit(CODE);

    expect(await screen.findByText('Could not reach SIE. Check your connection and try again.')).toBeInTheDocument();
  });

  it('refuses something that is not an account-link code without calling the API', () => {
    renderForm();

    enterAndSubmit('not-a-code');
    expect(screen.getByText('Account-link codes start with sie_link_. Check the code and try again.')).toBeInTheDocument();
    enterAndSubmit('sie_link_has a space');
    expect(redeemAccountLinkCode).not.toHaveBeenCalled();
    expect(codeField().value).toBe('');
  });

  it('submits once while a redemption is in flight', async () => {
    let resolve!: (value: { user_id: string; kind: string; organization_id: null }) => void;
    vi.mocked(redeemAccountLinkCode).mockReturnValue(new Promise((res) => (resolve = res)));
    renderForm();

    enterAndSubmit(CODE);
    expect(screen.getByRole('button', { name: 'Linking…' })).toBeDisabled();
    fireEvent.submit(codeField().closest('form')!);
    expect(redeemAccountLinkCode).toHaveBeenCalledTimes(1);

    resolve({ user_id: 'u-1', kind: 'ACCOUNT_LINK', organization_id: null });
    expect(await screen.findByText('Your account is linked')).toBeInTheDocument();
  });

  it('offers a different sign-in', () => {
    const { onSignOut } = renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Use a different sign-in' }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it('never puts the code in a message', () => {
    const withCode = new ApiError(`odd server text ${CODE}`, { status: 404 });
    expect(redemptionErrorMessage(withCode)).not.toContain(CODE);
    expect(redemptionErrorMessage(new Error(CODE))).not.toContain(CODE);
  });
});

describe('ProductionSessionGate with an unlinked sign-in', () => {
  function authenticated() {
    return {
      status: 'authenticated' as const,
      user: { access_token: 'tok-1', expired: false },
      error: null,
      signIn: vi.fn(),
      signOutLocally: vi.fn().mockResolvedValue(undefined),
      getAccessTokenLive: () => 'tok-1',
    };
  }

  function renderGate() {
    return render(
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
      </MemoryRouter>,
    );
  }

  afterEach(() => {
    cleanup();
    vi.resetAllMocks();
    window.sessionStorage.clear();
  });

  it('offers code entry on a 403, then opens the workspace once linked', async () => {
    const oidc = authenticated();
    mockUseOidcSession.mockReturnValue(oidc);
    vi.mocked(listAuthOrganizations)
      .mockRejectedValueOnce(
        new ApiError('This sign-in is not linked to a SIE account.', { status: 403, code: 'AUTHORIZATION_DENIED' }),
      )
      .mockResolvedValue({
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
    vi.mocked(redeemAccountLinkCode).mockResolvedValue({ user_id: 'user-1', kind: 'ACCOUNT_LINK', organization_id: null });

    renderGate();

    expect(await screen.findByRole('heading', { name: 'Link your account' })).toBeInTheDocument();
    expect(screen.queryByText('Authenticated Workspace')).toBeNull();
    enterAndSubmit(CODE);
    fireEvent.click(await screen.findByRole('button', { name: 'Continue to SIE' }));

    expect(await screen.findByText('Authenticated Workspace')).toBeInTheDocument();
    // The gate re-ran its bootstrap after the code was redeemed (first
    // call refused, second resolved); ProdAuthProvider then makes its own.
    expect(vi.mocked(redeemAccountLinkCode).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(listAuthOrganizations).mock.invocationCallOrder[1],
    );
    expect(oidc.signOutLocally).not.toHaveBeenCalled();
  });

  it('"Use a different sign-in" signs out locally', async () => {
    const oidc = authenticated();
    mockUseOidcSession.mockReturnValue(oidc);
    vi.mocked(listAuthOrganizations).mockRejectedValue(new ApiError('not linked', { status: 403 }));

    renderGate();

    fireEvent.click(await screen.findByRole('button', { name: 'Use a different sign-in' }));
    await waitFor(() => expect(oidc.signOutLocally).toHaveBeenCalledTimes(1));
  });

  it('other bootstrap failures still show the existing error screen', async () => {
    mockUseOidcSession.mockReturnValue(authenticated());
    vi.mocked(listAuthOrganizations).mockRejectedValue(new ApiError('Server exploded', { status: 500 }));

    renderGate();

    expect(await screen.findByText('Could not sign you in')).toBeInTheDocument();
    expect(screen.queryByLabelText('Account-link code')).toBeNull();
  });
});
