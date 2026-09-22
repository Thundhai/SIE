import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { ActionDetailPage } from './ActionDetailPage';

vi.mock('../../services/api/actions', () => ({
  getAction: vi.fn(),
  updateActionStatus: vi.fn(),
  updateAction: vi.fn(),
}));
vi.mock('../../services/api/sites', () => ({
  listSites: vi.fn().mockResolvedValue([]),
}));
vi.mock('../../services/api/decisions', () => ({
  listDecisions: vi.fn(),
}));
vi.mock('../../services/api/outcomes', () => ({
  listOutcomes: vi.fn(),
}));

import { getAction, updateAction, updateActionStatus } from '../../services/api/actions';
import { listDecisions, type IntelligenceDecision } from '../../services/api/decisions';
import { listOutcomes, type IntelligenceOutcome } from '../../services/api/outcomes';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderAt(actionId: string, permissions: string[] = []) {
  return render(
    <AuthProviderStub
      value={{
        isAuthenticated: true,
        organization: ORGANIZATION,
        hasPermission: (permission) => permissions.includes(permission),
      }}
    >
      <MemoryRouter initialEntries={[`/actions/${actionId}`]}>
        <Routes>
          <Route path="/actions/:actionId" element={<ActionDetailPage />} />
          <Route path="/events/:eventId" element={<div>Event detail page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

beforeEach(() => {
  vi.mocked(listDecisions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
  vi.mocked(listOutcomes).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
});

function makeDecision(overrides: Partial<IntelligenceDecision> = {}): IntelligenceDecision {
  return {
    id: 'dec-1',
    organization_id: 'org-1',
    site_id: null,
    site_label: null,
    scope: 'organization',
    attention_reference: 'ref-ppe-recurring-pattern',
    attention_category: 'RECURRING_PATTERN',
    attention_priority: 'HIGH',
    attention_title: 'Repeated PPE non-compliance',
    attention_explanation: 'PPE non-compliance recurred across the last three inspections.',
    intelligence_as_of: '2026-06-01T00:00:00Z',
    intelligence_window_days: 90,
    calculation_version: 'v1',
    evidence_source: 'recurrence',
    evidence_entity_ids: [],
    evidence_event_ids: [],
    decision: 'ACT',
    rationale: 'Raising a refresher training intervention.',
    linked_action_id: 'action-1',
    linked_action: { id: 'action-1', title: 'Review reversing procedure', status: 'OPEN' },
    decided_by_user_id: 'user-1',
    decided_by_api_client_id: null,
    decided_at: '2026-06-01T01:00:00Z',
    created_at: '2026-06-01T01:00:00Z',
    updated_at: '2026-06-01T01:00:00Z',
    ...overrides,
  };
}

function makeOutcome(overrides: Partial<IntelligenceOutcome> = {}): IntelligenceOutcome {
  return {
    id: 'outcome-1',
    organization_id: 'org-1',
    decision_id: 'dec-1',
    decision: { id: 'dec-1', attention_reference: 'ref-ppe-recurring-pattern', decision: 'ACT' },
    site_id: null,
    site_label: null,
    linked_action_id: 'action-1',
    linked_action: { id: 'action-1', title: 'Review reversing procedure', status: 'OPEN' },
    classification: 'PARTIALLY_EFFECTIVE',
    summary: 'Some improvement observed, one repeat incident this week.',
    evidence_event_ids: [],
    outcome_at: '2026-06-05T00:00:00Z',
    recorded_by_user_id: 'user-1',
    recorded_by_api_client_id: null,
    created_at: '2026-06-05T00:00:00Z',
    updated_at: '2026-06-05T00:00:00Z',
    ...overrides,
  };
}

const DETAIL = {
  id: 'action-1',
  organization_id: 'org-1',
  site_id: 'site-1',
  site_name: 'North Yard',
  source_event_id: 'evt-1',
  title: 'Review reversing procedure',
  description: 'Follow up on the incident.',
  action_type: 'CORRECTIVE' as const,
  priority: 'HIGH' as const,
  status: 'OPEN' as const,
  owner_user_id: 'user-1',
  owner_name: 'Jordan Blake',
  due_date: '2026-03-10T00:00:00Z',
  created_by_user_id: 'user-2',
  created_by_api_client_id: null,
  created_at: '2026-02-18T09:15:00Z',
  updated_at: '2026-02-18T09:15:00Z',
  completed_at: null,
  cancelled_at: null,
  external_reference: 'CAPA-2201',
  attributes: {},
};

describe('ActionDetailPage — real API path', () => {
  it('shows a loading state, then the real action', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);

    renderAt('action-1');
    expect(screen.getByRole('status')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());
    expect(screen.getByText('Jordan Blake')).toBeInTheDocument();
    expect(screen.queryByText(/Showing example action data/)).not.toBeInTheDocument();
  });

  it('shows a not-found empty state for a 404 (nonexistent or cross-tenant) action', async () => {
    vi.mocked(getAction).mockRejectedValue(new ApiError('Action not found.', { status: 404 }));

    renderAt('does-not-exist');
    await waitFor(() => expect(screen.getByText('Action not found')).toBeInTheDocument());
  });

  it('shows an error state on a real API failure, with a working retry', async () => {
    vi.mocked(getAction).mockRejectedValueOnce(new ApiError('Could not reach the SIE API.', { status: 0 }));

    renderAt('action-1');
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.'));

    vi.mocked(getAction).mockResolvedValueOnce(DETAIL);
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());
  });

  it('a status transition the backend refuses leaves the displayed status unchanged and shows the error (never optimistic)', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(updateActionStatus).mockRejectedValue(
      new ApiError('This transition is not allowed from the action\'s current status.', { status: 409 }),
    );

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Change status to'), 'IN_PROGRESS');
    await userEvent.click(screen.getByRole('button', { name: 'Update status' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('This transition is not allowed'));
    // Status badge still reads the original, persisted status — the
    // "In progress" text that does exist is only the (still-selected)
    // option inside the status-change <select>, not a status update.
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByLabelText('Change status to')).toHaveValue('IN_PROGRESS');
  });

  it('a status transition the backend accepts updates the displayed status only after the response resolves', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(updateActionStatus).mockResolvedValue({ ...DETAIL, status: 'IN_PROGRESS' });

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Change status to'), 'IN_PROGRESS');
    await userEvent.click(screen.getByRole('button', { name: 'Update status' }));

    await waitFor(() => expect(screen.getByText('In progress')).toBeInTheDocument());
  });

  it('unauthorized mutation: a 403 from a status-change attempt is shown, not hidden, and the action stays as it was', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(updateActionStatus).mockRejectedValue(
      new ApiError('Missing intervention:manage permission in the requested organization.', { status: 403 }),
    );

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText('Change status to'), 'IN_PROGRESS');
    await userEvent.click(screen.getByRole('button', { name: 'Update status' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Missing intervention:manage permission'));
    expect(screen.getByText('Open')).toBeInTheDocument();
  });

  it('unauthorized mutation: a 403 from an edit attempt is shown in the drawer, not hidden', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(updateAction).mockRejectedValue(
      new ApiError('Missing intervention:manage permission in the requested organization.', { status: 403 }),
    );

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Missing intervention:manage permission'));
  });

  it('assignment permission handling: without intervention:assign, no editable owner control is rendered', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    expect(screen.getByText('You do not have permission to reassign this action.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Owner')).not.toBeInTheDocument();
  });

  it('never shows the raw source_event_id UUID as the source-event label, and its link still navigates by the real id', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL); // source_event_id: 'evt-1'

    renderAt('action-1');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    const link = screen.getByRole('link', { name: 'View source event' });
    expect(link).toHaveAttribute('href', '/events/evt-1');
    expect(screen.queryByText('evt-1')).not.toBeInTheDocument();

    await userEvent.click(link);
    await waitFor(() => expect(screen.getByText('Event detail page')).toBeInTheDocument());
  });

  it('the breadcrumb never shows the raw actionId UUID as its visible label — the real title once loaded', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);

    renderAt('action-1');
    const breadcrumb = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(within(breadcrumb).getByText('Action detail')).toBeInTheDocument();
    expect(within(breadcrumb).queryByText('action-1')).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    expect(within(breadcrumb).getByText('Review reversing procedure')).toBeInTheDocument();
    expect(within(breadcrumb).queryByText('action-1')).not.toBeInTheDocument();
  });
});

describe('ActionDetailPage — Referenced by Intelligence (SIE Operational Linkage Audit finding #1)', () => {
  it('1. shows no "Referenced by Intelligence" section when nothing references this action', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);

    renderAt('action-1');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());
    await waitFor(() => expect(listDecisions).toHaveBeenCalled());

    expect(screen.queryByText('Referenced by Intelligence')).not.toBeInTheDocument();
  });

  it('2/6. renders one linked Intelligence Decision, with its signal, type, category, rationale and date', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(listDecisions).mockResolvedValue({ items: [makeDecision()], total: 1, page: 1, page_size: 50 });

    renderAt('action-1');
    await waitFor(() => expect(screen.getByText('Repeated PPE non-compliance')).toBeInTheDocument());

    expect(screen.getByText('Intelligence Decision')).toBeInTheDocument(); // singular
    expect(screen.getByText('Act')).toBeInTheDocument();
    expect(screen.getByText(/Recurring pattern/)).toBeInTheDocument();
    expect(screen.getByText('Raising a refresher training intervention.')).toBeInTheDocument();
    expect(screen.getByText(/Decided/)).toBeInTheDocument();

    expect(vi.mocked(listDecisions)).toHaveBeenCalledWith(
      expect.objectContaining({ organizationId: 'org-1', linkedActionId: 'action-1' }),
      expect.any(AbortSignal),
    );
  });

  it('3. renders multiple linked Intelligence Decisions, not just the first', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(listDecisions).mockResolvedValue({
      items: [
        makeDecision({ id: 'dec-1', attention_title: 'Repeated PPE non-compliance' }),
        makeDecision({ id: 'dec-2', attention_title: 'Second unrelated signal', rationale: 'A second, separate decision also referenced this action.' }),
      ],
      total: 2,
      page: 1,
      page_size: 50,
    });

    renderAt('action-1');
    await waitFor(() => expect(screen.getByText('Intelligence Decisions')).toBeInTheDocument()); // plural

    expect(screen.getByText('Repeated PPE non-compliance')).toBeInTheDocument();
    expect(screen.getByText('Second unrelated signal')).toBeInTheDocument();
  });

  it('4/7. renders a linked Intelligence Outcome, with its classification, date and summary', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(listOutcomes).mockResolvedValue({ items: [makeOutcome()], total: 1, page: 1, page_size: 50 });

    renderAt('action-1');
    await waitFor(() => expect(screen.getByText('Some improvement observed, one repeat incident this week.')).toBeInTheDocument());

    expect(screen.getByText('Intelligence Outcome')).toBeInTheDocument(); // singular
    expect(screen.getByText('Partially effective')).toBeInTheDocument();

    expect(vi.mocked(listOutcomes)).toHaveBeenCalledWith(
      expect.objectContaining({ organizationId: 'org-1', linkedActionId: 'action-1' }),
      expect.any(AbortSignal),
    );
  });

  it('5. renders both a linked Decision and a linked Outcome together', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(listDecisions).mockResolvedValue({ items: [makeDecision()], total: 1, page: 1, page_size: 50 });
    vi.mocked(listOutcomes).mockResolvedValue({ items: [makeOutcome()], total: 1, page: 1, page_size: 50 });

    renderAt('action-1');
    await waitFor(() => expect(screen.getByText('Repeated PPE non-compliance')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Partially effective')).toBeInTheDocument());

    expect(screen.getByText('Intelligence Decision')).toBeInTheDocument();
    expect(screen.getByText('Intelligence Outcome')).toBeInTheDocument();
  });

  it('8. an Intelligence lookup failure does not break the rest of the Action page', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);
    vi.mocked(listDecisions).mockRejectedValue(new ApiError('Could not reach the SIE API.', { status: 0 }));

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());

    // The rest of the page is fully usable despite the failed lookup.
    expect(screen.getByText('Jordan Blake')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Linked Intelligence Decisions are unavailable right now/)).toBeInTheDocument());

    // Core, unrelated workflows are untouched.
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByLabelText('Change status to')).toBeInTheDocument();
  });

  it('9. existing ActionDetailPage behavior is unchanged when there is nothing to reference', async () => {
    vi.mocked(getAction).mockResolvedValue(DETAIL);

    renderAt('action-1', ['intervention:manage']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Review reversing procedure' })).toBeInTheDocument());
    await waitFor(() => expect(listDecisions).toHaveBeenCalled());

    // Every pre-existing section and control still renders exactly as before.
    expect(screen.getByText('Jordan Blake')).toBeInTheDocument();
    expect(screen.getByText('Follow up on the incident.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View source event' })).toBeInTheDocument();
    expect(screen.getByLabelText('Change status to')).toBeInTheDocument();
    expect(screen.getByText('You do not have permission to reassign this action.')).toBeInTheDocument();
    expect(screen.queryByText('Referenced by Intelligence')).not.toBeInTheDocument();
  });
});
