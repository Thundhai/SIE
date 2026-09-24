import { apiRequest } from './client';

export type IntelligenceDecisionType = 'ACT' | 'ACCEPT' | 'MONITOR' | 'DEFER' | 'DISMISS';

export interface IntelligenceDecisionAction {
  id: string;
  title: string;
  status: string;
}

export interface IntelligenceDecision {
  id: string;
  organization_id: string;
  site_id: string | null;
  site_label: string | null;
  scope: string;
  attention_reference: string;
  attention_category: string;
  attention_priority: string;
  attention_title: string;
  attention_explanation: string;
  intelligence_as_of: string;
  intelligence_window_days: number;
  calculation_version: string | null;
  evidence_source: string | null;
  evidence_entity_ids: string[];
  evidence_event_ids: string[];
  decision: IntelligenceDecisionType;
  rationale: string;
  linked_action_id: string | null;
  linked_action: IntelligenceDecisionAction | null;
  decided_by_user_id: string | null;
  decided_by_api_client_id: string | null;
  decided_at: string;
  created_at: string;
  updated_at: string;
}

export interface IntelligenceDecisionListResponse {
  items: IntelligenceDecision[];
  total: number;
  page: number;
  page_size: number;
}

export function listIntelligenceDecisions(
  params: {
    organizationId: string;
    linkedActionId?: string;
    page?: number;
    pageSize?: number;
  },
  signal?: AbortSignal,
): Promise<IntelligenceDecisionListResponse> {
  return apiRequest<IntelligenceDecisionListResponse>('/intelligence/decisions', {
    query: {
      organization_id: params.organizationId,
      linked_action_id: params.linkedActionId,
      page: params.page ?? 1,
      page_size: params.pageSize ?? 25,
    },
    signal,
  });
}
