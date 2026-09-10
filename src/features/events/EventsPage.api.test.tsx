import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { EventsPage } from './EventsPage';

vi.mock('../../services/api/events', () => ({
  listEvents: vi.fn(),
}));
vi.mock('../../services/api/sites', () => ({
  listSites: vi.fn(),
}));

import { listEvents } from '../../services/api/events';
import { listSites } from '../../services/api/sites';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderPage() {
  return render(
    <AuthProviderStub value={{ isAuthenticated: true, organization: ORGANIZATION }}>
      <MemoryRouter initialEntries={['/events']}>
        <EventsPage />
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

const ONE_EVENT = {
  items: [
    {
      id: 'evt-1',
      event_time: '2026-06-01T00:00:00Z',
      event_type: 'INCIDENT',
      event_subtype: null,
      site_id: 'site-1',
      site_name: 'North Yard',
      status: 'open',
      severity: null,
      source_system: 'SafetyCloud',
      source_record_id: 'REF-1',
      data_quality_status: 'VALID',
    },
  ],
  total: 1,
  page: 1,
  page_size: 10,
};

describe('EventsPage — real API path', () => {
  beforeEach(() => {
    vi.mocked(listSites).mockResolvedValue([]);
  });

  it('shows a loading state, then real events, and never shows the fixture-disclosure banner', async () => {
    vi.mocked(listEvents).mockResolvedValue(ONE_EVENT);

    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('Loading events…');

    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    expect(screen.getByText('Incident')).toBeInTheDocument();
    expect(screen.queryByText(/Showing example event data/)).not.toBeInTheDocument();
  });

  it('shows an empty state for a real, successful query with zero results', async () => {
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });

    renderPage();
    await waitFor(() => expect(screen.getByText('No events match your filters')).toBeInTheDocument());
  });

  it('shows an error state on API failure, with a working retry', async () => {
    vi.mocked(listEvents).mockRejectedValueOnce(new ApiError('Could not reach the SIE API.', { status: 0 }));

    renderPage();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.'));

    vi.mocked(listEvents).mockResolvedValueOnce(ONE_EVENT);
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
  });

  it('re-queries the real API when the search filter changes', async () => {
    vi.mocked(listEvents).mockResolvedValue(ONE_EVENT);

    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.type(screen.getByLabelText('Search events'), 'forklift');

    await waitFor(() =>
      expect(listEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ organizationId: 'org-1', search: 'forklift', page: 1 }),
      ),
    );
  });

  it('re-queries the real API for page 2 via pagination', async () => {
    vi.mocked(listEvents).mockResolvedValue({ ...ONE_EVENT, total: 25, page: 1, page_size: 10 });

    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /next/i }));

    await waitFor(() => expect(listEvents).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
  });
});
