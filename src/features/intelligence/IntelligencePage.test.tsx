import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { IntelligencePage } from './IntelligencePage';

vi.mock('../../services/api/intelligence', () => ({
  getEnterpriseIntelligence: vi.fn(),
}));

import { getEnterpriseIntelligence } from '../../services/api/intelligence';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderPage() {
  return render(
    <AuthProviderStub value={{ isAuthenticated: true, organization: ORGANIZATION }}>
      <MemoryRouter initialEntries={['/intelligence']}>
        <IntelligencePage />
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

function baseIntelligence(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    scope: 'organization',
    organization_id: 'org-1',
    entity_id: null,
    as_of: '2026-06-01T00:00:00Z',
    window_days: 90,
    data_sufficiency: { status: 'SUFFICIENT_DATA', event_count: 40 },
    deterministic_risk: { score: 61.2, classification: 'HIGH', version: 'v1', components: [], insufficient_data_reason: null },
    trend: {
      classification: 'DETERIORATING',
      metric: 'total_events',
      current_value: 20,
      previous_value: 10,
      absolute_change: 10,
      percentage_change: 100,
      current_period_start: '2026-05-01T00:00:00Z',
      current_period_end: '2026-06-01T00:00:00Z',
      previous_period_start: '2026-04-01T00:00:00Z',
      previous_period_end: '2026-05-01T00:00:00Z',
      calculation_version: 'v1',
    },
    indicators: [
      { key: 'near_misses', label: 'Near misses', value: 12, category: 'LEADING', period_start: '2026-05-01T00:00:00Z', period_end: '2026-06-01T00:00:00Z', window_days: 30, previous_value: 8, absolute_change: 4, percentage_change: 50, trend_direction: 'INCREASING', unavailable_reason: null, calculation_version: 'v1' },
    ],
    patterns: [
      { pattern_key: 'p1', scope: 'site', site_id: 's1', site_label: 'North Yard', event_type: 'NEAR_MISS', event_subtype: null, count: 5, first_seen: '2026-01-01T00:00:00Z', last_seen: '2026-05-01T00:00:00Z', window_start: '2026-01-01T00:00:00Z', window_end: '2026-06-01T00:00:00Z', window_days: 90, supporting_event_ids: [], classification: 'RECURRING', calculation_version: 'v1' },
    ],
    concentrations: [],
    anomalies: [
      { metric: 'vehicle_incidents', label: 'Vehicle incidents', status: 'ANOMALOUS', direction: 'ABOVE_BASELINE', current_value: 8, baseline_mean: 3, baseline_stdev: 1, z_score: 3.2, baseline_period_count: 6, current_period_start: '2026-05-01T00:00:00Z', current_period_end: '2026-06-01T00:00:00Z', window_days: 30, supporting_event_count: 8, baseline_window_start: null, baseline_window_end: null, supporting_event_ids: [], calculation_version: 'v1' },
    ],
    associations: [
      { metric_a: 'near_misses', metric_b: 'observations', label_a: 'Near misses', label_b: 'Observations', classification: 'MODERATE_POSITIVE', correlation_coefficient: 0.55, period_count: 6, period_start: null, period_end: null, window_days: 90, values_a: [], values_b: [], supporting_event_ids: [], calculation_version: 'v1' },
    ],
    explanations: [],
    provenance: { organization_id: 'org-1', scope: 'organization', entity_id: null, as_of: '2026-06-01T00:00:00Z', window_start: '2026-03-01T00:00:00Z', window_end: '2026-06-01T00:00:00Z', window_days: 90, generated_at: '2026-06-01T00:05:00Z', event_count: 40, evidence_sample_event_ids: [], total_supporting_events: 40, calculation_versions: {} },
    actions_context: { open_action_count: 4, overdue_action_count: 1, high_priority_action_count: 2 },
    ...overrides,
  };
}

describe('IntelligencePage', () => {
  it('shows a loading state, then renders the risk score and classification', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('Loading intelligence data…');

    await waitFor(() => expect(screen.getByText('61.2')).toBeInTheDocument());
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('renders anomalies on the Anomalies tab, in plain HSE language (never "AI detected")', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
    renderPage();

    await waitFor(() => expect(screen.getByRole('tab', { name: 'Anomalies' })).toBeInTheDocument());
    await userEvent.click(screen.getByRole('tab', { name: 'Anomalies' }));

    expect(screen.getByText('Vehicle incidents')).toBeInTheDocument();
    expect(screen.getByText(/Above baseline/)).toBeInTheDocument();
    expect(screen.queryByText(/AI detected/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/AI prediction/i)).not.toBeInTheDocument();
  });

  it('renders recurring patterns on the Patterns tab', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
    renderPage();

    await waitFor(() => expect(screen.getByRole('tab', { name: 'Patterns' })).toBeInTheDocument());
    await userEvent.click(screen.getByRole('tab', { name: 'Patterns' }));

    expect(screen.getByText(/North Yard/)).toBeInTheDocument();
    expect(screen.getByText('Recurring pattern')).toBeInTheDocument();
  });

  it('renders associations on the Associations tab, phrased as association not causation', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
    renderPage();

    await waitFor(() => expect(screen.getByRole('tab', { name: 'Associations' })).toBeInTheDocument());
    await userEvent.click(screen.getByRole('tab', { name: 'Associations' }));

    expect(screen.getByText(/Near misses & Observations/)).toBeInTheDocument();
    expect(screen.getByText('Moderate positive association')).toBeInTheDocument();
    expect(screen.queryByText(/causes/i)).not.toBeInTheDocument();
  });

  it('handles the insufficient-data state honestly rather than hiding it', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(
      baseIntelligence({ data_sufficiency: { status: 'INSUFFICIENT_DATA', event_count: 2 } }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText(/Insufficient data for a reliable enterprise picture/)).toBeInTheDocument());
  });

  it('shows a calm access-denied state on a 403, not a scary generic error', async () => {
    vi.mocked(getEnterpriseIntelligence).mockRejectedValue(
      new ApiError('Missing intelligence:read permission in the requested organization.', { status: 403 }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("You don't have permission to view this")).toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows an error state with retry on a genuine failure', async () => {
    vi.mocked(getEnterpriseIntelligence).mockRejectedValueOnce(new ApiError('Could not reach the SIE API.', { status: 0 }));
    renderPage();

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.'));

    vi.mocked(getEnterpriseIntelligence).mockResolvedValueOnce(baseIntelligence());
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByText('61.2')).toBeInTheDocument());
  });

  it('shows the no-organization empty state when no identity is resolved', () => {
    render(
      <AuthProviderStub>
        <MemoryRouter>
          <IntelligencePage />
        </MemoryRouter>
      </AuthProviderStub>,
    );
    expect(screen.getByText('No organization context available')).toBeInTheDocument();
  });

  it('shows empty states for each tab when a section has no data', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(
      baseIntelligence({ anomalies: [], patterns: [], associations: [], indicators: [] }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText('No indicators available')).toBeInTheDocument());
  });
});
