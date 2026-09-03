import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthProviderStub } from '../../test/authTestUtils';
import { ActionDetailPage } from './ActionDetailPage';

function renderAt(actionId: string, permissions: string[] = []) {
  return render(
    <AuthProviderStub value={{ hasPermission: (permission) => permissions.includes(permission) }}>
      <MemoryRouter initialEntries={[`/actions/${actionId}`]}>
        <Routes>
          <Route path="/actions/:actionId" element={<ActionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

describe('ActionDetailPage', () => {
  it('shows a loading state before the fixture detail resolves', () => {
    renderAt('ACT-2001');
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders the fixture action\'s core fields', async () => {
    renderAt('ACT-2001');
    await waitFor(() => expect(screen.getByRole('heading', { name: /Review reversing procedure/ })).toBeInTheDocument());

    expect(screen.getByText('Jordan Blake')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
    expect(screen.getByText('In progress')).toBeInTheDocument();
  });

  it('shows a not-found empty state for an id that does not exist in the fixture data', async () => {
    renderAt('ACT-DOES-NOT-EXIST');
    await waitFor(() => expect(screen.getByText('Action not found')).toBeInTheDocument());
  });

  it('hides the status-change and reassignment controls without the matching permission', async () => {
    renderAt('ACT-2002'); // OPEN, no permissions granted
    await waitFor(() => expect(screen.getByRole('heading', { name: /Install edge protection/ })).toBeInTheDocument());

    expect(screen.getByText("You do not have permission to change this action's status.")).toBeInTheDocument();
    expect(screen.getByText('You do not have permission to reassign this action.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  });

  it('a permitted user can change status, and the backend transition rule is respected (never optimistic)', async () => {
    renderAt('ACT-2002', ['intervention:manage']); // OPEN -> IN_PROGRESS is a MANAGE-level transition

    await waitFor(() => expect(screen.getByRole('heading', { name: /Install edge protection/ })).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Change status to'), 'IN_PROGRESS');
    await userEvent.click(screen.getByRole('button', { name: 'Update status' }));

    await waitFor(() => expect(screen.getByText('In progress')).toBeInTheDocument());
  });

  it('a terminal action cannot be reopened through the UI', async () => {
    renderAt('ACT-2004', ['intervention:manage', 'intervention:close']); // COMPLETED

    await waitFor(() => expect(screen.getByRole('heading', { name: /Audit permit documentation/ })).toBeInTheDocument());
    expect(screen.getByText(/cannot be reopened/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Change status to')).not.toBeInTheDocument();
  });

  it('a permitted user can reassign the action', async () => {
    renderAt('ACT-2006', ['intervention:assign']); // owner already Priya Anand

    await waitFor(() => expect(screen.getByRole('heading', { name: /Confirm spill kit inventory/ })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole('option', { name: 'Marcus Feld' })).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Owner'), 'Marcus Feld');
    await userEvent.click(screen.getByRole('button', { name: 'Save assignment' }));

    await waitFor(() => expect(screen.getAllByText('Marcus Feld').length).toBeGreaterThan(0));
  });

  it('a permitted user can edit the action through the drawer', async () => {
    renderAt('ACT-2006', ['intervention:manage']);

    await waitFor(() => expect(screen.getByRole('heading', { name: /Confirm spill kit inventory/ })).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog');
    const titleInput = within(dialog).getByLabelText('Title');
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, 'Updated spill kit inventory check');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Updated spill kit inventory check' })).toBeInTheDocument());
  });
});
