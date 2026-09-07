import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { RiskAssessmentDetailPage } from './RiskAssessmentDetailPage';

vi.mock('../../services/api/riskAssessments', () => ({
  getRiskAssessment: vi.fn(),
}));

import { getRiskAssessment } from '../../services/api/riskAssessments';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };
const ASSESSMENT_ID = 'a1b2c3d4-0000-0000-0000-000000000001';

function renderPage(id: string = ASSESSMENT_ID) {
  return render(
    <AuthProviderStub value={{ isAuthenticated: true, organization: ORGANIZATION }}>
      <MemoryRouter initialEntries={[`/risk-assessments/${id}`]}>
        <Routes>
          <Route path="/risk-assessments/:assessmentId" element={<RiskAssessmentDetailPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

const DETAIL = {
  id: ASSESSMENT_ID,
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
  submitted_at: '2026-06-02T00:00:00Z',
  submitted_by_user_id: null,
  approved_at: '2026-06-03T00:00:00Z',
  approved_by_user_id: null,
  created_by_user_id: null,
  created_by_api_client_id: null,
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-03T00:00:00Z',
  findings: [
    {
      id: 'finding-1',
      assessment_id: ASSESSMENT_ID,
      risk_area: { concept_id: 'concept-1', concept_key: 'VEHICLE_INCIDENT', label: 'Vehicle incident', layer: 'GLOBAL' },
      title: 'Reversing near miss at loading dock',
      description: null,
      status: 'OPEN',
      candidate_status: null,
      likelihood: 3,
      consequence: 3,
      inherent_risk_score: 9,
      inherent_risk_classification: 'MODERATE',
      residual_likelihood: null,
      residual_consequence: null,
      residual_risk_score: null,
      residual_risk_classification: null,
    },
  ],
};

describe('RiskAssessmentDetailPage', () => {
  it('shows a loading state, then the real assessment, with no raw UUID shown as a primary label', async () => {
    vi.mocked(getRiskAssessment).mockResolvedValue(DETAIL);

    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('Loading risk assessment…');

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Q3 Enterprise Assessment' })).toBeInTheDocument());
    expect(screen.getByText('Reversing near miss at loading dock')).toBeInTheDocument();
    // The breadcrumb's current-page label is the assessment's own title,
    // never the raw assessmentId UUID.
    expect(screen.queryByText(ASSESSMENT_ID)).not.toBeInTheDocument();
  });

  it('handles a 404 with a calm not-found state, not a scary error', async () => {
    vi.mocked(getRiskAssessment).mockRejectedValue(new ApiError('Not found.', { status: 404 }));

    renderPage();
    await waitFor(() => expect(screen.getByText('Risk assessment not found')).toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows a calm access-denied state on a 403', async () => {
    vi.mocked(getRiskAssessment).mockRejectedValue(
      new ApiError('Missing risk_assessment:read permission in the requested organization.', { status: 403 }),
    );

    renderPage();
    await waitFor(() => expect(screen.getByText("You don't have permission to view this")).toBeInTheDocument());
  });

  it('shows the no-organization empty state when no identity is resolved', () => {
    render(
      <AuthProviderStub>
        <MemoryRouter initialEntries={[`/risk-assessments/${ASSESSMENT_ID}`]}>
          <Routes>
            <Route path="/risk-assessments/:assessmentId" element={<RiskAssessmentDetailPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProviderStub>,
    );
    expect(screen.getByText('No organization context available')).toBeInTheDocument();
  });
});
