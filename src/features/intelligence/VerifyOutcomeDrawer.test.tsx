import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import type { IntelligenceDecision } from '../../services/api/decisions';
import type { IntelligenceOutcome } from '../../services/api/outcomes';
import { VerifyOutcomeDrawer } from './VerifyOutcomeDrawer';

vi.mock('../../services/api/verifications', () => ({
  createVerification: vi.fn(),
  getVerificationState: vi.fn(),
}));

import {
  createVerification,
  getVerificationState,
  type IntelligenceOutcomeVerification,
  type VerificationState,
} from '../../services/api/verifications';

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

function makeState(overrides: Partial<VerificationState> = {}): VerificationState {
  return {
    outcome_id: 'outcome-1',
    current_verification: null,
    evidence_evaluation: {
      evidence_count: 0,
      valid_evidence_count: 0,
      invalid_evidence_count: 0,
      future_evidence_count: 0,
      evidence_status: 'NO_EVIDENCE',
      evidence_eligible_for_verification: false,
      reasons: [],
    },
    learning_eligibility: { eligible: false, reasons: [] },
    ...overrides,
  };
}

function makeVerification(overrides: Partial<IntelligenceOutcomeVerification> = {}): IntelligenceOutcomeVerification {
  return {
    id: 'verification-1',
    organization_id: 'org-1',
    outcome_id: 'outcome-1',
    status: 'INSUFFICIENT_EVIDENCE',
    rationale: 'No supporting evidence was supplied.',
    verified_at: '2026-06-06T00:00:00Z',
    verified_by_user_id: 'user-1',
    verified_by_api_client_id: null,
    created_at: '2026-06-06T00:00:00Z',
    updated_at: '2026-06-06T00:00:00Z',
    ...overrides,
  };
}

function renderDrawer(
  outcome: IntelligenceOutcome | null = makeOutcome(),
  decision: IntelligenceDecision | null = makeDecision(),
  onVerified = vi.fn(),
) {
  return render(
    <VerifyOutcomeDrawer
      isOpen={outcome !== null && decision !== null}
      onClose={vi.fn()}
      outcome={outcome}
      decision={decision}
      organizationId="org-1"
      onVerified={onVerified}
    />,
  );
}

beforeEach(() => {
  vi.mocked(createVerification).mockReset();
  vi.mocked(getVerificationState).mockReset();
  vi.mocked(getVerificationState).mockResolvedValue(makeState());
});

// --- 1. Verification entry point context: outcome + decision are both shown ---------------------

it('shows the decision and the outcome being verified, distinctly labeled', async () => {
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  expect(within(dialog).getByText('Decision — what did we decide?')).toBeInTheDocument();
  expect(within(dialog).getByText('Repeated PPE non-compliance')).toBeInTheDocument();
  expect(within(dialog).getByText('Outcome being verified — what actually happened?')).toBeInTheDocument();
  expect(within(dialog).getByText('Some improvement observed, one repeat incident this week.')).toBeInTheDocument();
  expect(within(dialog).getByText('Partially effective')).toBeInTheDocument();
  expect(within(dialog).getByText(/Verification — has this outcome been adequately supported\?/)).toBeInTheDocument();
});

it('shows the current verification state, including when none has been recorded yet', async () => {
  renderDrawer();
  const dialog = await screen.findByRole('dialog');
  await waitFor(() => expect(within(dialog).getByText('Not yet verified.')).toBeInTheDocument());
  expect(within(dialog).getByText('Evidence: No evidence supplied')).toBeInTheDocument();
});

it('shows the last recorded verification when one already exists', async () => {
  vi.mocked(getVerificationState).mockResolvedValue(
    makeState({ current_verification: makeVerification({ status: 'DISPUTED' }) }),
  );
  renderDrawer();
  const dialog = await screen.findByRole('dialog');
  await waitFor(() => expect(within(dialog).getByText('Last recorded:')).toBeInTheDocument());
  const lastRecordedRow = within(dialog).getByText('Last recorded:').closest('div');
  expect(within(lastRecordedRow!).getByText('Disputed')).toBeInTheDocument();
});

// --- 2. Verification form uses the existing contract (required fields validated) -----------------

it('requires a verification status and a rationale before submitting', async () => {
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.click(within(dialog).getByRole('button', { name: 'Record verification' }));
  expect(within(dialog).getByText('Choose a verification status.')).toBeInTheDocument();
  expect(createVerification).not.toHaveBeenCalled();

  await userEvent.selectOptions(within(dialog).getByLabelText('Verification status'), 'INSUFFICIENT_EVIDENCE');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record verification' }));
  expect(within(dialog).getByText('Rationale is required.')).toBeInTheDocument();
  expect(createVerification).not.toHaveBeenCalled();
});

// --- 3. Correct POST endpoint/payload against the real outcome_id --------------------------------

it('submits against the exact outcome being reviewed, using the real backend fields', async () => {
  vi.mocked(createVerification).mockResolvedValue(makeVerification());
  const onVerified = vi.fn();
  renderDrawer(makeOutcome(), makeDecision(), onVerified);
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Verification status'), 'INSUFFICIENT_EVIDENCE');
  await userEvent.type(within(dialog).getByLabelText('Rationale'), 'No supporting evidence was supplied.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record verification' }));

  await waitFor(() =>
    expect(createVerification).toHaveBeenCalledWith(
      expect.objectContaining({
        organizationId: 'org-1',
        outcomeId: 'outcome-1',
        input: expect.objectContaining({
          status: 'INSUFFICIENT_EVIDENCE',
          rationale: 'No supporting evidence was supplied.',
          verifiedAt: expect.any(String),
        }),
      }),
      expect.any(String),
    ),
  );
  await waitFor(() => expect(onVerified).toHaveBeenCalledWith(expect.objectContaining({ id: 'verification-1' })));
});

// --- 4. Successful verification updates the UI ---------------------------------------------------

it('shows the recorded verification after a successful submission', async () => {
  vi.mocked(createVerification).mockResolvedValue(makeVerification({ status: 'DISPUTED', rationale: 'Second reviewer disagrees.' }));
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Verification status'), 'DISPUTED');
  await userEvent.type(within(dialog).getByLabelText('Rationale'), 'Second reviewer disagrees.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record verification' }));

  await waitFor(() => expect(within(dialog).getByText('recorded.')).toBeInTheDocument());
  expect(within(dialog).getByText('Second reviewer disagrees.')).toBeInTheDocument();
  expect(within(dialog).getByText('Disputed')).toBeInTheDocument();
});

// --- 5. Permission denial is understandable -------------------------------------------------------

it('shows a distinct message on a 403, not the generic failure string', async () => {
  vi.mocked(createVerification).mockRejectedValue(
    new ApiError('Missing intelligence:decision_write permission in the requested organization.', { status: 403 }),
  );
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Verification status'), 'INSUFFICIENT_EVIDENCE');
  await userEvent.type(within(dialog).getByLabelText('Rationale'), 'Attempting to record.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record verification' }));

  await waitFor(() => expect(within(dialog).getByText(/don't have permission to verify outcomes/)).toBeInTheDocument());
  expect(within(dialog).queryByText('Missing intelligence:decision_write permission in the requested organization.')).not.toBeInTheDocument();
});

// --- 6. Invalid/not-found submission is handled ----------------------------------------------------

it('shows a distinct message when the outcome cannot be found', async () => {
  vi.mocked(createVerification).mockRejectedValue(new ApiError('Outcome not found in this organization.', { status: 404 }));
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Verification status'), 'INSUFFICIENT_EVIDENCE');
  await userEvent.type(within(dialog).getByLabelText('Rationale'), 'Attempting to record.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record verification' }));

  await waitFor(() => expect(within(dialog).getByText(/This outcome could not be found/)).toBeInTheDocument());
});

it('surfaces a generic failure (e.g. the 422 evidence-eligibility gate) without silently succeeding', async () => {
  vi.mocked(createVerification).mockRejectedValue(
    new ApiError('Cannot record VERIFIED: outcome evidence_status is NO_EVIDENCE, not VALID_EVIDENCE.', { status: 422 }),
  );
  renderDrawer();
  const dialog = await screen.findByRole('dialog');

  await userEvent.selectOptions(within(dialog).getByLabelText('Verification status'), 'VERIFIED');
  await userEvent.type(within(dialog).getByLabelText('Rationale'), 'Confirmed on-site.');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Record verification' }));

  await waitFor(() => expect(within(dialog).getByText(/Cannot record VERIFIED/)).toBeInTheDocument());
  expect(within(dialog).queryByText('recorded.')).not.toBeInTheDocument();
});

describe('when there is nothing to verify', () => {
  it('renders nothing without an outcome', () => {
    const { container } = renderDrawer(null, makeDecision());
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing without a decision', () => {
    const { container } = renderDrawer(makeOutcome(), null);
    expect(container).toBeEmptyDOMElement();
  });
});
