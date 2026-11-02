import { cleanup, render, screen, waitFor } from '@testing-library/react';
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
  ])('a %s refusal shows its own guidance', async (reason, title) => {
    session();
    storePendingInvitation(TOKEN);
    vi.mocked(inspectInvitation).mockResolvedValue(INVITATION);
    vi.mocked(acceptInvitation).mockRejectedValue(rejected(reason));

    renderAt('/invite/complete');
    await userEvent.click(await screen.findByRole('button', { name: 'Join Acme Safety' }));

    expect(await screen.findByText(title)).toBeInTheDocument();
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
