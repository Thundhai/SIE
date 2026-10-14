import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { IntelligencePage } from './IntelligencePage';

vi.mock('../../services/api/intelligence', () => ({
  getEnterpriseIntelligence: vi.fn(),
}));
vi.mock('../../services/api/attention', () => ({
  getAttention: vi.fn(),
  getSiteAttention: vi.fn(),
}));
vi.mock('../../services/api/sites', () => ({
  listSites: vi.fn(),
}));

import { getEnterpriseIntelligence } from '../../services/api/intelligence';
import { getAttention, getSiteAttention, type AttentionItem, type AttentionResult } from '../../services/api/attention';
import { listSites } from '../../services/api/sites';

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

/** Finds a `role="status"` element by its exact announced text, among
 * possibly several simultaneous loading regions on the page — a bare
 * `getByRole('status')` is ambiguous once more than one lane is loading
 * at once, so every loading-state assertion below goes through this
 * instead of relying on there being exactly one match. */
function getStatusRegionByText(text: string): HTMLElement {
  const region = screen.getAllByRole('status').find((element) => element.textContent === text);
  if (!region) {
    throw new Error(`No role="status" region found with text: "${text}"`);
  }
  return region;
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

/** Matches the real `AttentionItemDTO` shape (`sie_contract.attention`)
 * exactly, including its nested `AsOfWindow` and `EvidenceReference[]` —
 * not the frontend's own earlier, incorrect flattened/fabricated shape.
 * There is deliberately no `site_label` override point here: the DTO
 * carries no such field, and `IntelligencePage`/`AttentionList` resolve
 * a display name from the fetched site list by `site_id` instead. */
function makeAttentionItem(overrides: Partial<AttentionItem> = {}): AttentionItem {
  return {
    category: 'SIGNIFICANT_ANOMALY',
    priority: 'HIGH',
    title: 'Vehicle incidents above baseline',
    explanation: 'Vehicle incidents this period are above the recent baseline.',
    scope: 'organization',
    site_id: null,
    as_of: { as_of: '2026-06-01T00:00:00Z', generated_at: '2026-06-01T00:05:00Z', window_days: 90 },
    evidence: [{ evidence_type: 'safety_event', reference_id: 'evt-1', label: null }],
    limitation: null,
    reference: 'ref-anomaly-vehicle-incidents',
    ...overrides,
  };
}

function makeAttentionResult(items: AttentionItem[] = [makeAttentionItem()]): AttentionResult {
  return {
    scope: 'organization',
    organization_id: 'org-1',
    entity_id: null,
    as_of: { as_of: '2026-06-01T00:00:00Z', generated_at: '2026-06-01T00:05:00Z', window_days: 90 },
    items,
    category_status: [],
  };
}

describe('IntelligencePage', () => {
  beforeEach(() => {
    vi.mocked(listSites).mockResolvedValue([]);
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
  });

  it('shows a loading state, then renders the risk score and classification', async () => {
    vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
    renderPage();
    expect(getStatusRegionByText('Loading intelligence data…')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText('61.2')).toBeInTheDocument());
    // Scoped to the risk-classification card specifically: the default
    // Attention mock also resolves with a HIGH-priority item, so an
    // unscoped `getByText('High')` would be ambiguous between the two
    // independent, simultaneously-rendered sections.
    const riskClassificationCard = screen.getByText('Risk classification').parentElement as HTMLElement;
    expect(within(riskClassificationCard).getByText('High')).toBeInTheDocument();
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

  // --- Attention (SIE Milestone 33, attention-only delivery) -------------------------------------
  // `GET /intelligence/attention` is the one endpoint actually wired to
  // the Commercial Core HTTP boundary on this deployment — unlike
  // decisions/outcomes/verification/organizational-memory/context,
  // which still return HTTP 501 (see PUBLIC_ARCHITECTURE_BOUNDARY.md /
  // M43-IP-03). This section is deliberately read-only: no decision
  // recording, no "Review" action, nothing that implies an unsupported
  // capability works.

  describe('Attention', () => {
    it('shows a loading state — distinct from the simultaneous Enterprise Intelligence loading region — then renders items in the exact order the backend returned (never re-sorted)', async () => {
      vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
      const items = [
        makeAttentionItem({ reference: 'ref-1', title: 'Critical item', priority: 'CRITICAL' }),
        makeAttentionItem({ reference: 'ref-2', title: 'Low item', priority: 'LOW' }),
        makeAttentionItem({ reference: 'ref-3', title: 'High item', priority: 'HIGH' }),
      ];
      vi.mocked(getAttention).mockResolvedValue(makeAttentionResult(items));
      renderPage();

      expect(getStatusRegionByText('Loading attention…')).toBeInTheDocument();
      expect(getStatusRegionByText('Loading intelligence data…')).toBeInTheDocument();
      await waitFor(() => expect(screen.getByText('Critical item')).toBeInTheDocument());
      const titles = screen.getAllByText(/Critical item|Low item|High item/).map((el) => el.textContent);
      expect(titles).toEqual(['Critical item', 'Low item', 'High item']);
    });

    it('renders category, priority, and explanation in plain language, resolving the site name from the fetched site list by site_id', async () => {
      vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
      vi.mocked(listSites).mockResolvedValue([{ id: 'site-1', name: 'North Yard', location: null, country: null, status: 'ACTIVE', organization_id: 'org-1' }]);
      vi.mocked(getAttention).mockResolvedValue(
        makeAttentionResult([makeAttentionItem({ category: 'RECURRING_PATTERN', scope: 'site', site_id: 'site-1' })]),
      );
      renderPage();

      await waitFor(() => expect(screen.getByText(/Recurring pattern/)).toBeInTheDocument());
      // Scoped to the attention item itself: the site name also appears
      // as an <option> in the scope selector rendered from the same
      // fetched site list, and `role="listitem"` alone is ambiguous with
      // the Indicators panel's own <li> list, either of which an
      // unscoped query would also match.
      const attentionItem = screen.getByText('Vehicle incidents above baseline').closest('li') as HTMLElement;
      expect(within(attentionItem).getByText(/North Yard/)).toBeInTheDocument();
      expect(within(attentionItem).getByText('High')).toBeInTheDocument();
      expect(within(attentionItem).queryByText('HIGH')).not.toBeInTheDocument();
    });

    it('shows an honest empty state when there are no attention items', async () => {
      vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
      vi.mocked(getAttention).mockResolvedValue(makeAttentionResult([]));
      renderPage();

      await waitFor(() => expect(screen.getByText('Nothing needs attention right now')).toBeInTheDocument());
    });

    it('shows an error state with a working retry on a genuine failure, independent of the enterprise-intelligence lane', async () => {
      vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
      vi.mocked(getAttention).mockRejectedValueOnce(new ApiError('Could not reach the SIE API.', { status: 0 }));
      renderPage();

      await waitFor(() => expect(screen.getByText('Could not reach the SIE API.')).toBeInTheDocument());
      // The enterprise-intelligence lane still renders successfully — one
      // lane's failure never blanks the other.
      await waitFor(() => expect(screen.getByText('61.2')).toBeInTheDocument());

      vi.mocked(getAttention).mockResolvedValueOnce(makeAttentionResult());
      await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
      await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    });

    it('shows an error state for enterprise intelligence without blanking a successfully-loaded Attention list (independent lanes)', async () => {
      vi.mocked(getEnterpriseIntelligence).mockRejectedValue(new ApiError('Could not reach the SIE API.', { status: 0 }));
      vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
      renderPage();

      await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
      expect(screen.getByText('Could not reach the SIE API.')).toBeInTheDocument();
    });

    it('switches to a site scope and calls the site-scoped attention endpoint, preserving organization/site scoping', async () => {
      vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
      vi.mocked(listSites).mockResolvedValue([{ id: 'site-1', name: 'North Yard', location: null, country: null, status: 'ACTIVE', organization_id: 'org-1' }]);
      vi.mocked(getSiteAttention).mockResolvedValue(makeAttentionResult([]));
      renderPage();

      await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
      await userEvent.selectOptions(screen.getByLabelText('Scope'), 'site-1');

      await waitFor(() =>
        expect(getSiteAttention).toHaveBeenCalledWith(
          expect.objectContaining({ organizationId: 'org-1', siteId: 'site-1' }),
          expect.anything(),
        ),
      );
    });

    it('never offers a "Review" or decision-recording control (decisions are not available on this deployment)', async () => {
      vi.mocked(getEnterpriseIntelligence).mockResolvedValue(baseIntelligence());
      vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
      renderPage();

      await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
      expect(screen.queryByRole('button', { name: /review/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/decision/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/last decision/i)).not.toBeInTheDocument();
    });
  });
});
