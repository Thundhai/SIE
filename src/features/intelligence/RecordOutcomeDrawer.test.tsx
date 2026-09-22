import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import type { IntelligenceDecision } from '../../services/api/decisions';
import { RecordOutcomeDrawer } from './RecordOutcomeDrawer';

vi.mock('../../services/api/outcomes', () => ({
  createOutcome: vi.fn(),
}));
vi.mock('../actions/useActionRepository', () => ({
  useActionRepository: () => ({
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 50 }),
    isFixtureBacked: false,
  }),
}));

import { createOutcome, type IntelligenceOutcome } from '../../services/api/outcomes';

function makeDecision(overrides: Partial<IntelligenceDecision> = {}): IntelligenceDecision {
  return {
    id: 'dec-1',
    organization_id: 'org-1',
    site_id: 'site-1',
    site_label: 'North Yard',
    scope: 'site',
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
    evidence_event_ids: ['evt-1', 'evt-2'],
    decision: 'ACT',
    rationale: 'Raising a refresher training intervention.',
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

function makeOutcome(overrides: Partial<IntelligenceOutcome> = {}): IntelligenceOutcome {
  return {
    id: 'outcome-1',
    organization_id: 'org-1',
    decision_id: 'dec-1',
    decision: { id: 'dec-1', attention_reference: 'ref-ppe-recurring-pattern', decision: 'ACT' },
    site_id: null,
    site_label: null,
    linked_action_id: null,
    linked_action: null,
    classification: 'EFFECTIVE',
    summary: 'Follow-up inspection confirmed compliance.',
    evidence_event_ids: [],
    outcome_at: '2026-06-05T00:00:00Z',
    recorded_by_user_id: 'user-1',
    recorded_by_api_client_id: null,
    created_at: '2026-06-05T00:00:00Z',
    updated_at: '2026-06-05T00:00:00Z',
    ...overrides,
  };
}

function renderDrawer(decision: IntelligenceDecision | null = makeDecision(), onRecorded = vi.fn()) {
  return render(
    <RecordOutcomeDrawer isOpen={decision !== null} onClose={vi.fn()} decision={decision} organizationId="org-1" onRecorded={onRecorded} />,
  );
}

beforeEach(() => {
  vi.mocked(createOutcome).mockReset();
});

// --- 1/2. Decision context is displayed, distinct from the outcome form -------------------------

it('shows enough decision context to identify which decision this outcome concerns', async () => {
  renderDrawer(makeDecision());
  const dialog = await screen.findByRole('dialog');

  expect(within(dialog).getByText('Decision — what did we decide?')).toBeInTheDocument();
  expect(within(dialog).getByText('Repeated PPE non-compliance')).toBeInTheDocument();
  expect(within(dialog).getByText(/North Yard/)).toBeInTheDocument();
  expect(within(dialog).getByText('Raising a refresher training intervention.')).toBeInTheDocument();
  expect(within(dialog).getByText('ref-ppe-recurring-pattern')).toBeInTheDocument();
  expect(within(dialog).getByText('Outcome — what actually happened?')).toBeInTheDocument();
});

// --- 3. Required outcome fields are validated ----------------------------------------------------

it('requires a classification and a summary before submitting', async () => {
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.click(within(dialog).getByRole('button', { name: 'Record outcome' }));
  expect(within(dialog).getByText('Choose a classification.')).toBeInTheDocument();
  expect(createOutcome).not.toHaveBeenCalled();

  await userEvent.selectOptions(within(dialog).getByLabelText('Classification'), 'EFFECTIVE');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record outcome' }));
  expect(within(dialog).getByText('Summary is required.')).toBeInTheDocument();
  expect(createOutcome).not.toHaveBeenCalled();
});

// --- 4. Correct POST endpoint/payload is used ------------------------------------------------

it('submits the real backend fields against the decision being reviewed, nothing invented', async () => {
  vi.mocked(createOutcome).mockResolvedValue(makeOutcome());
  const onRecorded = vi.fn();
  renderDrawer(makeDecision(), onRecorded);
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Classification'), 'EFFECTIVE');
  await userEvent.type(within(dialog).getByLabelText('Summary'), 'Follow-up inspection confirmed compliance.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record outcome' }));

  await waitFor(() =>
    expect(createOutcome).toHaveBeenCalledWith(
      expect.objectContaining({
        organizationId: 'org-1',
        input: expect.objectContaining({
          decisionId: 'dec-1',
          classification: 'EFFECTIVE',
          summary: 'Follow-up inspection confirmed compliance.',
          outcomeAt: expect.any(String),
        }),
      }),
      expect.any(String),
    ),
  );
  await waitFor(() => expect(onRecorded).toHaveBeenCalledWith(expect.objectContaining({ id: 'outcome-1' })));
});

// --- 5. Successful submission updates the UI --------------------------------------------------

it('shows the recorded outcome after a successful submission', async () => {
  vi.mocked(createOutcome).mockResolvedValue(makeOutcome({ classification: 'PARTIALLY_EFFECTIVE', summary: 'Some improvement observed.' }));
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Classification'), 'PARTIALLY_EFFECTIVE');
  await userEvent.type(within(dialog).getByLabelText('Summary'), 'Some improvement observed.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record outcome' }));

  await waitFor(() => expect(within(dialog).getByText('recorded.')).toBeInTheDocument());
  expect(within(dialog).getByText('Some improvement observed.')).toBeInTheDocument();
  expect(within(dialog).getByText('Partially effective')).toBeInTheDocument();
});

// --- 6. Failed submission is communicated clearly ------------------------------------------------

it('surfaces a generic submission failure without silently succeeding', async () => {
  vi.mocked(createOutcome).mockRejectedValue(new ApiError('Could not reach the SIE API.', { status: 0 }));
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Classification'), 'INEFFECTIVE');
  await userEvent.type(within(dialog).getByLabelText('Summary'), 'Attempting to record.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record outcome' }));

  await waitFor(() => expect(within(dialog).getByText('Could not reach the SIE API.')).toBeInTheDocument());
  expect(within(dialog).queryByText('recorded.')).not.toBeInTheDocument();
});

// --- 7. Permission-denied behavior is handled distinctly, not folded into a generic message ------

it('shows a distinct message on a 403, not the generic failure string', async () => {
  vi.mocked(createOutcome).mockRejectedValue(
    new ApiError('Missing intelligence:decision_write permission in the requested organization.', { status: 403 }),
  );
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Classification'), 'INEFFECTIVE');
  await userEvent.type(within(dialog).getByLabelText('Summary'), 'Attempting to record.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record outcome' }));

  await waitFor(() => expect(within(dialog).getByText(/don't have permission to record outcomes/)).toBeInTheDocument());
  expect(within(dialog).queryByText('Missing intelligence:decision_write permission in the requested organization.')).not.toBeInTheDocument();
});

describe('when there is no decision to review', () => {
  it('renders nothing', () => {
    const { container } = renderDrawer(null);
    expect(container).toBeEmptyDOMElement();
  });
});
