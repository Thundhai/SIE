import { apiRequest } from './client';

export type IntelligenceDecisionType = 'ACT' | 'DO_NOT_ACT' | 'DEFER' | 'ALREADY_ADDRESSED' | 'NOT_RELEVANT';

export type IntelligenceDecisionActorType = 'human' | 'machine';

/**
 * Field-for-field `sie_contract.DecisionReferenceDTO` (Roadmap Phase 1) —
 * narrower than the pre-extraction shape this type used to mirror.
 * `calculation_version`/`evidence_*`/a joined `linked_action`/
 * `site_label` are not part of this contract; a caller that needs the
 * linked SafetyAction's own title/status already holds
 * `linked_action_id` itself (it supplied it) and resolves it via the
 * existing actions API.
 */
export interface IntelligenceDecision {
  id: string;
  organization_id: string;
  attention_reference: string;
  scope: string;
  site_id: string | null;
  attention_category: string;
  attention_priority: string;
  attention_title: string;
  decision: IntelligenceDecisionType;
  rationale: string;
  decided_at: string;
  actor_type: IntelligenceDecisionActorType;
  actor_id: string;
}

export interface IntelligenceDecisionListResponse {
  items: IntelligenceDecision[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateIntelligenceDecisionInput {
  scope: string;
  siteId?: string;
  asOf: string;
  windowDays: number;
  attentionReference: string;
  decision: IntelligenceDecisionType;
  rationale: string;
  linkedActionId?: string;
}

export function createIntelligenceDecision(
  organizationId: string,
  input: CreateIntelligenceDecisionInput,
  idempotencyKey?: string,
): Promise<IntelligenceDecision> {
  return apiRequest<IntelligenceDecision>('/intelligence/decisions', {
    method: 'POST',
    query: { organization_id: organizationId },
    headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
    body: {
      scope: input.scope,
      site_id: input.siteId,
      as_of: input.asOf,
      window_days: input.windowDays,
      attention_reference: input.attentionReference,
      decision: input.decision,
      rationale: input.rationale,
      linked_action_id: input.linkedActionId,
    },
  });
}

export function listIntelligenceDecisions(
  params: {
    organizationId: string;
    linkedActionId?: string;
    attentionReference?: string;
    page?: number;
    pageSize?: number;
  },
  signal?: AbortSignal,
): Promise<IntelligenceDecisionListResponse> {
  return apiRequest<IntelligenceDecisionListResponse>('/intelligence/decisions', {
    query: {
      organization_id: params.organizationId,
      linked_action_id: params.linkedActionId,
      attention_reference: params.attentionReference,
      page: params.page ?? 1,
      page_size: params.pageSize ?? 25,
    },
    signal,
  });
}

export function getIntelligenceDecision(
  organizationId: string,
  decisionId: string,
  signal?: AbortSignal,
): Promise<IntelligenceDecision> {
  return apiRequest<IntelligenceDecision>(`/intelligence/decisions/${decisionId}`, {
    query: { organization_id: organizationId },
    signal,
  });
}
