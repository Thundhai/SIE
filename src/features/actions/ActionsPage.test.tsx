import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthProviderStub } from '../../test/authTestUtils';
import { ActionsPage } from './ActionsPage';

function renderPage(canCreate = false) {
  return render(
    <AuthProviderStub value={canCreate ? { hasPermission: () => true } : undefined}>
      <MemoryRouter initialEntries={['/actions']}>
        <Routes>
          <Route path="/actions" element={<ActionsPage />} />
          <Route path="/actions/:actionId" element={<div>Action detail page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

describe('ActionsPage', () => {
  it('shows a loading state before the fixture data resolves', () => {
    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('Loading actions…');
  });

  it('renders fixture actions in a table once loaded, and discloses that the data is not live', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    expect(screen.getByText(/Review reversing procedure/)).toBeInTheDocument();
    expect(screen.getByText(/Showing example action data/)).toBeInTheDocument();
  });

  it('filters by search term', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.type(screen.getByLabelText('Search actions'), 'edge protection');
    await waitFor(() => expect(screen.getByText(/Install edge protection/)).toBeInTheDocument());
    expect(screen.queryByText(/Review reversing procedure/)).not.toBeInTheDocument();
  });

  it('shows an empty state when no action matches the filters', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.type(screen.getByLabelText('Search actions'), 'no such action exists anywhere');
    await waitFor(() => expect(screen.getByText('No actions match your filters')).toBeInTheDocument());
  });

  it('never renders the raw sourceEventId UUID as the Source column\'s visible label', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    // ACT-2001's fixture seed has sourceEventId 'EVT-1001' — the id
    // itself must never appear as a table cell's visible text.
    expect(screen.queryByText('EVT-1001')).not.toBeInTheDocument();
    expect(screen.getAllByText('Linked event').length).toBeGreaterThan(0);
  });

  it('does not show a "Create action" control without intervention:manage permission', async () => {
    renderPage(false);
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Create action' })).not.toBeInTheDocument();
  });

  it('navigating a row goes to that action\'s detail page', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.click(screen.getByText(/Review reversing procedure/));
    await waitFor(() => expect(screen.getByText('Action detail page')).toBeInTheDocument());
  });

  it('a permitted user can create an action through the drawer and is taken to it', async () => {
    renderPage(true);
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Create action' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Title'), 'New fixture-created action');
    await userEvent.selectOptions(within(dialog).getByLabelText('Action type'), 'FOLLOW_UP');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create action' }));

    await waitFor(() => expect(screen.getByText('Action detail page')).toBeInTheDocument());
  });
});
