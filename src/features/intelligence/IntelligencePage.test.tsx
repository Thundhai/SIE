import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { IntelligencePage } from './IntelligencePage';

vi.mock('../../services/api/attention', () => ({
  getAttention: vi.fn(),
  getSiteAttention: vi.fn(),
}));
vi.mock('../../services/api/fieldIntelligenceContext', () => ({
  getFieldIntelligenceContext: vi.fn(),
  getSiteFieldIntelligenceContext: vi.fn(),
}));
vi.mock('../../services/api/decisions', () => ({
  listDecisions: vi.fn(),
  createDecision: vi.fn(),
}));
vi.mock('../../services/api/memoryIntegration', () => ({
  getMemoryContext: vi.fn(),
  getSiteMemoryContext: vi.fn(),
}));
vi.mock('../../services/api/sites', () => ({
  listSites: vi.fn(),
}));
vi.mock('../actions/useActionRepository', () => ({
  useActionRepository: () => ({
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 50 }),
    isFixtureBacked: false,
  }),
}));

import { getAttention, getSiteAttention, type AttentionItem, type AttentionResult } from '../../services/api/attention';
import { createDecision, listDecisions, type IntelligenceDecision } from '../../services/api/decisions';
import {
  getFieldIntelligenceContext,
  getSiteFieldIntelligenceContext,
  type FieldIntelligenceContext,
} from '../../services/api/fieldIntelligenceContext';
import { getMemoryContext, type IntegratedMemory } from '../../services/api/memoryIntegration';
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

function makeAttentionItem(overrides: Partial<AttentionItem> = {}): AttentionItem {
  return {
    category: 'SIGNIFICANT_ANOMALY',
    priority: 'HIGH',
    title: 'Vehicle incidents above baseline',
    explanation: 'Vehicle incidents this period are above the recent baseline.',
    scope: 'organization',
    site_id: null,
    site_label: null,
    as_of: '2026-06-01T00:00:00Z',
    window_days: 90,
    evidence: { source: 'enterprise_anomaly', calculation_version: 'v1', entity_ids: [], event_ids: ['evt-1', 'evt-2'] },
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
    as_of: '2026-06-01T00:00:00Z',
    window_days: 90,
    generated_at: '2026-06-01T00:05:00Z',
    items,
    category_statuses: [],
    calculation_versions: {},
  };
}

function makeEnterpriseIntelligence(overrides: Partial<FieldIntelligenceContext['deterministic']> = {}): FieldIntelligenceContext['deterministic'] {
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
    indicators: [],
    patterns: [],
    concentrations: [],
    anomalies: [],
    associations: [],
    explanations: [],
    provenance: { organization_id: 'org-1', scope: 'organization', entity_id: null, as_of: '2026-06-01T00:00:00Z', window_start: '2026-03-01T00:00:00Z', window_end: '2026-06-01T00:00:00Z', window_days: 90, generated_at: '2026-06-01T00:05:00Z', event_count: 40, evidence_sample_event_ids: [], total_supporting_events: 40, calculation_versions: {} },
    actions_context: { open_action_count: 4, overdue_action_count: 1, high_priority_action_count: 2 },
    ...overrides,
  };
}

function makeContext(overrides: Partial<FieldIntelligenceContext> = {}): FieldIntelligenceContext {
  return {
    scope: 'organization',
    organization_id: 'org-1',
    entity_id: null,
    as_of: '2026-06-01T00:00:00Z',
    window_days: 90,
    generated_at: '2026-06-01T00:05:00Z',
    observed: {
      outcome: 'OK',
      unavailable_reason: null,
      event_count: 40,
      evidence_sample_event_ids: [],
      open_finding_count: 2,
      open_finding_sample: [],
      open_finding_control_count: 0,
      actions: { open_action_count: 4, overdue_action_count: 1, high_priority_action_count: 2 },
      open_action_sample: [],
    },
    deterministic: makeEnterpriseIntelligence(),
    predictive: { outcome: 'NOT_AVAILABLE', value: null },
    knowledge: { outcome: 'NOT_QUERIED', unavailable_reason: null, query: null, results: [], result_count: 0 },
    organizational_memory: { outcome: 'OK', unavailable_reason: null, items: [], calculation_version: 'v1' },
    calculation_versions: {},
    operational_scope: null,
    ...overrides,
  };
}

function makeMemory(overrides: Partial<IntegratedMemory> = {}): IntegratedMemory {
  return {
    memory_id: 'mem-1',
    memory_type: 'LESSON_LEARNED',
    title: 'Permit checks should precede coordination meetings',
    memory_content: 'Repeated permit deviations indicate permit verification should occur earlier.',
    rationale: 'Recurred across multiple accepted candidates.',
    memory_created_at: '2026-01-01T00:00:00Z',
    learning_candidate_id: 'cand-1',
    outcome_id: 'out-1',
    verification_id: 'ver-1',
    outcome_site_id: null,
    applicability_basis: 'ORGANIZATION_WIDE',
    governance_status: 'ACTIVE',
    governance_is_explicit: false,
    governance_decided_at: null,
    ...overrides,
  };
}

function makeDecision(overrides: Partial<IntelligenceDecision> = {}): IntelligenceDecision {
  return {
    id: 'dec-1',
    organization_id: 'org-1',
    site_id: null,
    site_label: null,
    scope: 'organization',
    attention_reference: 'ref-anomaly-vehicle-incidents',
    attention_category: 'SIGNIFICANT_ANOMALY',
    attention_priority: 'HIGH',
    attention_title: 'Vehicle incidents above baseline',
    attention_explanation: 'Vehicle incidents this period are above the recent baseline.',
    intelligence_as_of: '2026-06-01T00:00:00Z',
    intelligence_window_days: 90,
    calculation_version: 'v1',
    evidence_source: 'enterprise_anomaly',
    evidence_entity_ids: [],
    evidence_event_ids: ['evt-1', 'evt-2'],
    decision: 'ACT',
    rationale: 'Raising a corrective action.',
    linked_action_id: null,
    linked_action: null,
    decided_by_user_id: 'user-1',
    decided_by_api_client_id: null,
    decided_at: '2026-06-01T01:00:00Z',
    created_at: '2026-06-01T01:00:00Z',
    updated_at: '2026-06-01T01:00:00Z',
    ...overrides,
  };
}

describe('IntelligencePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listSites).mockResolvedValue([]);
    vi.mocked(listDecisions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
    vi.mocked(getMemoryContext).mockResolvedValue({
      scope: 'organization', organization_id: 'org-1', entity_id: null, project_id: null,
      as_of: '2026-06-01T00:00:00Z', generated_at: '2026-06-01T00:00:00Z', items: [], total: 0, page: 1, page_size: 25,
      calculation_version: 'v1',
    });
  });

  // --- 1. Intelligence loading: success / empty / API failure ----------------------------------

  it('shows loading, then renders attention and intelligence context on success', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    expect(screen.getAllByRole('status')[0]).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    expect(screen.getByText('61.2')).toBeInTheDocument();
  });

  it('shows an honest empty state when there are no attention items', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult([]));
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText('Nothing needs attention right now')).toBeInTheDocument());
  });

  it('shows an error state for attention without blanking intelligence context (independent lanes)', async () => {
    vi.mocked(getAttention).mockRejectedValue(new ApiError('Could not reach the SIE API.', { status: 0 }));
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText('Could not reach the SIE API.')).toBeInTheDocument());
    // Intelligence context still renders.
    await waitFor(() => expect(screen.getByText('61.2')).toBeInTheDocument());
  });

  it('shows an error state for intelligence context without blanking attention (independent lanes)', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockRejectedValue(new ApiError('Could not reach the SIE API.', { status: 0 }));
    renderPage();

    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    expect(screen.getByText('Could not reach the SIE API.')).toBeInTheDocument();
  });

  // --- 2. Attention: items load, order preserved, human-readable fields, reference preserved ----

  it('renders attention items in the exact order the backend returned (never re-sorted)', async () => {
    const items = [
      makeAttentionItem({ reference: 'ref-1', title: 'Critical item', priority: 'CRITICAL' }),
      makeAttentionItem({ reference: 'ref-2', title: 'Low item', priority: 'LOW' }),
      makeAttentionItem({ reference: 'ref-3', title: 'High item', priority: 'HIGH' }),
    ];
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult(items));
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText('Critical item')).toBeInTheDocument());
    const titles = screen.getAllByText(/Critical item|Low item|High item/).map((el) => el.textContent);
    expect(titles).toEqual(['Critical item', 'Low item', 'High item']);
  });

  it('renders category, priority, explanation, and site label in plain language', async () => {
    vi.mocked(getAttention).mockResolvedValue(
      makeAttentionResult([makeAttentionItem({ category: 'RECURRING_PATTERN', site_id: 'site-1', site_label: 'North Yard' })]),
    );
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText(/Recurring pattern/)).toBeInTheDocument());
    expect(screen.getByText(/North Yard/)).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();
  });

  // --- 3. Decision: Review -> ACT / DO_NOT_ACT, rationale validation, API failure ----------------

  it('opens the review drawer and preserves the attention reference when recording a decision', async () => {
    const item = makeAttentionItem();
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult([item]));
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    vi.mocked(createDecision).mockResolvedValue(makeDecision());
    renderPage();

    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Reference/)).toBeInTheDocument();
    expect(within(dialog).getByText(item.reference)).toBeInTheDocument();

    await userEvent.selectOptions(within(dialog).getByLabelText('Decision'), 'ACT');
    await userEvent.type(within(dialog).getByLabelText('Rationale'), 'Raising a corrective action.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Record decision' }));

    await waitFor(() =>
      expect(createDecision).toHaveBeenCalledWith(
        expect.objectContaining({
          organizationId: 'org-1',
          input: expect.objectContaining({
            attentionReference: item.reference,
            scope: item.scope,
            asOf: item.as_of,
            windowDays: item.window_days,
            decision: 'ACT',
            rationale: 'Raising a corrective action.',
          }),
        }),
        expect.any(String),
      ),
    );
    await waitFor(() => expect(within(dialog).getByText('recorded.')).toBeInTheDocument());
  });

  it('records a DO_NOT_ACT decision with its own rationale', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    vi.mocked(createDecision).mockResolvedValue(makeDecision({ decision: 'DO_NOT_ACT', rationale: 'Control already verified effective.' }));
    renderPage();

    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    const dialog = await screen.findByRole('dialog');

    await userEvent.selectOptions(within(dialog).getByLabelText('Decision'), 'DO_NOT_ACT');
    await userEvent.type(within(dialog).getByLabelText('Rationale'), 'Control already verified effective.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Record decision' }));

    await waitFor(() =>
      expect(createDecision).toHaveBeenCalledWith(
        expect.objectContaining({ input: expect.objectContaining({ decision: 'DO_NOT_ACT' }) }),
        expect.any(String),
      ),
    );
  });

  it('requires a decision and a rationale before submitting', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    const dialog = await screen.findByRole('dialog');

    await userEvent.click(within(dialog).getByRole('button', { name: 'Record decision' }));
    expect(within(dialog).getByText('Choose a decision.')).toBeInTheDocument();
    expect(createDecision).not.toHaveBeenCalled();

    await userEvent.selectOptions(within(dialog).getByLabelText('Decision'), 'ACT');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Record decision' }));
    expect(within(dialog).getByText('Rationale is required.')).toBeInTheDocument();
    expect(createDecision).not.toHaveBeenCalled();
  });

  it('surfaces a decision submission failure without silently succeeding', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    vi.mocked(createDecision).mockRejectedValue(new ApiError('Could not reach the SIE API.', { status: 0 }));
    renderPage();

    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    const dialog = await screen.findByRole('dialog');

    await userEvent.selectOptions(within(dialog).getByLabelText('Decision'), 'ACT');
    await userEvent.type(within(dialog).getByLabelText('Rationale'), 'Attempting to act.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Record decision' }));

    await waitFor(() => expect(within(dialog).getByText('Could not reach the SIE API.')).toBeInTheDocument());
    expect(within(dialog).queryByText('recorded.')).not.toBeInTheDocument();
  });

  it('shows a previously recorded decision on the attention list', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    vi.mocked(listDecisions).mockResolvedValue({ items: [makeDecision()], total: 1, page: 1, page_size: 100 });
    renderPage();

    await waitFor(() => expect(screen.getByText('Last decision:')).toBeInTheDocument());
    // "Act" appears both on the attention list's own "Last decision" badge
    // and in the separate "Recent decisions" history section below —
    // both are real, independently-fetched renderings of the same
    // decision, not a duplicate-rendering bug.
    expect(screen.getAllByText('Act').length).toBeGreaterThan(0);
  });

  // --- 4. Intelligence categories: truthful, never blurred ---------------------------------------

  it('never claims SIE decided anything — the human-decision framing is explicit', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('SIE signal')).toBeInTheDocument();
    expect(within(dialog).getByText(/SIE surfaced the signal above, it did not decide anything/)).toBeInTheDocument();
  });

  it('shows Predictive as not available at organization scope, honestly, never a fabricated value', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText(/Predictive intelligence is evaluated per site/)).toBeInTheDocument());
  });

  it('shows Knowledge as not queried, honestly, never a fabricated citation', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText('Knowledge and evidence retrieval has not been queried for this view.')).toBeInTheDocument());
  });

  it('renders a returned organizational memory item with its real applicability/provenance, never invented', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(
      makeContext({ organizational_memory: { outcome: 'OK', unavailable_reason: null, items: [makeMemory()], calculation_version: 'v1' } }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText('Permit checks should precede coordination meetings')).toBeInTheDocument());
    expect(screen.getByText('Applies across the organization')).toBeInTheDocument();
  });

  it('shows an honest empty state when no organizational memory applies', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText('No governed organizational memory applies to this scope right now.')).toBeInTheDocument());
  });

  it('never blanks other categories when one category is UNAVAILABLE', async () => {
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(
      makeContext({ observed: { outcome: 'UNAVAILABLE', unavailable_reason: 'Database timeout.', event_count: 0, evidence_sample_event_ids: [], open_finding_count: 0, open_finding_sample: [], open_finding_control_count: 0, actions: null, open_action_sample: [] } }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText('Observed data is unavailable: Database timeout.')).toBeInTheDocument());
    // Deterministic still renders.
    expect(screen.getByText('61.2')).toBeInTheDocument();
  });

  // --- 5. Context: organization/site scope --------------------------------------------------------

  it('switches to site scope and calls the site-scoped attention/context endpoints', async () => {
    vi.mocked(listSites).mockResolvedValue([{ id: 'site-1', name: 'North Yard', location: null, country: null, status: 'ACTIVE', organization_id: 'org-1' }]);
    vi.mocked(getAttention).mockResolvedValue(makeAttentionResult());
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    vi.mocked(getSiteAttention).mockResolvedValue(makeAttentionResult([]));
    vi.mocked(getSiteFieldIntelligenceContext).mockResolvedValue(makeContext({ entity_id: 'site-1', scope: 'site' }));
    renderPage();

    await waitFor(() => expect(screen.getByText('Vehicle incidents above baseline')).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText('Scope'), 'site-1');

    await waitFor(() => expect(getSiteAttention).toHaveBeenCalledWith(expect.objectContaining({ organizationId: 'org-1', siteId: 'site-1' }), expect.anything()));
    expect(getSiteFieldIntelligenceContext).toHaveBeenCalledWith(expect.objectContaining({ organizationId: 'org-1', siteId: 'site-1' }), expect.anything());
  });

  // --- No-organization / permission-denied states -------------------------------------------------

  it('shows the no-organization empty state and makes no attention/context request', () => {
    render(
      <AuthProviderStub>
        <MemoryRouter>
          <IntelligencePage />
        </MemoryRouter>
      </AuthProviderStub>,
    );
    expect(screen.getByText('No organization context available')).toBeInTheDocument();
    expect(getAttention).not.toHaveBeenCalled();
    expect(getFieldIntelligenceContext).not.toHaveBeenCalled();
  });

  it('shows a calm access-denied state on a 403, not a scary generic error', async () => {
    vi.mocked(getAttention).mockRejectedValue(new ApiError('Missing intelligence:read permission in the requested organization.', { status: 403 }));
    vi.mocked(getFieldIntelligenceContext).mockResolvedValue(makeContext());
    renderPage();

    await waitFor(() => expect(screen.getByText("You don't have permission to view this")).toBeInTheDocument());
  });
});
