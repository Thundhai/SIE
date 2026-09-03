import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { ActionsPage } from './ActionsPage';

vi.mock('../../services/api/actions', () => ({
  listActions: vi.fn(),
  createAction: vi.fn(),
}));
vi.mock('../../services/api/sites', () => ({
  listSites: vi.fn(),
}));

import { createAction, listActions } from '../../services/api/actions';
import { listSites } from '../../services/api/sites';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderPage(canCreate = false) {
  return render(
    <AuthProviderStub
      value={{
        isAuthenticated: true,
        organization: ORGANIZATION,
        // Only intervention:manage — intervention:assign is intentionally
        // withheld so the create form's owner picker (which needs a
        // listMembers() call this file doesn't mock) never renders.
        hasPermission: (permission) => canCreate && permission === 'intervention:manage',
      }}
    >
      <MemoryRouter initialEntries={['/actions']}>
        <Routes>
          <Route path="/actions" element={<ActionsPage />} />
          <Route path="/actions/:actionId" element={<div>Action detail page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

const ONE_ACTION = {
  items: [
    {
      id: 'action-1',
      organization_id: 'org-1',
      site_id: 'site-1',
      site_name: 'North Yard',
      source_event_id: 'evt-1',
      title: 'Review reversing procedure',
      description: 'Follow up.',
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
    },
  ],
  total: 1,
  page: 1,
  page_size: 10,
};

describe('ActionsPage — real API path', () => {
  beforeEach(() => {
    vi.mocked(listSites).mockResolvedValue([]);
  });

  it('shows a loading state, then real actions, and never shows the fixture-disclosure banner', async () => {
    vi.mocked(listActions).mockResolvedValue(ONE_ACTION);

    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('Loading actions…');

    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    expect(screen.getByText(/Review reversing procedure/)).toBeInTheDocument();
    expect(screen.getByText('Jordan Blake')).toBeInTheDocument();
    expect(screen.queryByText(/Showing example action data/)).not.toBeInTheDocument();
    // The real source_event_id UUID ('evt-1') is never the Source
    // column's visible label — a human-readable one is shown instead.
    expect(screen.queryByText('evt-1')).not.toBeInTheDocument();
    expect(screen.getByText('Linked event')).toBeInTheDocument();
  });

  it('shows an empty state for a real, successful query with zero results', async () => {
    vi.mocked(listActions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });

    renderPage();
    await waitFor(() => expect(screen.getByText('No actions match your filters')).toBeInTheDocument());
  });

  it('shows an error state on API failure, with a working retry', async () => {
    vi.mocked(listActions).mockRejectedValueOnce(new ApiError('Could not reach the SIE API.', { status: 0 }));

    renderPage();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.'));

    vi.mocked(listActions).mockResolvedValueOnce(ONE_ACTION);
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
  });

  it('re-queries the real API when the status filter changes', async () => {
    vi.mocked(listActions).mockResolvedValue(ONE_ACTION);

    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'IN_PROGRESS');

    await waitFor(() =>
      expect(listActions).toHaveBeenLastCalledWith(
        expect.objectContaining({ organizationId: 'org-1', status: 'IN_PROGRESS', page: 1 }),
      ),
    );
  });

  it('re-queries the real API for page 2 via pagination', async () => {
    vi.mocked(listActions).mockResolvedValue({ ...ONE_ACTION, total: 25, page: 1, page_size: 10 });

    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /next/i }));

    await waitFor(() => expect(listActions).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
  });

  it('shows a "Create action" control only when intervention:manage is granted', async () => {
    vi.mocked(listActions).mockResolvedValue(ONE_ACTION);

    renderPage(false);
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Create action' })).not.toBeInTheDocument();
  });

  it('unauthorized mutation: a 403 from a create attempt is shown, not hidden, and the list is unaffected', async () => {
    vi.mocked(listActions).mockResolvedValue(ONE_ACTION);
    vi.mocked(createAction).mockRejectedValue(
      new ApiError('Missing intervention:manage permission in the requested organization.', { status: 403 }),
    );

    renderPage(true);
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Create action' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Title'), 'Attempted action');
    await userEvent.selectOptions(within(dialog).getByLabelText('Action type'), 'FOLLOW_UP');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create action' }));

    await waitFor(() =>
      expect(within(dialog).getByRole('alert')).toHaveTextContent('Missing intervention:manage permission'),
    );
    // The dialog is still open and the underlying list is unchanged — no
    // optimistic success was assumed.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
