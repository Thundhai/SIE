import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { AuthProviderStub } from '../../test/authTestUtils';
import { RiskAssessmentDetailPage } from './RiskAssessmentDetailPage';

vi.mock('../../services/api/riskAssessments', () => ({
  getRiskAssessment: vi.fn(),
  getRiskAssessmentReport: vi.fn(),
  listFindingActions: vi.fn(),
}));

import { getRiskAssessment, getRiskAssessmentReport, listFindingActions } from '../../services/api/riskAssessments';
import type { RiskAssessmentDetail, RiskAssessmentReport } from '../../services/api/riskAssessments';

const ORGANIZATION = { id: 'org-1', name: 'Acme' };
const ASSESSMENT_ID = 'a1b2c3d4-0000-0000-0000-000000000001';
const FINDING_ID = 'f1f1f1f1-0000-0000-0000-000000000001';
const CONTROL_ID = 'c1c1c1c1-0000-0000-0000-000000000001';

function renderPage(id: string = ASSESSMENT_ID, authValue: Record<string, unknown> = {}) {
  return render(
    <AuthProviderStub value={{ isAuthenticated: true, organization: ORGANIZATION, hasPermission: () => true, ...authValue }}>
      <MemoryRouter initialEntries={[`/risk-assessments/${id}`]}>
        <Routes>
          <Route path="/risk-assessments/:assessmentId" element={<RiskAssessmentDetailPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProviderStub>,
  );
}

const DETAIL: RiskAssessmentDetail = {
  id: ASSESSMENT_ID,
  organization_id: 'org-1',
  scope: 'ORGANIZATION',
  site_id: null,
  title: 'Q3 Enterprise Assessment',
  reference: 'RA-2026-001',
  assessment_type: 'BASELINE',
  status: 'DRAFT',
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
  updated_at: '2026-06-03T00:00:00Z',
  findings: [
    {
      id: FINDING_ID,
      assessment_id: ASSESSMENT_ID,
      risk_area: {
        concept_id: 'concept-1',
        concept_key: 'VEHICLE_INCIDENT',
        label: 'Vehicle Incident',
        layer: 'GLOBAL',
        parent_domain: null,
        ontology_version: 1,
        scope: 'GLOBAL',
      },
      title: 'Reversing near miss at loading dock',
      description: 'A vehicle reversed without a spotter present.',
      system_analysis_summary: null,
      assessor_notes: null,
      source: 'MANUAL',
      originating_calculation_version: null,
      occurrence_period_start: null,
      occurrence_period_end: null,
      status: 'OPEN',
      candidate_status: null,
      candidate_generated_at: null,
      likelihood: 3,
      consequence: 3,
      inherent_risk_score: 9,
      inherent_risk_classification: 'MODERATE',
      residual_likelihood: null,
      residual_consequence: null,
      residual_risk_score: null,
      residual_risk_classification: null,
      inherent_risk_methodology_version: 'v1',
      residual_risk_methodology_version: null,
      linked_action_id: null,
      controls: [
        {
          id: CONTROL_ID,
          finding_id: FINDING_ID,
          description: 'Reversing spotter procedure',
          control_type: 'ADMINISTRATIVE',
          status: 'IN_PLACE',
          owner_user_id: null,
          reference: null,
          effectiveness: 'NOT_ASSESSED',
          effectiveness_rationale: null,
          assessed_at: null,
          assessed_by_user_id: null,
          evidence: [],
          created_at: '2026-06-01T00:00:00Z',
          updated_at: '2026-06-01T00:00:00Z',
        },
      ],
      evidence: [
        {
          id: 'ev-1',
          evidence_type: 'EVENT',
          reference_id: 'event-1',
          reference_label: null,
          created_at: '2026-06-01T00:00:00Z',
        },
      ],
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-06-01T00:00:00Z',
    },
  ],
};

const REPORT: RiskAssessmentReport = {
  id: ASSESSMENT_ID,
  organization_id: 'org-1',
  site_id: null,
  reference: 'RA-2026-001',
  title: 'Q3 Enterprise Assessment',
  assessment_type: 'BASELINE',
  assessment_date: '2026-06-01T00:00:00Z',
  as_of: '2026-06-01T00:00:00Z',
  methodology_version: 'v1',
  status: 'DRAFT',
  version: 1,
  lineage_id: 'lineage-1',
  supersedes_id: null,
  assessment_summary: {
    finding_count: 1,
    findings_by_status: { OPEN: 1 },
    findings_by_candidate_status: {},
    unrated_finding_count: 0,
    linked_action_count: 0,
    action_status_counts: {},
  },
  risk_distribution: {
    inherent: { critical: 0, high: 0, moderate: 1, low: 0, unrated: 0 },
    residual: { critical: 0, high: 0, moderate: 0, low: 0, unrated: 1 },
  },
  risk_areas: [],
  action_response_summary: {
    findings_with_no_response_action: 1,
    findings_with_one_response_action: 0,
    findings_with_multiple_response_actions: 0,
    total_response_actions: 0,
    completed_response_actions: 0,
    cancelled_response_actions: 0,
    outstanding_response_actions: 0,
    overdue_response_actions: 0,
    computed_at: '2026-06-03T00:00:00Z',
  },
  evidence_coverage: {
    total_findings: 1,
    findings_with_event_evidence: 1,
    findings_with_knowledge_evidence: 0,
    findings_with_action_evidence: 0,
    findings_with_intelligence_evidence: 0,
    findings_with_multiple_evidence_types: 0,
    findings_with_no_evidence: 0,
  },
  control_effectiveness: {
    total_controls: 1,
    implementation_status_counts: { IN_PLACE: 1 },
    effectiveness_rating_counts: { NOT_ASSESSED: 1 },
    findings_with_no_controls: 0,
    findings_with_controls_but_no_effectiveness_assessment: 1,
    findings_with_ineffective_or_partially_effective_controls: 0,
    assessed_controls_with_evidence: 0,
    assessed_controls_without_evidence: 1,
  },
  readiness: {
    status: 'NOT_READY',
    reasons: ['1 control has not yet been assessed for effectiveness.'],
    unrated_finding_count: 0,
    pending_candidate_review_count: 0,
    findings_without_evidence_count: 0,
    unresolved_high_risk_finding_count: 0,
    high_risk_findings_without_action_count: 0,
    has_no_findings: false,
  },
  generated_at: '2026-06-03T00:00:00Z',
};

describe('RiskAssessmentDetailPage', () => {
  it('shows a loading state, then the real assessment header, with no raw UUID shown as a primary label', async () => {
    vi.mocked(getRiskAssessment).mockResolvedValue(DETAIL);
    vi.mocked(getRiskAssessmentReport).mockResolvedValue(REPORT);

    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('Loading risk assessment…');

    await waitFor(() => expect(screen.getByText('Q3 Enterprise Assessment')).toBeInTheDocument());
    expect(screen.queryByText(ASSESSMENT_ID)).not.toBeInTheDocument();
    expect(screen.queryByText(FINDING_ID)).not.toBeInTheDocument();
  });

  it('Overview tab renders the real, backend-computed report — never a frontend-derived score', async () => {
    vi.mocked(getRiskAssessment).mockResolvedValue(DETAIL);
    vi.mocked(getRiskAssessmentReport).mockResolvedValue(REPORT);

    renderPage();
    await waitFor(() => expect(getRiskAssessmentReport).toHaveBeenCalledWith('org-1', ASSESSMENT_ID, expect.anything()));
    expect(await screen.findByText('Not ready')).toBeInTheDocument();
    expect(screen.getByText('1 control has not yet been assessed for effectiveness.')).toBeInTheDocument();
  });

  it('Findings tab shows real finding data, and expands to show its controls and evidence', async () => {
    vi.mocked(getRiskAssessment).mockResolvedValue(DETAIL);
    vi.mocked(getRiskAssessmentReport).mockResolvedValue(REPORT);
    vi.mocked(listFindingActions).mockResolvedValue({ items: [], total: 0 });

    renderPage();
    await waitFor(() => expect(screen.getByText('Q3 Enterprise Assessment')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('tab', { name: /Findings/ }));
    expect(screen.getByText('Reversing near miss at loading dock')).toBeInTheDocument();
    expect(screen.getByText('Vehicle Incident')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Reversing near miss at loading dock'));
    expect(screen.getByText('Reversing spotter procedure')).toBeInTheDocument();
    expect(screen.getByText('Not yet assessed')).toBeInTheDocument();
    // Evidence is shown via its type/navigation label, never the raw
    // reference_id UUID.
    expect(screen.queryByText('event-1')).not.toBeInTheDocument();
  });

  it('Controls tab aggregates controls across findings without a raw UUID label', async () => {
    vi.mocked(getRiskAssessment).mockResolvedValue(DETAIL);
    vi.mocked(getRiskAssessmentReport).mockResolvedValue(REPORT);

    renderPage();
    await waitFor(() => expect(screen.getByText('Q3 Enterprise Assessment')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('tab', { name: 'Controls' }));
    expect(screen.getByText('Reversing spotter procedure')).toBeInTheDocument();
    expect(screen.queryByText(CONTROL_ID)).not.toBeInTheDocument();
  });

  it('Evidence tab aggregates evidence across findings, grouped by finding', async () => {
    vi.mocked(getRiskAssessment).mockResolvedValue(DETAIL);
    vi.mocked(getRiskAssessmentReport).mockResolvedValue(REPORT);

    renderPage();
    await waitFor(() => expect(screen.getByText('Q3 Enterprise Assessment')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('tab', { name: 'Evidence' }));
    expect(screen.getByText('Reversing near miss at loading dock')).toBeInTheDocument();
    expect(screen.getByText('Event evidence')).toBeInTheDocument();
  });

  it('Actions tab shows an honest empty state when no findings have linked actions', async () => {
    vi.mocked(getRiskAssessment).mockResolvedValue(DETAIL);
    vi.mocked(getRiskAssessmentReport).mockResolvedValue(REPORT);
    vi.mocked(listFindingActions).mockResolvedValue({ items: [], total: 0 });

    renderPage();
    await waitFor(() => expect(screen.getByText('Q3 Enterprise Assessment')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('tab', { name: 'Actions' }));
    await waitFor(() => expect(screen.getByText('No actions linked to this assessment')).toBeInTheDocument());
  });

  it('hides the "Assess effectiveness" control without risk_assessment:write permission', async () => {
    vi.mocked(getRiskAssessment).mockResolvedValue(DETAIL);
    vi.mocked(getRiskAssessmentReport).mockResolvedValue(REPORT);
    vi.mocked(listFindingActions).mockResolvedValue({ items: [], total: 0 });

    renderPage(ASSESSMENT_ID, { hasPermission: () => false });
    await waitFor(() => expect(screen.getByText('Q3 Enterprise Assessment')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('tab', { name: 'Controls' }));
    expect(screen.queryByRole('button', { name: 'Assess effectiveness' })).not.toBeInTheDocument();
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
