import { apiRequest } from './client';

export type IntelligenceOutcomeClassification =
  | 'EFFECTIVE'
  | 'PARTIALLY_EFFECTIVE'
  | 'INEFFECTIVE'
  | 'NO_OUTCOME_RECORDED';

export type IntelligenceOutcomeVerificationStatus =
  | 'VERIFIED'
  | 'INSUFFICIENT_EVIDENCE'
  | 'DISPUTED';

export type EvidenceStatus =
  | 'NO_EVIDENCE'
  | 'INVALID_EVIDENCE'
  | 'INSUFFICIENT_EVIDENCE'
  | 'VALID_EVIDENCE';

export interface IntelligenceOutcome {
  id: string;
  organization_id: string;
  decision_id: string;
  decision: { id: string; attention_reference: string; decision: string } | null;
  site_id: string | null;
  site_label: string | null;
  linked_action_id: string | null;
  linked_action: { id: string; title: string; status: string } | null;
  classification: IntelligenceOutcomeClassification;
  summary: string;
  evidence_event_ids: string[];
  outcome_at: string;
  recorded_by_user_id: string | null;
  recorded_by_api_client_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IntelligenceOutcomeListResponse {
  items: IntelligenceOutcome[];
  total: number;
  page: number;
  page_size: number;
}

export interface EvidenceEvaluation {
  evidence_count: number;
  valid_evidence_count: number;
  invalid_evidence_count: number;
  future_evidence_count: number;
  evidence_status: EvidenceStatus;
  evidence_eligible_for_verification: boolean;
  reasons: string[];
}

export interface OutcomeVerification {
  id: string;
  organization_id: string;
  outcome_id: string;
  status: IntelligenceOutcomeVerificationStatus;
  rationale: string;
  verified_at: string;
  verified_by_user_id: string | null;
  verified_by_api_client_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface LearningEligibility {
  eligible: boolean;
  reasons: string[];
}

export interface OutcomeVerificationState {
  outcome_id: string;
  current_verification: OutcomeVerification | null;
  evidence_evaluation: EvidenceEvaluation;
  learning_eligibility: LearningEligibility;
}

export interface CreateOutcomeBody {
  decision_id: string;
  site_id?: string;
  linked_action_id?: string;
  classification: IntelligenceOutcomeClassification;
  summary: string;
  evidence_event_ids?: string[];
  outcome_at: string;
}

export interface CreateVerificationBody {
  status: IntelligenceOutcomeVerificationStatus;
  rationale: string;
  verified_at: string;
}

export function listIntelligenceOutcomes(
  params: {
    organizationId: string;
    linkedActionId?: string;
    decisionId?: string;
    page?: number;
    pageSize?: number;
  },
  signal?: AbortSignal,
): Promise<IntelligenceOutcomeListResponse> {
  return apiRequest<IntelligenceOutcomeListResponse>('/intelligence/outcomes', {
    query: {
      organization_id: params.organizationId,
      linked_action_id: params.linkedActionId,
      decision_id: params.decisionId,
      page: params.page ?? 1,
      page_size: params.pageSize ?? 25,
    },
    signal,
  });
}

export function createIntelligenceOutcome(
  organizationId: string,
  body: CreateOutcomeBody,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<IntelligenceOutcome> {
  return apiRequest<IntelligenceOutcome>('/intelligence/outcomes', {
    method: 'POST',
    query: { organization_id: organizationId },
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    signal,
  });
}

export function getOutcomeVerificationState(
  organizationId: string,
  outcomeId: string,
  signal?: AbortSignal,
): Promise<OutcomeVerificationState> {
  return apiRequest<OutcomeVerificationState>(`/intelligence/outcomes/${outcomeId}/verification-state`, {
    query: { organization_id: organizationId },
    signal,
  });
}

export function createOutcomeVerification(
  organizationId: string,
  outcomeId: string,
  body: CreateVerificationBody,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<OutcomeVerification> {
  return apiRequest<OutcomeVerification>(`/intelligence/outcomes/${outcomeId}/verifications`, {
    method: 'POST',
    query: { organization_id: organizationId },
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    signal,
  });
}
