import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { EventDetailPage } from './EventDetailPage';

vi.mock('../../services/api/events', () => ({
  getEvent: vi.fn(),
}));

import { getEvent } from '../../services/api/events';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderAt(eventId: string) {
  return render(
    <AuthProviderStub value={{ isAuthenticated: true, organization: ORGANIZATION }}>
      <MemoryRouter initialEntries={[`/events/${eventId}`]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

const DETAIL = {
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
  organization_id: 'org-1',
  period_end: null,
  reported_time: null,
  potential_severity: null,
  description: 'A forklift near miss in the north yard.',
  location: null,
  project: null,
  department: null,
  contractor: null,
  activity: null,
  attributes: {},
  data_quality_issues: null,
  provenance: {
    organization_id: 'org-1',
    source_system: 'SafetyCloud',
    source_record_id: 'REF-1',
    source_record_version: null,
    source_schema_version: null,
    ingestion_batch_id: 'batch-1',
    ingestion_source_id: 'ds-1',
    data_source_name: 'SafetyCloud Feed',
    ingestion_time: '2026-06-02T00:00:00Z',
    normalization_version: 'normalize-v1',
    schema_version: 'schema-v1',
    correlation_id: null,
  },
};

describe('EventDetailPage — real API path', () => {
  it('shows a loading state, then the real event, with its real provenance and an insufficient-evidence finding', async () => {
    vi.mocked(getEvent).mockResolvedValue(DETAIL);

    renderAt('evt-1');
    expect(screen.getByRole('status')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Incident' })).toBeInTheDocument());
    expect(screen.getByText('A forklift near miss in the north yard.')).toBeInTheDocument();
    expect(screen.getByText('Insufficient evidence to state a finding here.')).toBeInTheDocument();
    expect(screen.getByText('SafetyCloud Feed')).toBeInTheDocument();
    expect(screen.getByText('batch-1')).toBeInTheDocument();
    expect(screen.queryByText(/Showing example event data/)).not.toBeInTheDocument();
  });

  it('shows a not-found empty state for a 404 (nonexistent or cross-tenant) event', async () => {
    vi.mocked(getEvent).mockRejectedValue(new ApiError('Event not found.', { status: 404 }));

    renderAt('does-not-exist');

    await waitFor(() => expect(screen.getByText('Event not found')).toBeInTheDocument());
  });

  it('shows an error state on a real API failure, with a working retry', async () => {
    vi.mocked(getEvent).mockRejectedValueOnce(new ApiError('Could not reach the SIE API.', { status: 0 }));

    renderAt('evt-1');
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.'));

    vi.mocked(getEvent).mockResolvedValueOnce(DETAIL);
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Incident' })).toBeInTheDocument());
  });
});
