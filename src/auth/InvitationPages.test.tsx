import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../services/api/errors';
import type { PublicInvitation } from '../services/api/invitations';
import { InvitationCompletePage, InvitationLandingPage } from './InvitationPages';
import { readPendingInvitation, storePendingInvitation } from './invitationFlow';

const mockUseOidcSession = vi.fn();
vi.mock('./oidcSession', () => ({ useOidcSession: () => mockUseOidcSession() }));

const mockPersist = vi.fn();
vi.mock('./organizationPersistence', () => ({ persistActiveOrganizationId: (id: string) => mockPersist(id) }));

vi.mock('../services/api/invitations', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/api/invitations')>()),
  inspectInvitation: vi.fn(),
  startInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
}));
import { acceptInvitation, inspectInvitation, startInvitation } from '../services/api/invitations';

const TOKEN = 'sie_link_testtoken1234567890';

const INVITATION: PublicInvitation = {
  status: 'PENDING',
  organization_id: 'org-1',
  organization_name: 'Acme Safety',
  role: 'HSE_ANALYST',
  invited_email: 'new.hire@example.com',
  expires_at: '2026-11-05T00:00:00Z',
  methods: ['password', 'sso'],
};

function rejected(reason: string, status = 403) {
  return new ApiError('refused', { status, code: 'INVITATION_REJECTED', details: { reason } });
}

function session(overrides: Record<string, unknown> = {}) {
  const value = {
    status: 'authenticated',
    user: { profile: { name: 'New Hire' } },
    error: null,
    signIn: vi.fn().mockResolvedValue(undefined),
    signOutLocally: vi.fn().mockResolvedValue(undefined),
    getAccessTokenLive: () => 'access-token',
    ...overrides,
  };
  mockUseOidcSession.mockReturnValue(value);
  return value;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/invite" element={<InvitationLandingPage />} />
        <Route path="/invite/complete" element={<InvitationCompletePage />} />
        <Route path="/" element={<div>Dashboard</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubEnv('MODE', 'production');
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.resetAllMocks();
  window.sessionStorage.clear();
  window.history.replaceState(null, '', '/');
});

describe('InvitationLandingPage', () => {
  it('moves the code from the URL fragment into session storage and shows the invitation', async () => {
    session({ status: 'unauthenticated', user: null });
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    window.history.replaceState(null, '', `/invite#token=${TOKEN}`);

    renderAt('/invite');

    await waitFor(() => expect(screen.getByText('Acme Safety')).toBeInTheDocument());
    expect(screen.getByText('HSE analyst')).toBeInTheDocument();
    const email = screen.getByLabelText('Invited email') as HTMLInputElement;
    expect(email.value).toBe('new.hire@example.com');
    expect(email.readOnly).toBe(true);
    expect(readPendingInvitation()).toBe(TOKEN);
    expect(window.location.hash).toBe('');
    expect(vi.mocked(inspectInvitation).mock.calls[0][0]).toBe(TOKEN);
  });

  it.each([
    ['Create an account with email and password', 'password'],
    ["Continue with your organization's single sign-on", 'sso'],
  ])('"%s" records the method and signs in with the invited email as a hint', async (label, method) => {
    const oidc = session({ status: 'unauthenticated', user: null });
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(startInvitation).mockResolvedValue({ ...INVITATION, status: 'REGISTRATION_STARTED' });
    storePendingInvitation(TOKEN);

    renderAt('/invite');
    await userEvent.click(await screen.findByRole('button', { name: label }));

    expect(startInvitation).toHaveBeenCalledWith(TOKEN, method);
    expect(oidc.signIn).toHaveBeenCalledWith(
      expect.objectContaining({ login_hint: 'new.hire@example.com', state: { returnTo: '/invite/complete' } }),
    );
  });

  it('an existing user signs in without starting registration', async () => {
    const oidc = session({ status: 'unauthenticated', user: null });
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    storePendingInvitation(TOKEN);

    renderAt('/invite');
    await userEvent.click(await screen.findByRole('button', { name: 'Sign in to accept' }));

    expect(startInvitation).not.toHaveBeenCalled();
    expect(oidc.signIn).toHaveBeenCalled();
  });

  it.each([
    ['EXPIRED', 'This invitation has expired'],
    ['REVOKED', 'This invitation is no longer valid'],
    ['ACCEPTED', 'This invitation has already been used'],
  ])('a %s invitation shows its closed screen and no sign-in buttons', async (status, title) => {
    session({ status: 'unauthenticated', user: null });
    vi.mocked(inspectInvitation).mockResolvedValue({ ...INVITATION, status: status as PublicInvitation['status'] });
    storePendingInvitation(TOKEN);

    renderAt('/invite');

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /email and password/ })).not.toBeInTheDocument();
  });

  it('an unknown code shows the invalid-link screen', async () => {
    session({ status: 'unauthenticated', user: null });
    vi.mocked(inspectInvitation).mockRejectedValue(rejected('invitation_not_found', 404));
    storePendingInvitation(TOKEN);

    renderAt('/invite');

    expect(await screen.findByText('This invitation link is not valid')).toBeInTheDocument();
    expect(readPendingInvitation()).toBeNull();
  });

  it('with no code at all shows the invalid-link screen without calling the API', async () => {
    session({ status: 'unauthenticated', user: null });
    renderAt('/invite');
    expect(await screen.findByText('This invitation link is not valid')).toBeInTheDocument();
    expect(inspectInvitation).not.toHaveBeenCalled();
  });

  it('a malformed code in the link is an invalid link, never a fallback to a remembered invitation', async () => {
    session({ status: 'unauthenticated', user: null });
    storePendingInvitation(TOKEN); // an earlier invitation in this tab
    window.history.replaceState(null, '', '/invite#token=short');

    renderAt('/invite');

    expect(await screen.findByText('This invitation link is not valid')).toBeInTheDocument();
    expect(inspectInvitation).not.toHaveBeenCalled();
    expect(readPendingInvitation()).toBeNull();
    expect(window.location.hash).toBe('');
  });

  it.each([
    ['EXPIRED', 'This invitation has expired'],
    ['REVOKED', 'This invitation is no longer valid'],
  ])('when start reports %s, shows the closed screen instead of sending the person to register', async (status, title) => {
    const oidc = session({ status: 'unauthenticated', user: null });
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(startInvitation).mockResolvedValue({ ...INVITATION, status: status as PublicInvitation['status'] });
    storePendingInvitation(TOKEN);

    renderAt('/invite');
    await userEvent.click(await screen.findByRole('button', { name: 'Create an account with email and password' }));

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(oidc.signIn).not.toHaveBeenCalled();
  });

  it('a new invitation link opened while the page is mounted is validated, not ignored', async () => {
    session({ status: 'unauthenticated', user: null });
    vi.mocked(inspectInvitation).mockImplementation(async (token) =>
      token === TOKEN ? INVITATION : { ...INVITATION, organization_name: 'Second Org' },
    );
    window.history.replaceState(null, '', `/invite#token=${TOKEN}`);
    renderAt('/invite');
    expect(await screen.findByText('Acme Safety')).toBeInTheDocument();

    const second = 'sie_link_secondtoken0987654321';
    window.history.replaceState(null, '', `/invite#token=${second}`);
    act(() => {
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(await screen.findByText('Second Org')).toBeInTheDocument();
    expect(readPendingInvitation()).toBe(second);
    expect(window.location.hash).toBe('');

    window.history.replaceState(null, '', '/invite#token=bad');
    act(() => {
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(await screen.findByText('This invitation link is not valid')).toBeInTheDocument();
    expect(readPendingInvitation()).toBeNull();
    expect(window.location.hash).toBe('');
  });

  it('an action still pending when another link opens never redirects with the old invitation', async () => {
    const oidc = session({ status: 'unauthenticated', user: null });
    const second = 'sie_link_secondtoken0987654321';
    vi.mocked(inspectInvitation).mockImplementation(async (token) =>
      token === TOKEN ? INVITATION : { ...INVITATION, organization_name: 'Second Org', invited_email: 'second@example.com' },
    );
    let finishStart: (value: PublicInvitation) => void = () => undefined;
    vi.mocked(startInvitation).mockReturnValue(new Promise((resolve) => (finishStart = resolve)));
    window.history.replaceState(null, '', `/invite#token=${TOKEN}`);

    renderAt('/invite');
    await userEvent.click(await screen.findByRole('button', { name: 'Create an account with email and password' }));
    window.history.replaceState(null, '', `/invite#token=${second}`);
    act(() => {
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(await screen.findByText('Second Org')).toBeInTheDocument();

    await act(async () => {
      finishStart({ ...INVITATION, status: 'REGISTRATION_STARTED' });
    });

    expect(oidc.signIn).not.toHaveBeenCalled();
    expect(screen.getByText('Second Org')).toBeInTheDocument();
  });

  it('explains that invitations need production sign-in in dev mode', () => {
    vi.stubEnv('MODE', 'test');
    session({ status: 'unauthenticated', user: null });
    renderAt('/invite');
    expect(screen.getByText('Invitations need production sign-in')).toBeInTheDocument();
  });
});

describe('InvitationCompletePage', () => {
  it('accepts with the access token and the full name, then offers the dashboard', async () => {
    session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue({ ...INVITATION, status: 'REGISTRATION_STARTED' });
    vi.mocked(acceptInvitation).mockResolvedValue({
      organization_id: 'org-1',
      user_id: 'user-9',
      role: 'HSE_ANALYST',
      outcome: 'account_created',
    });

    renderAt('/invite/complete');
    const name = (await screen.findByLabelText('Full name')) as HTMLInputElement;
    expect(name.value).toBe('New Hire');
    await userEvent.click(screen.getByRole('button', { name: 'Join Acme Safety' }));

    expect(acceptInvitation).toHaveBeenCalledWith(TOKEN, 'access-token', 'New Hire');
    expect(await screen.findByText("You're in")).toBeInTheDocument();
    expect(mockPersist).toHaveBeenCalledWith('org-1');
    expect(readPendingInvitation()).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Go to your dashboard' }));
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it.each([
    ['email_not_verified', 'Verify your email address', /verified my email/, false],
    ['email_mismatch', 'This invitation is for a different email', /different account/, true],
    ['existing_account_sign_in_required', 'You already have an SIE account', /existing account/, true],
  ])('a %s refusal shows its screen and signs in again', async (reason, title, button, signsOut) => {
    const oidc = session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation).mockRejectedValue(rejected(reason));

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));
    expect(await screen.findByText(title)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: button }));

    expect(oidc.signOutLocally).toHaveBeenCalledTimes(signsOut ? 1 : 0);
    expect(oidc.signIn).toHaveBeenCalledWith(
      expect.objectContaining({ prompt: 'login', state: { returnTo: '/invite/complete' } }),
    );
    expect(mockPersist).not.toHaveBeenCalled();
    expect(readPendingInvitation()).toBe(TOKEN);
  });

  it.each([
    ['account_inactive', 'Your SIE account is not active'],
    ['orphaned_identity_requires_account_link', 'Your sign-in needs to be relinked'],
    ['concurrent_conflict', 'Please try again'],
    ['issuer_not_trusted_for_email', "Registration isn't available for this sign-in"],
    ['email_verification_failed', "Registration isn't available for this sign-in"],
  ])('a %s refusal shows its own guidance', async (reason, title) => {
    session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation).mockRejectedValue(rejected(reason));

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));

    expect(await screen.findByText(title)).toBeInTheDocument();
  });

  it('a provider outage offers a retry, which accepts again', async () => {
    session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation)
      .mockRejectedValueOnce(rejected('email_verification_unavailable', 503))
      .mockResolvedValueOnce({ organization_id: 'org-1', user_id: 'u', role: 'HSE_ANALYST', outcome: 'account_created' });

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));
    expect(await screen.findByText("We couldn't reach your sign-in provider")).toBeInTheDocument();
    expect(screen.queryByText(/finish setting up sign-in/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByText("You're in")).toBeInTheDocument();
    expect(acceptInvitation).toHaveBeenCalledTimes(2);
  });

  it('a 401 from accept clears the local session but keeps the invitation, so sign-in is offered', async () => {
    const oidc = session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation).mockRejectedValue(new ApiError('expired', { status: 401 }));

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));

    await waitFor(() => expect(oidc.signOutLocally).toHaveBeenCalledTimes(1));
    expect(readPendingInvitation()).toBe(TOKEN);
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });

  it('a silent token renewal after acceptance keeps the success screen and does not re-inspect', async () => {
    session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation).mockResolvedValue({
      organization_id: 'org-1',
      user_id: 'u',
      role: 'HSE_ANALYST',
      outcome: 'account_created',
    });

    const view = renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));
    expect(await screen.findByText("You're in")).toBeInTheDocument();

    session({ user: { profile: { name: 'New Hire' }, access_token: 'renewed' } }); // a new user object
    view.rerender(
      <MemoryRouter initialEntries={['/invite/complete']}>
        <Routes>
          <Route path="/invite/complete" element={<InvitationCompletePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("You're in")).toBeInTheDocument();
    expect(screen.queryByText('This invitation link is not valid')).not.toBeInTheDocument();
    expect(inspectInvitation).toHaveBeenCalledTimes(1);
  });

  it('an inspection still pending when acceptance starts cannot overwrite the result', async () => {
    const oidc = session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValueOnce(INVITATION);
    let resolveAccept: (value: unknown) => void = () => undefined;
    vi.mocked(acceptInvitation).mockReturnValue(new Promise((resolve) => (resolveAccept = resolve)) as never);

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));
    expect(oidc.signIn).not.toHaveBeenCalled();
    resolveAccept({ organization_id: 'org-1', user_id: 'u', role: 'HSE_ANALYST', outcome: 'account_created' });

    expect(await screen.findByText("You're in")).toBeInTheDocument();
  });

  it('an over-long provider name is cut to the 255 characters the API accepts', async () => {
    session({ user: { profile: { name: 'N'.repeat(400) } } });
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation).mockResolvedValue({
      organization_id: 'org-1',
      user_id: 'u',
      role: 'HSE_ANALYST',
      outcome: 'account_created',
    });

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));

    expect(acceptInvitation).toHaveBeenCalledWith(TOKEN, 'access-token', 'N'.repeat(255));
  });

  it('an invitation revoked meanwhile shows the closed screen and forgets the code', async () => {
    session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation).mockRejectedValue(rejected('invitation_revoked', 410));

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));

    expect(await screen.findByText('This invitation is no longer valid')).toBeInTheDocument();
    expect(readPendingInvitation()).toBeNull();
  });

  it('asks a signed-out visitor to sign in first, without calling accept', async () => {
    const oidc = session({ status: 'unauthenticated', user: null });
    storePendingInvitation(TOKEN);

    renderAt('/invite/complete');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(acceptInvitation).not.toHaveBeenCalled();
    expect(oidc.signIn).toHaveBeenCalledWith({ state: { returnTo: '/invite/complete' } });
  });

  it('shows a rate-limit message on 429', async () => {
    session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation).mockRejectedValue(new ApiError('slow down', { status: 429 }));

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));

    expect(await screen.findByText(/Too many attempts/)).toBeInTheDocument();
  });
});
