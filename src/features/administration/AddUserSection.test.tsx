import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../../auth/AuthContext';
import type { AuthContextValue } from '../../auth/types';
import { ApiError } from '../../services/api/errors';
import type { AddedUser } from '../../services/api/users';
import { AddUserSection } from './AddUserSection';

vi.mock('../../services/api/users', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/api/users')>()),
  addUser: vi.fn(),
  resendPasswordEmail: vi.fn(),
}));
import { addUser, resendPasswordEmail } from '../../services/api/users';

function added(overrides: Partial<AddedUser> = {}): AddedUser {
  return {
    user_id: 'user-9',
    organization_id: 'org-1',
    role: 'VIEWER',
    outcome: 'account_created',
    email_sent: true,
    email_failed: false,
    ...overrides,
  };
}

function renderSection(permissions: string[] = ['users:manage'], onAdded = vi.fn()) {
  const value: AuthContextValue = {
    isAuthenticated: true,
    isDevIdentity: false,
    user: { id: 'admin-1', name: 'Admin', email: 'admin@example.com' },
    organization: { id: 'org-1', name: 'Test Org' },
    memberships: [],
    permissions,
    hasPermission: (permission) => permissions.includes(permission),
  };
  render(
    <AuthContext.Provider value={value}>
      <AddUserSection organizationId="org-1" onAdded={onAdded} />
    </AuthContext.Provider>,
  );
  return { onAdded };
}

async function submit(email = 'new.person@example.com', name = 'New Person') {
  await userEvent.type(screen.getByLabelText('Email'), email);
  if (name) await userEvent.type(screen.getByLabelText('Full name (optional)'), name);
  await userEvent.click(screen.getByRole('button', { name: 'Add' }));
}

function refusal(reason: string, status = 409) {
  return new ApiError('refused', { status, code: 'USER_ADD_REJECTED', details: { reason } });
}

describe('AddUserSection', () => {
  afterEach(() => {
    cleanup();
    vi.resetAllMocks();
  });

  it('is hidden without users:manage', () => {
    renderSection(['users:read']);
    expect(screen.queryByText('Add user')).not.toBeInTheDocument();
  });

  it('adds a new person and says a set-password email was sent', async () => {
    vi.mocked(addUser).mockResolvedValue(added());
    const { onAdded } = renderSection();

    await submit();

    expect(addUser).toHaveBeenCalledWith('org-1', { email: 'new.person@example.com', role: 'VIEWER', name: 'New Person' });
    expect(await screen.findByText('new.person@example.com was added as Viewer.')).toBeInTheDocument();
    expect(screen.getByText(/We emailed them a link to set their password/)).toBeInTheDocument();
    expect(onAdded).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Email')).toHaveValue('');
  });

  it('omits an empty name', async () => {
    vi.mocked(addUser).mockResolvedValue(added());
    renderSection();

    await submit('a@example.com', '');

    expect(addUser).toHaveBeenCalledWith('org-1', { email: 'a@example.com', role: 'VIEWER' });
  });

  it('tells the admin when the person can sign in straight away', async () => {
    vi.mocked(addUser).mockResolvedValue(added({ outcome: 'existing_sign_in', email_sent: false }));
    renderSection();

    await submit();

    expect(await screen.findByText('They already have a sign-in, so they can sign in now.')).toBeInTheDocument();
    expect(screen.queryByText(/We emailed them/)).not.toBeInTheDocument();
  });

  it('offers to resend when the email could not be sent', async () => {
    vi.mocked(addUser).mockResolvedValue(added({ email_sent: false, email_failed: true }));
    vi.mocked(resendPasswordEmail).mockResolvedValue({ email_sent: true });
    renderSection();

    await submit();
    await userEvent.click(await screen.findByRole('button', { name: 'Send email again' }));

    expect(resendPasswordEmail).toHaveBeenCalledWith('org-1', 'user-9');
    expect(await screen.findByText(/We emailed them a link to set their password/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send email again' })).not.toBeInTheDocument();
  });

  it.each([
    ['already_member', 'This person is already a member of this organization.'],
    ['auth0_account_unverified', /never verified it/],
    ['not_configured', "Adding users isn't set up on this deployment yet."],
    ['auth0_unavailable', /Nothing was changed/],
  ])('explains the %s refusal in plain words', async (reason, text) => {
    vi.mocked(addUser).mockRejectedValue(refusal(reason));
    const { onAdded } = renderSection();

    await submit();

    expect(await screen.findByRole('alert')).toHaveTextContent(text);
    expect(onAdded).not.toHaveBeenCalled();
    // The form keeps what was typed, so it can be corrected and retried.
    expect(screen.getByLabelText('Email')).toHaveValue('new.person@example.com');
  });
});
