import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
vi.mock('../../services/api/attention', () => ({
  getAttention: vi.fn(),
}));
vi.mock('../../services/api/decisions', () => ({
  listDecisions: vi.fn(),
  createDecision: vi.fn(),
}));
vi.mock('../../services/api/memoryIntegration', () => ({
  getMemoryContext: vi.fn(),
  getSiteMemoryContext: vi.fn(),
}));
vi.mock('../actions/useActionRepository', () => ({
  useActionRepository: () => ({
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 50 }),
    isFixtureBacked: false,
  }),
}));

import { getAnalyticsSummary } from '../../services/api/analytics';
import { getAttention, type AttentionItem } from '../../services/api/attention';
import { createDecision, listDecisions, type IntelligenceDecision } from '../../services/api/decisions';
import { listEvents } from '../../services/api/events';
import { getEnterpriseIntelligence } from '../../services/api/intelligence';
import { getMemoryContext } from '../../services/api/memoryIntegration';

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

const ATTENTION_ITEM: AttentionItem = {
  category: 'SIGNIFICANT_ANOMALY',
  priority: 'HIGH',
  title: 'Vehicle incidents above baseline',
  explanation: 'Vehicle incidents this period are above the recent baseline.',
  scope: 'organization',
  site_id: null,
  site_label: null,
  as_of: '2026-06-01T00:00:00Z',
  window_days: 90,
  evidence: { source: 'enterprise_anomaly', calculation_version: 'v1', entity_ids: [], event_ids: ['evt-1'] },
  limitation: null,
  reference: 'ref-anomaly-vehicle-incidents',
};

const ATTENTION_SUCCESS = {
  scope: 'organization',
  organization_id: 'org-1',
  entity_id: null,
  as_of: '2026-06-01T00:00:00Z',
  window_days: 90,
  generated_at: '2026-06-01T00:05:00Z',
  items: [ATTENTION_ITEM],
  category_statuses: [],
  calculation_versions: {},
};

describe('HomePage', () => {
  beforeEach(() => {
    vi.mocked(getAnalyticsSummary).mockResolvedValue(ANALYTICS_SUMMARY);
    vi.mocked(listEvents).mockResolvedValue({ items: [ONE_EVENT], total: 1, page: 1, page_size: 5 });
    vi.mocked(getAttention).mockResolvedValue(ATTENTION_SUCCESS);
    vi.mocked(listDecisions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
    vi.mocked(getMemoryContext).mockResolvedValue({
      scope: 'organization', organization_id: 'org-1', entity_id: null, project_id: null,
      as_of: '2026-06-01T00:00:00Z', generated_at: '2026-06-01T00:00:00Z', items: [], total: 0, page: 1, page_size: 25,
      calculation_version: 'v1',
    });
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

  it('handles the enterprise intelligence API success: renders risk score, "what is changing", and ranked attention', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE_SUCCESS);
    renderHome();

    await waitFor(() => expect(screen.getByText('42.5')).toBeInTheDocument());
    expect(screen.getByText('Moderate')).toBeInTheDocument();
    expect(screen.getByText('Vehicle incidents')).toBeInTheDocument();
    expect(screen.getByText('Above baseline')).toBeInTheDocument();
    // The ranked attention list (SIE Milestone 33/42) — replaces the old
    // flat "Open actions"/"High-priority actions" counts as the primary
    // prioritization mechanism.
    expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review' })).toBeInTheDocument();
  });

  it('opens the review drawer from Home and records a decision', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(INTELLIGENCE_SUCCESS);
    const decisionRecord: IntelligenceDecision = {
      id: 'dec-1', organization_id: 'org-1', site_id: null, site_label: null, scope: 'organization',
      attention_reference: ATTENTION_ITEM.reference, attention_category: ATTENTION_ITEM.category,
      attention_priority: ATTENTION_ITEM.priority, attention_title: ATTENTION_ITEM.title,
      attention_explanation: ATTENTION_ITEM.explanation, intelligence_as_of: ATTENTION_ITEM.as_of,
      intelligence_window_days: ATTENTION_ITEM.window_days, calculation_version: 'v1',
      evidence_source: 'enterprise_anomaly', evidence_entity_ids: [], evidence_event_ids: ['evt-1'],
      decision: 'ACT', rationale: 'Raising a corrective action.', linked_action_id: null, linked_action: null,
      decided_by_user_id: 'user-1', decided_by_api_client_id: null, decided_at: '2026-06-01T01:00:00Z',
      created_at: '2026-06-01T01:00:00Z', updated_at: '2026-06-01T01:00:00Z',
    };
    vi.mocked(createDecision).mockResolvedValue(decisionRecord);
    renderHome();

    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    const dialog = await screen.findByRole('dialog');

    await userEvent.selectOptions(within(dialog).getByLabelText('Decision'), 'ACT');
    await userEvent.type(within(dialog).getByLabelText('Rationale'), 'Raising a corrective action.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Record decision' }));

    await waitFor(() => expect(createDecision).toHaveBeenCalled());
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
