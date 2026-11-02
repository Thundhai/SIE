import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../../auth/AuthContext';
import type { AuthContextValue } from '../../auth/types';
import type { Invitation } from '../../services/api/invitations';
import { InvitationsSection } from './InvitationsSection';

vi.mock('../../services/api/invitations', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/api/invitations')>()),
  listInvitations: vi.fn(),
  createInvitation: vi.fn(),
  resendInvitation: vi.fn(),
  revokeInvitation: vi.fn(),
}));
import { createInvitation, listInvitations, resendInvitation, revokeInvitation } from '../../services/api/invitations';

function invitation(overrides: Partial<Invitation> = {}): Invitation {
  return {
    id: 'inv-1',
    organization_id: 'org-1',
    email: 'pending@example.com',
    role: 'VIEWER',
    status: 'PENDING',
    created_at: '2026-11-02T00:00:00Z',
    expires_at: '2026-11-05T00:00:00Z',
    created_by_user_id: 'admin-1',
    registration_started_at: null,
    verified_at: null,
    accepted_at: null,
    revoked_at: null,
    accepted_user_id: null,
    issue_count: 1,
    ...overrides,
  };
}

function renderSection(permissions: string[] = ['users:manage']) {
  const value: AuthContextValue = {
    isAuthenticated: true,
    isDevIdentity: false,
    user: { id: 'admin-1', name: 'Admin', email: 'admin@example.com' },
    organization: { id: 'org-1', name: 'Test Org' },
    memberships: [],
    permissions,
    hasPermission: (permission) => permissions.includes(permission),
  };
  return render(
    <AuthContext.Provider value={value}>
      <InvitationsSection organizationId="org-1" />
    </AuthContext.Provider>,
  );
}

describe('InvitationsSection', () => {
  beforeEach(() => {
    vi.mocked(listInvitations).mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
    vi.resetAllMocks();
    vi.restoreAllMocks();
  });

  it('is hidden, and never calls the API, without users:manage', () => {
    renderSection(['users:read']);
    expect(screen.queryByText('Invitations')).not.toBeInTheDocument();
    expect(listInvitations).not.toHaveBeenCalled();
  });

  it('lists invitations with their status and no code', async () => {
    vi.mocked(listInvitations).mockResolvedValue([
      invitation(),
      invitation({ id: 'inv-2', email: 'done@example.com', status: 'ACCEPTED', accepted_at: '2026-11-03T00:00:00Z' }),
      invitation({ id: 'inv-3', email: 'gone@example.com', status: 'REVOKED' }),
    ]);

    renderSection();

    const pendingRow = (await screen.findByText('pending@example.com')).closest('tr') as HTMLElement;
    expect(within(pendingRow).getByText('Pending')).toBeInTheDocument();
    expect(within(pendingRow).getByRole('button', { name: /Resend/ })).toBeInTheDocument();
    expect(within(pendingRow).getByText('You')).toBeInTheDocument(); // created by the signed-in admin
    expect(screen.getByText(/to Test Org/)).toBeInTheDocument();
    const acceptedRow = screen.getByText('done@example.com').closest('tr') as HTMLElement;
    expect(within(acceptedRow).getByText('Accepted')).toBeInTheDocument();
    expect(within(acceptedRow).queryByRole('button')).not.toBeInTheDocument();
    const revokedRow = screen.getByText('gone@example.com').closest('tr') as HTMLElement;
    expect(within(revokedRow).queryByRole('button')).not.toBeInTheDocument();
  });

  it('creates an invitation and shows its link once, with the code in the fragment', async () => {
    vi.mocked(createInvitation).mockResolvedValue({
      invitation: invitation({ email: 'new@example.com', role: 'HSE_ANALYST' }),
      code: 'sie_link_ONE-TIME',
    });

    renderSection();
    await userEvent.type(await screen.findByLabelText('Email'), 'new@example.com');
    await userEvent.selectOptions(screen.getByLabelText('Role'), 'HSE_ANALYST');
    await userEvent.selectOptions(screen.getByLabelText('Expires in'), '24');
    await userEvent.click(screen.getByRole('button', { name: 'Invite' }));

    expect(createInvitation).toHaveBeenCalledWith('org-1', {
      email: 'new@example.com',
      role: 'HSE_ANALYST',
      expires_in_hours: 24,
    });
    const link = await screen.findByTestId('invitation-link');
    expect(link.textContent).toBe(`${window.location.origin}/invite#token=sie_link_ONE-TIME`);
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByTestId('invitation-link')).not.toBeInTheDocument();
  });

  it('shows the backend error when an invitation cannot be created', async () => {
    vi.mocked(createInvitation).mockRejectedValue(new Error('An open invitation for this email already exists.'));

    renderSection();
    await userEvent.type(await screen.findByLabelText('Email'), 'dup@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Invite' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('already exists');
  });

  it('resends (showing the new link) and revokes after confirmation', async () => {
    vi.mocked(listInvitations).mockResolvedValue([invitation()]);
    vi.mocked(resendInvitation).mockResolvedValue({ invitation: invitation({ issue_count: 2 }), code: 'sie_link_SECOND' });
    vi.mocked(revokeInvitation).mockResolvedValue(invitation({ status: 'REVOKED' }));
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderSection();
    await userEvent.click(await screen.findByRole('button', { name: 'Resend invitation to pending@example.com' }));
    expect(resendInvitation).toHaveBeenCalledWith('org-1', 'inv-1');
    expect((await screen.findByTestId('invitation-link')).textContent).toContain('sie_link_SECOND');

    await userEvent.click(screen.getByRole('button', { name: 'Revoke invitation to pending@example.com' }));
    await waitFor(() => expect(revokeInvitation).toHaveBeenCalledWith('org-1', 'inv-1'));
  });

  it('revoking the invitation whose link is on screen removes that link', async () => {
    vi.mocked(listInvitations).mockResolvedValue([invitation()]);
    vi.mocked(resendInvitation).mockResolvedValue({ invitation: invitation({ issue_count: 2 }), code: 'sie_link_SECOND' });
    vi.mocked(revokeInvitation).mockResolvedValue(invitation({ status: 'REVOKED' }));
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderSection();
    await userEvent.click(await screen.findByRole('button', { name: 'Resend invitation to pending@example.com' }));
    expect(await screen.findByTestId('invitation-link')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Revoke invitation to pending@example.com' }));

    await waitFor(() => expect(screen.queryByTestId('invitation-link')).not.toBeInTheDocument());
  });

  it('while one row action is pending, every row action is disabled', async () => {
    vi.mocked(listInvitations).mockResolvedValue([
      invitation(),
      invitation({ id: 'inv-2', email: 'other@example.com' }),
    ]);
    let finish: (value: unknown) => void = () => undefined;
    vi.mocked(resendInvitation).mockReturnValue(new Promise((resolve) => (finish = resolve)) as never);

    renderSection();
    await userEvent.click(await screen.findByRole('button', { name: 'Resend invitation to pending@example.com' }));

    for (const name of [
      'Resend invitation to pending@example.com',
      'Revoke invitation to pending@example.com',
      'Resend invitation to other@example.com',
      'Revoke invitation to other@example.com',
    ]) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
    finish({ invitation: invitation({ issue_count: 2 }), code: 'sie_link_X' });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Resend invitation to other@example.com' })).toBeEnabled());
  });

  it('does not revoke when the confirmation is declined', async () => {
    vi.mocked(listInvitations).mockResolvedValue([invitation()]);
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    renderSection();
    await userEvent.click(await screen.findByRole('button', { name: 'Revoke invitation to pending@example.com' }));

    expect(revokeInvitation).not.toHaveBeenCalled();
  });
});
