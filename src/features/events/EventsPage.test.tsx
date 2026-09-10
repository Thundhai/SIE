import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthProviderStub } from '../../test/authTestUtils';
import { EventsPage } from './EventsPage';

function renderPage() {
  return render(
    <AuthProviderStub>
      <MemoryRouter initialEntries={['/events']}>
        <EventsPage />
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

describe('EventsPage', () => {
  it('shows a loading state before the fixture data resolves', () => {
    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('Loading events…');
  });

  it('renders fixture events in a table once loaded, and discloses that the data is not live', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    expect(screen.getByText(/Vehicle incident — reversing collision/)).toBeInTheDocument();
    expect(screen.getByText(/Showing example event data/)).toBeInTheDocument();
  });

  it('filters by search term', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.type(screen.getByLabelText('Search events'), 'lifting');
    await waitFor(() => expect(screen.getByText(/Lifting operation/)).toBeInTheDocument());
    expect(screen.queryByText(/Vehicle incident — reversing collision/)).not.toBeInTheDocument();
  });

  it('shows an empty state when no event matches the filters', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.type(screen.getByLabelText('Search events'), 'no such event exists anywhere');
    await waitFor(() => expect(screen.getByText('No events match your filters')).toBeInTheDocument());
  });
});
