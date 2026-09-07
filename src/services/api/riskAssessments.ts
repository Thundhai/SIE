/**
 * Risk Assessments service — thin typed wrappers around the real,
 * already-built read endpoints (`backend/app/api/v1/risk_assessments.py`,
 * SIE Milestones 25-29A). Response shapes mirror `RiskAssessmentRead`/
 * `RiskAssessmentDetailRead`/`RiskAssessmentListRead`
 * (`backend/app/schemas/risk_assessment.py`) field-for-field. UI-01 wires
 * up only the list/detail read views — findings, controls, effectiveness,
 * evidence, and reporting stay for a later UI milestone (see
 * `src/features/riskAssessments/`'s own module docstring).
 */
import { apiRequest } from './client';

export interface RiskAssessmentSummary {
  id: string;
  organization_id: string;
  scope: string;
  site_id: string | null;
  title: string;
  reference: string | null;
  assessment_type: string;
  status: string;
  lineage_id: string;
  version: number;
  supersedes_id: string | null;
  assessment_date: string;
  as_of: string;
  window_days: number;
  assessor_user_id: string | null;
  methodology_version: string;
  submitted_at: string | null;
  submitted_by_user_id: string | null;
  approved_at: string | null;
  approved_by_user_id: string | null;
  created_by_user_id: string | null;
  created_by_api_client_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RiskAssessmentFindingSummary {
  id: string;
  assessment_id: string;
  risk_area: { concept_id: string; concept_key: string; label: string; layer: string };
  title: string;
  description: string | null;
  status: string;
  candidate_status: string | null;
  likelihood: number | null;
  consequence: number | null;
  inherent_risk_score: number | null;
  inherent_risk_classification: string | null;
  residual_likelihood: number | null;
  residual_consequence: number | null;
  residual_risk_score: number | null;
  residual_risk_classification: string | null;
}

export interface RiskAssessmentDetail extends RiskAssessmentSummary {
  findings: RiskAssessmentFindingSummary[];
}

export interface RiskAssessmentListResponse {
  items: RiskAssessmentSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ListRiskAssessmentsParams {
  organizationId: string;
  page: number;
  pageSize: number;
  status?: string;
  scope?: string;
  signal?: AbortSignal;
}

export function listRiskAssessments(params: ListRiskAssessmentsParams): Promise<RiskAssessmentListResponse> {
  const { organizationId, page, pageSize, status, scope, signal } = params;
  return apiRequest<RiskAssessmentListResponse>('/risk-assessments', {
    query: { organization_id: organizationId, page, page_size: pageSize, status, scope },
    signal,
  });
}

export function getRiskAssessment(
  organizationId: string,
  assessmentId: string,
  signal?: AbortSignal,
): Promise<RiskAssessmentDetail> {
  return apiRequest<RiskAssessmentDetail>(`/risk-assessments/${assessmentId}`, {
    query: { organization_id: organizationId },
    signal,
  });
}
