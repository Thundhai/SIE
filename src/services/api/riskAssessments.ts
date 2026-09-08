/**
 * Risk Assessments service — thin typed wrappers around the real,
 * already-built endpoints (`backend/app/api/v1/risk_assessments.py`,
 * SIE Milestones 25-29A). Response/request shapes mirror
 * `backend/app/schemas/risk_assessment.py`/`risk_assessment_report.py`
 * field-for-field — nothing here is invented; every shape below was
 * checked directly against the backend schema file before being typed
 * (SIE Milestone UI-02's own "inspect the actual backend contract"
 * requirement).
 */
import { apiRequest } from './client';

// --- Findings: risk area, evidence, controls -------------------------------------------------

export interface RiskAreaConcept {
  concept_id: string;
  concept_key: string;
  label: string;
  layer: string;
  parent_domain: string | null;
  ontology_version: number;
  scope: string;
}

export type RiskEvidenceType = 'EVENT' | 'ANOMALY' | 'PATTERN' | 'ASSOCIATION' | 'KNOWLEDGE_DOCUMENT' | 'ACTION' | 'OTHER';

export interface RiskEvidence {
  id: string;
  evidence_type: RiskEvidenceType;
  reference_id: string | null;
  reference_label: string | null;
  created_at: string;
}

export type ControlType = 'ELIMINATION' | 'SUBSTITUTION' | 'ENGINEERING' | 'ADMINISTRATIVE' | 'PPE' | 'OTHER';
export type ControlStatus = 'PROPOSED' | 'IN_PLACE' | 'NOT_IMPLEMENTED' | 'PARTIALLY_IMPLEMENTED' | 'NOT_VERIFIED';
/** The backend's actual `ControlEffectiveness` enum
 * (`backend/app/models/risk_assessment_enums.py`) — NOT_ASSESSED,
 * INEFFECTIVE, PARTIALLY_EFFECTIVE, EFFECTIVE. */
export type ControlEffectiveness = 'NOT_ASSESSED' | 'INEFFECTIVE' | 'PARTIALLY_EFFECTIVE' | 'EFFECTIVE';

export interface RiskControl {
  id: string;
  finding_id: string;
  description: string;
  control_type: ControlType;
  status: ControlStatus;
  owner_user_id: string | null;
  reference: string | null;
  effectiveness: ControlEffectiveness;
  effectiveness_rationale: string | null;
  assessed_at: string | null;
  assessed_by_user_id: string | null;
  evidence: RiskEvidence[];
  created_at: string;
  updated_at: string;
}

export type FindingStatus = 'OPEN' | 'ADDRESSED' | 'CLOSED';
export type RiskCandidateStatus = 'IDENTIFIED' | 'UNDER_REVIEW' | 'ACCEPTED' | 'REJECTED';
export type FindingSource =
  | 'MANUAL'
  | 'INSPECTION'
  | 'INTELLIGENCE_RISK_SCORE'
  | 'INTELLIGENCE_ANOMALY'
  | 'INTELLIGENCE_PATTERN'
  | 'INTELLIGENCE_ASSOCIATION'
  | 'INTELLIGENCE_CONCENTRATION'
  | 'INTELLIGENCE_TREND'
  | 'INTELLIGENCE_INDICATOR'
  | 'KNOWLEDGE';

export interface RiskAssessmentFinding {
  id: string;
  assessment_id: string;
  risk_area: RiskAreaConcept;
  title: string;
  description: string | null;
  system_analysis_summary: string | null;
  assessor_notes: string | null;
  source: FindingSource;
  originating_calculation_version: string | null;
  occurrence_period_start: string | null;
  occurrence_period_end: string | null;
  status: FindingStatus;
  candidate_status: RiskCandidateStatus | null;
  candidate_generated_at: string | null;
  likelihood: number | null;
  consequence: number | null;
  inherent_risk_score: number | null;
  inherent_risk_classification: string | null;
  residual_likelihood: number | null;
  residual_consequence: number | null;
  residual_risk_score: number | null;
  residual_risk_classification: string | null;
  inherent_risk_methodology_version: string | null;
  residual_risk_methodology_version: string | null;
  linked_action_id: string | null;
  controls: RiskControl[];
  evidence: RiskEvidence[];
  created_at: string;
  updated_at: string;
}

// --- Assessment ----------------------------------------------------------------------------

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

export interface RiskAssessmentDetail extends RiskAssessmentSummary {
  findings: RiskAssessmentFinding[];
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
  siteId?: string;
  signal?: AbortSignal;
}

export function listRiskAssessments(params: ListRiskAssessmentsParams): Promise<RiskAssessmentListResponse> {
  const { organizationId, page, pageSize, status, scope, siteId, signal } = params;
  return apiRequest<RiskAssessmentListResponse>('/risk-assessments', {
    query: { organization_id: organizationId, page, page_size: pageSize, status, scope, site_id: siteId },
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

// --- Reporting (SIE Milestone 28, read-only) ------------------------------------------------

export interface RiskBandCounts {
  critical: number;
  high: number;
  moderate: number;
  low: number;
  unrated: number;
}

export interface RiskDistribution {
  inherent: RiskBandCounts;
  residual: RiskBandCounts;
}

export interface RiskAreaSummary {
  concept_id: string;
  concept_key: string;
  label: string;
  layer: string;
  parent_domain: string | null;
  scope: string;
  finding_count: number;
  highest_inherent_risk_score: number | null;
  highest_inherent_risk_classification: string | null;
  highest_residual_risk_score: number | null;
  highest_residual_risk_classification: string | null;
  open_finding_count: number;
  closed_finding_count: number;
  associated_action_count: number;
}

export interface ActionResponseSummary {
  findings_with_no_response_action: number;
  findings_with_one_response_action: number;
  findings_with_multiple_response_actions: number;
  total_response_actions: number;
  completed_response_actions: number;
  cancelled_response_actions: number;
  outstanding_response_actions: number;
  overdue_response_actions: number;
  computed_at: string;
}

export interface EvidenceCoverage {
  total_findings: number;
  findings_with_event_evidence: number;
  findings_with_knowledge_evidence: number;
  findings_with_action_evidence: number;
  findings_with_intelligence_evidence: number;
  findings_with_multiple_evidence_types: number;
  findings_with_no_evidence: number;
}

export interface ControlEffectivenessSummary {
  total_controls: number;
  implementation_status_counts: Record<string, number>;
  effectiveness_rating_counts: Record<string, number>;
  findings_with_no_controls: number;
  findings_with_controls_but_no_effectiveness_assessment: number;
  findings_with_ineffective_or_partially_effective_controls: number;
  assessed_controls_with_evidence: number;
  assessed_controls_without_evidence: number;
}

export interface AssessmentReadiness {
  status: string;
  reasons: string[];
  unrated_finding_count: number;
  pending_candidate_review_count: number;
  findings_without_evidence_count: number;
  unresolved_high_risk_finding_count: number;
  high_risk_findings_without_action_count: number;
  has_no_findings: boolean;
}

export interface AssessmentSummaryCounts {
  finding_count: number;
  findings_by_status: Record<string, number>;
  findings_by_candidate_status: Record<string, number>;
  unrated_finding_count: number;
  linked_action_count: number;
  action_status_counts: Record<string, number>;
}

export interface RiskAssessmentReport {
  id: string;
  organization_id: string;
  site_id: string | null;
  reference: string | null;
  title: string;
  assessment_type: string;
  assessment_date: string;
  as_of: string;
  methodology_version: string;
  status: string;
  version: number;
  lineage_id: string;
  supersedes_id: string | null;
  assessment_summary: AssessmentSummaryCounts;
  risk_distribution: RiskDistribution;
  risk_areas: RiskAreaSummary[];
  action_response_summary: ActionResponseSummary;
  evidence_coverage: EvidenceCoverage;
  control_effectiveness: ControlEffectivenessSummary;
  readiness: AssessmentReadiness;
  generated_at: string;
}

export function getRiskAssessmentReport(
  organizationId: string,
  assessmentId: string,
  signal?: AbortSignal,
): Promise<RiskAssessmentReport> {
  return apiRequest<RiskAssessmentReport>(`/risk-assessments/${assessmentId}/report`, {
    query: { organization_id: organizationId },
    signal,
  });
}

// --- Control effectiveness (SIE Milestone 29/29A) -------------------------------------------

export interface AssessControlEffectivenessBody {
  effectiveness_rating: Exclude<ControlEffectiveness, 'NOT_ASSESSED'>;
  effectiveness_rationale: string;
  assessed_at?: string;
}

/** The ONE, dedicated, governed path to setting a control's
 * effectiveness (SIE Milestone 29A) — never the generic finding
 * PATCH/`controls` bulk-replace path. See
 * `RiskAssessmentControlEffectivenessAssess`'s own docstring
 * (`backend/app/schemas/risk_assessment.py`). */
export function assessControlEffectiveness(
  organizationId: string,
  assessmentId: string,
  findingId: string,
  controlId: string,
  body: AssessControlEffectivenessBody,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<RiskControl> {
  return apiRequest<RiskControl>(
    `/risk-assessments/${assessmentId}/findings/${findingId}/controls/${controlId}/assess-effectiveness`,
    {
      method: 'POST',
      query: { organization_id: organizationId },
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
      signal,
    },
  );
}

// --- Finding <-> Action relationship (SIE Milestone 27) -------------------------------------

export interface RiskAssessmentLinkedAction {
  id: string;
  finding_id: string;
  action_id: string;
  action_title: string;
  action_status: string;
  created_at: string;
  created_by_user_id: string | null;
  created_by_api_client_id: string | null;
}

export interface RiskAssessmentLinkedActionList {
  items: RiskAssessmentLinkedAction[];
  total: number;
}

export function listFindingActions(
  organizationId: string,
  assessmentId: string,
  findingId: string,
  signal?: AbortSignal,
): Promise<RiskAssessmentLinkedActionList> {
  return apiRequest<RiskAssessmentLinkedActionList>(
    `/risk-assessments/${assessmentId}/findings/${findingId}/actions`,
    { query: { organization_id: organizationId }, signal },
  );
}

export interface CreateFindingActionBody {
  title: string;
  description?: string;
  action_type: string;
  priority?: string;
  owner_user_id?: string;
  due_date?: string;
  external_reference?: string;
}

/** Creates a brand-new `SafetyAction` and links it to this finding in
 * one operation (SIE Milestone 27, item 1: "Create an action from a
 * finding"). Requires `risk_assessment:write` AND `intervention:manage`
 * (`+intervention:assign` if `owner_user_id` is supplied) on the
 * backend — the frontend never assumes either. */
export function createFindingAction(
  organizationId: string,
  assessmentId: string,
  findingId: string,
  body: CreateFindingActionBody,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<RiskAssessmentLinkedAction> {
  return apiRequest<RiskAssessmentLinkedAction>(`/risk-assessments/${assessmentId}/findings/${findingId}/actions`, {
    method: 'POST',
    query: { organization_id: organizationId },
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    signal,
  });
}

/** Links an already-existing action to this finding — idempotent by
 * construction on the backend (linking an already-linked action returns
 * the existing relationship, not an error). */
export function linkFindingAction(
  organizationId: string,
  assessmentId: string,
  findingId: string,
  actionId: string,
  signal?: AbortSignal,
): Promise<RiskAssessmentLinkedAction> {
  return apiRequest<RiskAssessmentLinkedAction>(
    `/risk-assessments/${assessmentId}/findings/${findingId}/actions/link`,
    { method: 'POST', query: { organization_id: organizationId }, body: { action_id: actionId }, signal },
  );
}

export function unlinkFindingAction(
  organizationId: string,
  assessmentId: string,
  findingId: string,
  actionId: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiRequest<void>(`/risk-assessments/${assessmentId}/findings/${findingId}/actions/${actionId}`, {
    method: 'DELETE',
    query: { organization_id: organizationId },
    signal,
  });
}

// --- Finding closure (SIE Milestone 27, "closure governance") -------------------------------

/** The one governed path to `FindingStatus.CLOSED` — requires
 * `risk_assessment:approve`, a non-blank `closure_reason`, and a finding
 * that has actually been rated. Never triggered automatically by a
 * linked action's own status. */
export function closeFinding(
  organizationId: string,
  assessmentId: string,
  findingId: string,
  closureReason: string,
  signal?: AbortSignal,
): Promise<RiskAssessmentFinding> {
  return apiRequest<RiskAssessmentFinding>(`/risk-assessments/${assessmentId}/findings/${findingId}/close`, {
    method: 'POST',
    query: { organization_id: organizationId },
    body: { closure_reason: closureReason },
    signal,
  });
}
