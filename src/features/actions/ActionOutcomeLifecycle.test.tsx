import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProviderStub } from '../../test/authTestUtils';
import { ApiError } from '../../services/api/errors';
import type { SafetyAction } from '../../types/actions';
import { ActionOutcomeLifecycle } from './ActionOutcomeLifecycle';

vi.mock('../../services/api/intelligenceOutcomes', () => ({
  listIntelligenceOutcomes: vi.fn(),
  createIntelligenceOutcome: vi.fn(),
  getOutcomeVerificationState: vi.fn(),
  createOutcomeVerification: vi.fn(),
}));
vi.mock('../../services/api/intelligenceDecisions', () => ({
  listIntelligenceDecisions: vi.fn(),
}));

import { listIntelligenceOutcomes } from '../../services/api/intelligenceOutcomes';
import { listIntelligenceDecisions } from '../../services/api/intelligenceDecisions';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function makeCompletedAction(overrides: Partial<SafetyAction> = {}): SafetyAction {
  return {
    id: 'act-1',
    siteId: null,
    siteName: null,
    sourceEventId: null,
    title: 'Review reversing procedure',
    description: null,
    actionType: 'CORRECTIVE',
    priority: 'HIGH',
    status: 'COMPLETED',
    ownerUserId: null,
    ownerName: null,
    dueDate: null,
    createdByUserId: null,
    createdAt: '2026-06-01T00:00:00Z',
    updatedAt: '2026-06-01T00:00:00Z',
    completedAt: '2026-06-02T00:00:00Z',
    cancelledAt: null,
    externalReference: null,
    ...overrides,
  };
}

function renderLifecycle() {
  return render(
    <AuthProviderStub value={{ organization: ORGANIZATION, hasPermission: () => true }}>
      <ActionOutcomeLifecycle action={makeCompletedAction()} />
    </AuthProviderStub>,
  );
}

describe('ActionOutcomeLifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // SIE M43-IP-03: decision/outcome/verification recording is
  // implemented in the private Commercial Core repository and has no
  // client wired for it yet on this deployment -- every call here 501s
  // today. This section must say so honestly rather than showing a
  // scary generic error or a form that can never succeed.
  it('shows an honest "not available" state on a 501, not a generic error or a dead-end form', async () => {
    vi.mocked(listIntelligenceDecisions).mockRejectedValue(new ApiError('Not implemented.', { status: 501 }));
    vi.mocked(listIntelligenceOutcomes).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    renderLifecycle();

    await waitFor(() => expect(screen.getByText("Outcome tracking isn't available on this deployment")).toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /record outcome/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/No intelligence decision is linked/)).not.toBeInTheDocument();
  });

  it('still shows a genuine error honestly, distinct from the 501 "not available" case', async () => {
    vi.mocked(listIntelligenceDecisions).mockRejectedValue(new ApiError('Could not reach the SIE API.', { status: 0 }));
    vi.mocked(listIntelligenceOutcomes).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    renderLifecycle();

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.'));
    expect(screen.queryByText("Outcome tracking isn't available on this deployment")).not.toBeInTheDocument();
  });

  it('shows the normal no-decision-linked state when the backend is genuinely available and just has nothing to show', async () => {
    vi.mocked(listIntelligenceDecisions).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    vi.mocked(listIntelligenceOutcomes).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    renderLifecycle();

    await waitFor(() => expect(screen.getByText(/No intelligence decision is linked/)).toBeInTheDocument());
    expect(screen.queryByText("Outcome tracking isn't available on this deployment")).not.toBeInTheDocument();
  });

  // Roadmap Phase 1: Decisions is wired now, but Outcomes still 501s on
  // most deployments (Roadmap Phase 2). The two must not be conflated --
  // a real, linked decision should show even while outcome recording
  // stays unavailable, instead of the whole section collapsing to the
  // generic "not available" empty state.
  it('shows the real decision even when outcome tracking specifically is still unavailable', async () => {
    vi.mocked(listIntelligenceDecisions).mockResolvedValue({
      items: [
        {
          id: 'dec-1',
          organization_id: 'org-1',
          attention_reference: 'attn:org:2026-06-01:trend:0',
          scope: 'organization',
          site_id: null,
          attention_category: 'enterprise_trend',
          attention_priority: 'HIGH',
          attention_title: 'Rising incident rate',
          decision: 'ACT',
          rationale: 'Escalated to site manager.',
          decided_at: '2026-06-01T00:00:00Z',
          actor_type: 'human',
          actor_id: 'user-1',
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
    });
    vi.mocked(listIntelligenceOutcomes).mockRejectedValue(new ApiError('Not implemented.', { status: 501 }));
    renderLifecycle();

    await waitFor(() => expect(screen.getByText('Rising incident rate')).toBeInTheDocument());
    expect(screen.getByText(/Outcome tracking isn't available on this deployment yet/)).toBeInTheDocument();
    expect(screen.queryByText("Outcome tracking isn't available on this deployment", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /record outcome/i })).not.toBeInTheDocument();
  });
});
