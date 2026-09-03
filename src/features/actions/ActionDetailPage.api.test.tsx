import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { ActionDetailPage } from './ActionDetailPage';

vi.mock('../../services/api/actions', () => ({
  getAction: vi.fn(),
  updateActionStatus: vi.fn(),
  updateAction: vi.fn(),
}));
vi.mock('../../services/api/sites', () => ({
  listSites: vi.fn().mockResolvedValue([]),
}));

import { getAction, updateAction, updateActionStatus } from '../../services/api/actions';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderAt(actionId: string, permissions: string[] = []) {
  return render(
    <AuthProviderStub
      value={{
        isAuthenticated: true,
        organization: ORGANIZATION,
        hasPermission: (permission) => permissions.includes(permission),
      }}
    >
      <MemoryRouter initialEntries={[`/actions/${actionId}`]}>
        <Routes>
          <Route path="/actions/:actionId" element={<ActionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

const DETAIL = {
  id: 'action-1',
  organization_id: 'org-1',
  site_id: 'site-1',
  site_name: 'North Yard',
  source_event_id: 'evt-1',
  title: 'Review reversing procedure',
  description: 'Follow up on the incident.',
  action_type: 'CORRECTIVE' as const,
  priority: 'HIGH' as const,
  status: 'OPEN' as const,
  owner_user_id: 'user-1',
  owner_name: 'Jordan Blake',
  due_date: '2026-03-10T00:00:00Z',
  created_by_user_id: 'user-2',
  created_by_api_client_id: null,
  created_at: '2026-02-18T09:15:00Z',
  updated_at: '2026-02-18T09:15:00Z',
  completed_at: null,
  cancelled_at: null,
  external_reference: 'CAPA-2201',
  attributes: {},
};

describe('ActionDetailPage — real API path', () => {
  it('shows a loading state, then the real action', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);

    renderAt('action-1');
    expect(screen.getByRole('status')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());
    expect(screen.getByText('Jordan Blake')).toBeInTheDocument();
    expect(screen.queryByText(/Showing example action data/)).not.toBeInTheDocument();
  });

  it('shows a not-found empty state for a 404 (nonexistent or cross-tenant) action', async () => {
    vi.mocked(getAction).mockRejectedValue(new ApiError('Action not found.', { status: 404 }));

    renderAt('does-not-exist');
    await waitFor(() => expect(screen.getByText('Action not found')).toBeInTheDocument());
  });

  it('shows an error state on a real API failure, with a working retry', async () => {
    vi.mocked(getAction).mockRejectedValueOnce(new ApiError('Could not reach the SIE API.', { status: 0 }));

    renderAt('action-1');
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.'));

    vi.mocked(getAction).mockResolvedValueOnce(DETAIL);
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());
  });

  it('a status transition the backend refuses leaves the displayed status unchanged and shows the error (never optimistic)', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(updateActionStatus).mockRejectedValue(
      new ApiError('This transition is not allowed from the action\'s current status.', { status: 409 }),
    );

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Change status to'), 'IN_PROGRESS');
    await userEvent.click(screen.getByRole('button', { name: 'Update status' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('This transition is not allowed'));
    // Status badge still reads the original, persisted status — the
    // "In progress" text that does exist is only the (still-selected)
    // option inside the status-change <select>, not a status update.
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByLabelText('Change status to')).toHaveValue('IN_PROGRESS');
  });

  it('a status transition the backend accepts updates the displayed status only after the response resolves', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(updateActionStatus).mockResolvedValue({ ...DETAIL, status: 'IN_PROGRESS' });

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Change status to'), 'IN_PROGRESS');
    await userEvent.click(screen.getByRole('button', { name: 'Update status' }));

    await waitFor(() => expect(screen.getByText('In progress')).toBeInTheDocument());
  });

  it('unauthorized mutation: a 403 from a status-change attempt is shown, not hidden, and the action stays as it was', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(updateActionStatus).mockRejectedValue(
      new ApiError('Missing intervention:manage permission in the requested organization.', { status: 403 }),
    );

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Change status to'), 'IN_PROGRESS');
    await userEvent.click(screen.getByRole('button', { name: 'Update status' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Missing intervention:manage permission'));
    expect(screen.getByText('Open')).toBeInTheDocument();
  });

  it('unauthorized mutation: a 403 from an edit attempt is shown in the drawer, not hidden', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(updateAction).mockRejectedValue(
      new ApiError('Missing intervention:manage permission in the requested organization.', { status: 403 }),
    );

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Missing intervention:manage permission'));
  });

  it('assignment permission handling: without intervention:assign, no editable owner control is rendered', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    expect(screen.getByText('You do not have permission to reassign this action.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Owner')).not.toBeInTheDocument();
  });
});
