import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthProviderStub } from '../../test/authTestUtils';
import { EventDetailPage } from './EventDetailPage';

function renderAt(eventId: string) {
  return render(
    <AuthProviderStub>
      <MemoryRouter initialEntries={[`/events/${eventId}`]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

describe('EventDetailPage', () => {
  it('shows a loading state before the fixture detail resolves', () => {
    renderAt('EVT-1001');
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders the evidence-grounded finding (Finding → Evidence → Context) for an event that has one', async () => {
    renderAt('EVT-1001');
    await waitFor(() => expect(screen.getByRole('heading', { name: /Vehicle incident/ })).toBeInTheDocument());

    expect(screen.getByText('Vehicle-related events have increased over the selected period at this site.')).toBeInTheDocument();
    expect(screen.getByText('Supporting evidence')).toBeInTheDocument();
    expect(screen.getByText('E1')).toBeInTheDocument();
  });

  it('shows "insufficient evidence" rather than fabricating a finding for an event with none', async () => {
    renderAt('EVT-1009');
    await waitFor(() => expect(screen.getByRole('heading', { name: /Housekeeping deficiency/ })).toBeInTheDocument());

    expect(screen.getByText('Insufficient evidence to state a finding here.')).toBeInTheDocument();
  });

  it('shows a not-found empty state for an id that does not exist in the fixture data', async () => {
    renderAt('EVT-DOES-NOT-EXIST');
    await waitFor(() => expect(screen.getByText('Event not found')).toBeInTheDocument());
  });
});
