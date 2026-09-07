import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { RiskAssessmentsPage } from './RiskAssessmentsPage';

vi.mock('../../services/api/riskAssessments', () => ({
  listRiskAssessments: vi.fn(),
}));

import { listRiskAssessments } from '../../services/api/riskAssessments';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };

function renderPage() {
  return render(
    <AuthProviderStub value={{ isAuthenticated: true, organization: ORGANIZATION }}>
      <MemoryRouter initialEntries={['/risk-assessments']}>
        <RiskAssessmentsPage />
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

const ONE_ASSESSMENT = {
  id: 'a1b2c3d4-0000-0000-0000-000000000001',
  organization_id: 'org-1',
  scope: 'ORGANIZATION',
  site_id: null,
  title: 'Q3 Enterprise Assessment',
  reference: 'RA-2026-001',
  assessment_type: 'BASELINE',
  status: 'APPROVED',
  lineage_id: 'lineage-1',
  version: 1,
  supersedes_id: null,
  assessment_date: '2026-06-01T00:00:00Z',
  as_of: '2026-06-01T00:00:00Z',
  window_days: 90,
  assessor_user_id: null,
  methodology_version: 'v1',
  submitted_at: null,
  submitted_by_user_id: null,
  approved_at: null,
  approved_by_user_id: null,
  created_by_user_id: null,
  created_by_api_client_id: null,
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-01T00:00:00Z',
};

describe('RiskAssessmentsPage', () => {
  it('shows a loading state, then real risk assessments, with no raw UUID shown as a label', async () => {
    vi.mocked(listRiskAssessments).mockResolvedValue({ items: [ONE_ASSESSMENT], total: 1, page: 1, page_size: 10 });

    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('Loading risk assessments…');

    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    expect(screen.getByText('Q3 Enterprise Assessment')).toBeInTheDocument();
    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.queryByText(ONE_ASSESSMENT.id)).not.toBeInTheDocument();
  });

  it('shows an empty state for a real, successful query with zero results', async () => {
    vi.mocked(listRiskAssessments).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });

    renderPage();
    await waitFor(() => expect(screen.getByText('No risk assessments yet')).toBeInTheDocument());
  });

  it('shows a calm access-denied state on a 403', async () => {
    vi.mocked(listRiskAssessments).mockRejectedValue(
      new ApiError('Missing risk_assessment:read permission in the requested organization.', { status: 403 }),
    );

    renderPage();
    await waitFor(() => expect(screen.getByText("You don't have permission to view this")).toBeInTheDocument());
  });

  it('shows an error state on API failure, with a working retry', async () => {
    vi.mocked(listRiskAssessments).mockRejectedValueOnce(new ApiError('Could not reach the SIE API.', { status: 0 }));

    renderPage();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not reach the SIE API.'));

    vi.mocked(listRiskAssessments).mockResolvedValueOnce({ items: [ONE_ASSESSMENT], total: 1, page: 1, page_size: 10 });
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
  });

  it('shows the no-organization empty state when no identity is resolved', () => {
    render(
      <AuthProviderStub>
        <MemoryRouter>
          <RiskAssessmentsPage />
        </MemoryRouter>
      </AuthProviderStub>,
    );
    expect(screen.getByText('No organization context available')).toBeInTheDocument();
  });
});
