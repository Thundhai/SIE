import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { HomePage } from './HomePage';

vi.mock('../../services/api/analytics', () => ({
  getAnalyticsSummary: vi.fn(),
}));
vi.mock('../../services/api/intelligence', () => ({
  getEnterpriseIntelligence: vi.fn(),
}));
vi.mock('../../services/api/events', () => ({
  listEvents: vi.fn(),
}));

import { getAnalyticsSummary } from '../../services/api/analytics';
import { listEvents } from '../../services/api/events';
import { getEnterpriseIntelligence } from '../../services/api/intelligence';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderHome() {
  return render(
    <AuthProviderStub value={{ isAuthenticated: true, organization: ORGANIZATION }}>
      <MemoryRouter initialEntries={['/']}>
        <HomePage />
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

const ANALYTICS_SUMMARY = {
  organization_id: 'org-1',
  entity_type: 'ORGANIZATION',
  entity_id: null,
  as_of: '2026-06-01T00:00:00Z',
  window_days: 90,
  event_count: 12,
  data_sufficiency: 'SUFFICIENT_DATA',
  features: {},
  indicators: [],
  signals: [],
  source_reliability: [],
};

const INTELLIGENCE_SUCCESS = {
  scope: 'organization',
  organization_id: 'org-1',
  entity_id: null,
  as_of: '2026-06-01T00:00:00Z',
  window_days: 90,
  data_sufficiency: { status: 'SUFFICIENT_DATA', event_count: 40 },
  deterministic_risk: { score: 42.5, classification: 'MODERATE', version: 'v1', components: [], insufficient_data_reason: null },
  trend: {
    classification: 'STABLE',
    metric: 'total_events',
    current_value: 12,
    previous_value: 10,
    absolute_change: 2,
    percentage_change: 20,
    current_period_start: '2026-05-01T00:00:00Z',
    current_period_end: '2026-06-01T00:00:00Z',
    previous_period_start: '2026-04-01T00:00:00Z',
    previous_period_end: '2026-05-01T00:00:00Z',
    calculation_version: 'v1',
  },
  indicators: [],
  patterns: [{ pattern_key: 'p1', scope: 'site', site_id: 's1', site_label: 'North Yard', event_type: 'NEAR_MISS', event_subtype: null, count: 5, first_seen: '2026-01-01T00:00:00Z', last_seen: '2026-05-01T00:00:00Z', window_start: '2026-01-01T00:00:00Z', window_end: '2026-06-01T00:00:00Z', window_days: 90, supporting_event_ids: [], classification: 'RECURRING', calculation_version: 'v1' }],
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
};

const ONE_EVENT = {
  id: 'evt-1',
  event_time: '2026-06-01T00:00:00Z',
  event_type: 'NEAR_MISS',
  event_subtype: null,
  site_id: 'site-1',
  site_name: 'North Yard',
  status: 'open',
  severity: null,
  source_system: 'SafetyCloud',
  source_record_id: 'REF-1',
  data_quality_status: 'VALID',
};

describe('HomePage', () => {
  beforeEach(() => {
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS_SUMMARY);
    vi.mocked(listEvents).mockResolvedValue({ items: [ONE_EVENT], total: 1, page: 1, page_size: 5 });
  });

  it('renders the Home heading', () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE_SUCCESS);
    renderHome();
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  });

  it('shows the no-organization empty state when no identity is resolved', () => {
    render(
      <AuthProviderStub>
        <MemoryRouter>
          <HomePage />
        </MemoryRouter>
      </AuthProviderStub>,
    );
    expect(screen.getByText('No organization context available')).toBeInTheDocument();
  });

  it('handles the enterprise intelligence API success: renders risk score, "what is changing", and "needs attention"', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE_SUCCESS);
    renderHome();

    await waitFor(() => expect(screen.getByText('42.5')).toBeInTheDocument());
    expect(screen.getByText('Moderate')).toBeInTheDocument();
    expect(screen.getByText('Vehicle incidents')).toBeInTheDocument();
    expect(screen.getByText('Above baseline')).toBeInTheDocument();
    expect(screen.getByText('Open actions')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('High-priority actions')).toBeInTheDocument();
  });

  it('handles the enterprise intelligence API failure without blanking the rest of the page', async () => {
    vi.mocked(getEnterpriseIntelligence).mockRejectedValue(new ApiError('Could not reach the SIE API.', { status: 0 }));
    renderHome();

    await waitFor(() => expect(screen.getAllByRole('alert')[0]).toHaveTextContent('Could not reach the SIE API.'));
    // The independent Recent events / At a glance sections still render.
    await waitFor(() => expect(screen.getByText('Recorded events')).toBeInTheDocument());
  });

  it('renders recent events and navigates to the event on click', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE_SUCCESS);
    renderHome();

    await waitFor(() => expect(screen.getByText('Near miss')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /Near miss/ })).toBeInTheDocument();
  });

  it('shows an empty state when there are no recent events', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE_SUCCESS);
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 5 });
    renderHome();

    await waitFor(() => expect(screen.getByText('No events recorded yet')).toBeInTheDocument());
  });
});
