import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AddMemberDrawer } from './AddMemberDrawer';
import { ApiError } from '../../services/api/errors';
import type { OrganizationMembership } from '../../services/api/organizations';

vi.mock('../../services/api/administration', () => ({
  addMember: vi.fn(),
}));

import { addMember } from '../../services/api/administration';

/**
 * Add Member deliberately has no name/email lookup — the backend has no
 * `GET /users` endpoint (SIE Milestone 18's documented contract gap) —
 * so a raw, client-validated user id is the only input surface.
 */
describe('AddMemberDrawer', () => {
  it('rejects a non-UUID user id before ever calling the API', async () => {
    render(<AddMemberDrawer isOpen onClose={() => {}} organizationId="org-1" onAdded={() => {}} />);

    await userEvent.type(screen.getByLabelText('User ID'), 'not-a-uuid');
    await userEvent.click(screen.getByRole('button', { name: 'Add member' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Enter a valid existing user id (UUID).');
    expect(addMember).not.toHaveBeenCalled();
  });

  it('requires a role to be chosen', async () => {
    render(<AddMemberDrawer isOpen onClose={() => {}} organizationId="org-1" onAdded={() => {}} />);

    await userEvent.type(screen.getByLabelText('User ID'), '11111111-1111-1111-1111-111111111111');
    await userEvent.click(screen.getByRole('button', { name: 'Add member' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Choose a role.');
    expect(addMember).not.toHaveBeenCalled();
  });

  it('adds a member with the chosen role and status', async () => {
    const membership = { id: 'mem-1', user_id: '11111111-1111-1111-1111-111111111111', organization_id: 'org-1', role: 'HSE_MANAGER', status: 'ACTIVE' } satisfies OrganizationMembership;
    vi.mocked(addMember).mockResolvedValue(membership);
    const onAdded = vi.fn();
    const onClose = vi.fn();

    render(<AddMemberDrawer isOpen onClose={onClose} organizationId="org-1" onAdded={onAdded} />);

    await userEvent.type(screen.getByLabelText('User ID'), '11111111-1111-1111-1111-111111111111');
    await userEvent.selectOptions(screen.getByLabelText('Role'), 'HSE_MANAGER');
    await userEvent.click(screen.getByRole('button', { name: 'Add member' }));

    await waitFor(() =>
      expect(addMember).toHaveBeenCalledWith('org-1', { userId: '11111111-1111-1111-1111-111111111111', role: 'HSE_MANAGER', status: 'ACTIVE' }),
    );
    await waitFor(() => expect(onAdded).toHaveBeenCalledWith(membership));
    expect(onClose).toHaveBeenCalled();
  });

  it('on a 404, reports that no such user exists rather than a generic error', async () => {
    vi.mocked(addMember).mockRejectedValue(new ApiError('Not found', { status: 404 }));

    render(<AddMemberDrawer isOpen onClose={() => {}} organizationId="org-1" onAdded={() => {}} />);

    await userEvent.type(screen.getByLabelText('User ID'), '11111111-1111-1111-1111-111111111111');
    await userEvent.selectOptions(screen.getByLabelText('Role'), 'HSE_MANAGER');
    await userEvent.click(screen.getByRole('button', { name: 'Add member' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('No user exists with that id.'));
  });

  it('on a 403, shows a permission message naming the required scope', async () => {
    vi.mocked(addMember).mockRejectedValue(new ApiError('Forbidden', { status: 403 }));

    render(<AddMemberDrawer isOpen onClose={() => {}} organizationId="org-1" onAdded={() => {}} />);

    await userEvent.type(screen.getByLabelText('User ID'), '11111111-1111-1111-1111-111111111111');
    await userEvent.selectOptions(screen.getByLabelText('Role'), 'HSE_MANAGER');
    await userEvent.click(screen.getByRole('button', { name: 'Add member' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('users:manage'));
  });
});
