import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { ReportsPage } from './ReportsPage';

vi.mock('../../services/api/intelligence', () => ({
  getEnterpriseIntelligence: vi.fn(),
}));
vi.mock('../../services/api/analytics', () => ({
  getAnalyticsSummary: vi.fn(),
}));
vi.mock('../../services/api/events', () => ({
  listEvents: vi.fn(),
}));
vi.mock('../../services/api/actions', () => ({
  listActions: vi.fn(),
}));

import { getAnalyticsSummary } from '../../services/api/analytics';
import { listActions } from '../../services/api/actions';
import { listEvents } from '../../services/api/events';
import { getEnterpriseIntelligence } from '../../services/api/intelligence';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderReports() {
  return render(
    <AuthProviderStub value={{ isAuthenticated: true, organization: ORGANIZATION }}>
      <ReportsPage />
    </AuthProviderStub>,
  );
}

const INTELLIGENCE = {
  scope: 'organization',
  organization_id: 'org-1',
  entity_id: null,
  as_of: '2026-06-01T00:00:00Z',
  window_days: 30,
  data_sufficiency: { status: 'SUFFICIENT_DATA', event_count: 40 },
  deterministic_risk: {
    score: 42.5,
    classification: 'MODERATE',
    version: 'risk-score-v1',
    components: [
      { key: 'incident_frequency', label: 'Incident frequency', raw_score: 60, weight: 1, normalized_weight: 50, contribution: 30 },
    ],
    insufficient_data_reason: null,
  },
  trend: {
    classification: 'DETERIORATING',
    metric: 'incident_count',
    current_value: 5,
    previous_value: 2,
    absolute_change: 3,
    percentage_change: 150,
    current_period_start: '2026-05-02T00:00:00Z',
    current_period_end: '2026-06-01T00:00:00Z',
    previous_period_start: '2026-04-02T00:00:00Z',
    previous_period_end: '2026-05-02T00:00:00Z',
    calculation_version: 'enterprise-trend-v1',
  },
  indicators: [
    { key: 'incident_count', label: 'Incident Count', value: 5, category: 'LAGGING', period_start: '2026-05-02T00:00:00Z', period_end: '2026-06-01T00:00:00Z', window_days: 30, previous_value: 2, absolute_change: 3, percentage_change: 150, trend_direction: 'INCREASING', unavailable_reason: null, calculation_version: 'enterprise-indicator-v1' },
    { key: 'near_miss_count', label: 'Near Misses', value: 8, category: 'LEADING', period_start: '2026-05-02T00:00:00Z', period_end: '2026-06-01T00:00:00Z', window_days: 30, previous_value: 6, absolute_change: 2, percentage_change: 33.33, trend_direction: 'INCREASING', unavailable_reason: null, calculation_version: 'enterprise-indicator-v1' },
  ],
  patterns: [
    { pattern_key: 'p1', scope: 'site', site_id: 's1', site_label: 'North Yard', event_type: 'NEAR_MISS', event_subtype: null, count: 5, first_seen: '2026-01-01T00:00:00Z', last_seen: '2026-05-01T00:00:00Z', window_start: '2026-01-01T00:00:00Z', window_end: '2026-06-01T00:00:00Z', window_days: 30, supporting_event_ids: [], classification: 'RECURRING', calculation_version: 'v1' },
  ],
  concentrations: [
    { dimension: 'site', key: 's1', label: 'North Yard', count: 6, total: 10, percentage: 60, classification: 'HIGH', calculation_version: 'concentration-v1' },
  ],
  anomalies: [
    { metric: 'vehicle_incidents', label: 'Vehicle Incidents', status: 'ANOMALOUS', direction: 'ABOVE_BASELINE', current_value: 8, baseline_mean: 3, baseline_stdev: 1, z_score: 3.2, baseline_period_count: 6, current_period_start: '2026-05-01T00:00:00Z', current_period_end: '2026-06-01T00:00:00Z', window_days: 30, supporting_event_count: 8, baseline_window_start: null, baseline_window_end: null, supporting_event_ids: [], calculation_version: 'v1' },
    { metric: 'near_miss_count', label: 'Near Misses', status: 'NORMAL', direction: 'NONE', current_value: 8, baseline_mean: 7, baseline_stdev: 1, z_score: 0.5, baseline_period_count: 6, current_period_start: '2026-05-01T00:00:00Z', current_period_end: '2026-06-01T00:00:00Z', window_days: 30, supporting_event_count: 8, baseline_window_start: null, baseline_window_end: null, supporting_event_ids: [], calculation_version: 'v1' },
  ],
  associations: [
    { metric_a: 'near_misses', metric_b: 'observations', label_a: 'Near misses', label_b: 'Observations', classification: 'MODERATE_POSITIVE', correlation_coefficient: 0.55, period_count: 6, period_start: null, period_end: null, window_days: 30, values_a: [], values_b: [], supporting_event_ids: [], calculation_version: 'v1' },
  ],
  explanations: [
    { code: 'INCIDENT_FREQUENCY', message: '5 incident(s) were recorded in the current period.', value: 5, baseline: 2, contribution: 30, evidence_reference: 'indicator:frequency' },
  ],
  provenance: {
    organization_id: 'org-1',
    scope: 'organization',
    entity_id: null,
    as_of: '2026-06-01T00:00:00Z',
    window_start: '2026-05-02T00:00:00Z',
    window_end: '2026-06-01T00:00:00Z',
    window_days: 30,
    generated_at: '2026-06-01T00:05:00Z',
    event_count: 40,
    evidence_sample_event_ids: [],
    total_supporting_events: 40,
    calculation_versions: { risk_score: 'risk-score-v1', enterprise_trend: 'enterprise-trend-v1' },
  },
  actions_context: { open_action_count: 4, overdue_action_count: 1, high_priority_action_count: 2 },
};

const ANALYTICS = {
  organization_id: 'org-1',
  entity_type: 'ORGANIZATION',
  entity_id: null,
  as_of: '2026-06-01T00:00:00Z',
  window_days: 30,
  event_count: 12,
  data_sufficiency: 'SUFFICIENT_DATA',
  features: {},
  indicators: [],
  signals: [
    { signal_type: 'OVERDUE_ACTION_SURGE', severity: 'HIGH', observed_period_start: '2026-05-01T00:00:00Z', observed_period_end: '2026-06-01T00:00:00Z', entity_type: 'organization', entity_id: null, supporting_features: {}, supporting_event_ids: [], data_quality: 'SUFFICIENT_DATA', calculation_version: 'v1' },
  ],
  source_reliability: [
    { source_system: 'Manual Entry', record_count: 40, valid_count: 38, partial_count: 1, invalid_count: 1, quarantined_count: 0, latest_event_time: '2026-06-01T00:00:00Z', latest_ingestion_time: '2026-06-01T00:05:00Z', is_stale: false, freshness_threshold_days: 7 },
  ],
};

const ONE_EVENT = {
  id: 'evt-1',
  event_time: '2026-06-01T00:00:00Z',
  event_type: 'NEAR_MISS',
  event_subtype: null,
  site_id: 'site-1',
  site_name: 'North Yard',
  status: 'open',
  severity: 'LOW',
  source_system: 'Manual Entry',
  source_record_id: 'rec-1',
  data_quality_status: 'VALID',
};

const ACTIONS = {
  items: [
    { id: 'act-1', organization_id: 'org-1', site_id: null, site_name: null, source_event_id: null, title: 'Fix guardrail', description: null, action_type: 'CORRECTIVE', priority: 'HIGH', status: 'OPEN', owner_user_id: null, owner_name: 'J. Smith', due_date: '2026-06-10T00:00:00Z', created_by_user_id: null, created_by_api_client_id: null, created_at: '2026-05-01T00:00:00Z', updated_at: '2026-05-01T00:00:00Z', completed_at: null, cancelled_at: null, external_reference: null, attributes: {} },
    { id: 'act-2', organization_id: 'org-1', site_id: null, site_name: null, source_event_id: null, title: 'Archived item', description: null, action_type: 'PREVENTIVE', priority: 'LOW', status: 'COMPLETED', owner_user_id: null, owner_name: null, due_date: null, created_by_user_id: null, created_by_api_client_id: null, created_at: '2026-04-01T00:00:00Z', updated_at: '2026-04-01T00:00:00Z', completed_at: '2026-04-05T00:00:00Z', cancelled_at: null, external_reference: null, attributes: {} },
  ],
  total: 2,
  page: 1,
  page_size: 100,
};

describe('ReportsPage', () => {
  it('shows the executive summary and reporting period from backend values only', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE as never);
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS as never);
    vi.mocked(listEvents).mockResolvedValue({ items: [ONE_EVENT], total: 1, page: 1, page_size: 100 } as never);
    vi.mocked(listActions).mockResolvedValue(ACTIONS as never);

    renderReports();

    await waitFor(() => expect(screen.getByText('42.5')).toBeInTheDocument());
    expect(screen.getByText('May 2, 2026 – Jun 1, 2026')).toBeInTheDocument();
    expect(screen.getByText('Apr 2, 2026 – May 2, 2026')).toBeInTheDocument();
    expect(screen.getByText('5 incident(s) were recorded in the current period.')).toBeInTheDocument();
    expect(screen.getByText(/Evidence: indicator:frequency/)).toBeInTheDocument();
  });

  it('shows the risk profile component breakdown exactly as returned, with no frontend arithmetic', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE as never);
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS as never);
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);
    vi.mocked(listActions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);

    renderReports();

    await waitFor(() => expect(screen.getByText('Incident frequency')).toBeInTheDocument());
    expect(screen.getByText('60.0 / 100')).toBeInTheDocument();
    expect(screen.getByText('50.0%')).toBeInTheDocument();
    expect(screen.getByText('30.0 pts')).toBeInTheDocument();
  });

  it('groups indicators into lagging and leading exactly as the backend categorizes them', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE as never);
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS as never);
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);
    vi.mocked(listActions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);

    renderReports();

    await waitFor(() => expect(screen.getByText('Lagging indicators')).toBeInTheDocument());
    expect(screen.getByText('Leading indicators')).toBeInTheDocument();
    expect(screen.getByText('Incident Count')).toBeInTheDocument();
    expect(screen.getByText('Near Misses')).toBeInTheDocument();
  });

  it('shows only open actions in Action status, ranked by priority, and excludes completed/cancelled ones', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE as never);
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS as never);
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);
    vi.mocked(listActions).mockResolvedValue(ACTIONS as never);

    renderReports();

    await waitFor(() => expect(screen.getByText('Fix guardrail')).toBeInTheDocument());
    expect(screen.queryByText('Archived item')).not.toBeInTheDocument();
  });

  it('shows intelligence signals, patterns, concentrations, and associations from real backend fields previously unused by this page', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE as never);
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS as never);
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);
    vi.mocked(listActions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);

    renderReports();

    await waitFor(() => expect(screen.getByText('A surge in overdue corrective actions was detected.')).toBeInTheDocument());
    expect(screen.getByText('North Yard')).toBeInTheDocument();
    expect(screen.getByText(/60.0%/)).toBeInTheDocument();
    expect(screen.getByText('Near misses & Observations')).toBeInTheDocument();
    expect(screen.getByText('Moderate positive association')).toBeInTheDocument();
  });

  it('shows only ANOMALOUS anomalies, and shows data-quality source reliability', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE as never);
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS as never);
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);
    vi.mocked(listActions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);

    renderReports();

    await waitFor(() => expect(screen.getByText(/Current value 8, baseline average 3\.0/)).toBeInTheDocument());
    expect(screen.queryByText(/Current value 8, baseline average 7\.0/)).not.toBeInTheDocument();
    expect(screen.getByText('Manual Entry')).toBeInTheDocument();
  });

  it('shows report provenance including calculation source versions', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE as never);
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS as never);
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);
    vi.mocked(listActions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);

    renderReports();

    await waitFor(() => expect(screen.getByText('Risk score', { selector: 'span' })).toBeInTheDocument());
    expect(screen.getByText('Enterprise trend', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getAllByText(/risk-score-v1/).length).toBeGreaterThan(0);
    expect(screen.getByText(/enterprise-trend-v1/)).toBeInTheDocument();
  });

  it('shows a permission-denied message on a 403 rather than an empty report', async () => {
    vi.mocked(getEnterpriseIntelligence).mockRejectedValue(new ApiError('Missing intelligence:read permission', { status: 403 }));
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS as never);
    vi.mocked(listEvents).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);
    vi.mocked(listActions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as never);

    renderReports();

    await waitFor(() => expect(screen.getByText("You don't have permission to view this report")).toBeInTheDocument());
  });
});
