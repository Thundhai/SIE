/**
 * Human Decision & Intervention Trace service — SIE Milestone 34/42.
 * Thin typed wrappers around `backend/app/api/v1/intelligence_decisions.py`.
 * Mirrors `IntelligenceDecisionCreate`/`IntelligenceDecisionRead`
 * (`backend/app/schemas/intelligence_decision.py`) field-for-field.
 *
 * **The decision vocabulary below is the backend's real, closed
 * `IntelligenceDecisionType` enum** (`app/models/intelligence_decision_enums.py`)
 * — `ACT` / `DO_NOT_ACT` / `DEFER` / `ALREADY_ADDRESSED` / `NOT_RELEVANT`.
 * This is not the illustrative `ACT`/`MONITOR`/`DISMISS` naming used in
 * some milestone descriptions — the actual repository is the source of
 * truth (SIE Milestone 42 spec §1: "based on the actual current
 * repository, not assumptions from previous milestone reports").
 */
import { apiRequest } from './client';

export type IntelligenceDecisionType = 'ACT' | 'DO_NOT_ACT' | 'DEFER' | 'ALREADY_ADDRESSED' | 'NOT_RELEVANT';

export interface IntelligenceDecisionActionSummary {
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
  linked_action: IntelligenceDecisionActionSummary | null;
  decided_by_user_id: string | null;
  decided_by_api_client_id: string | null;
  decided_at: string;
  created_at: string;
  updated_at: string;
}

export interface IntelligenceDecisionList {
  items: IntelligenceDecision[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateDecisionInput {
  /** Must exactly match the `GET /intelligence/attention` (or
   * `/sites/{id}/attention`) response this decision concerns — the
   * backend re-derives "what SIE said" from these fields server-side
   * rather than trusting anything else the client sends (see
   * `resolve_attention_item()`'s own docstring). Never substitute a
   * fresh "now" for `asOf`. */
  scope: string;
  siteId?: string;
  asOf: string;
  windowDays: number;
  attentionReference: string;
  decision: IntelligenceDecisionType;
  rationale: string;
  linkedActionId?: string;
}

export function listDecisions(
  params: {
    organizationId: string;
    page?: number;
    pageSize?: number;
    siteId?: string;
    attentionReference?: string;
    decision?: IntelligenceDecisionType;
  },
  signal?: AbortSignal,
): Promise<IntelligenceDecisionList> {
  return apiRequest<IntelligenceDecisionList>('/intelligence/decisions', {
    query: {
      organization_id: params.organizationId,
      page: params.page,
      page_size: params.pageSize,
      site_id: params.siteId,
      attention_reference: params.attentionReference,
      decision: params.decision,
    },
    signal,
  });
}

export function createDecision(
  params: { organizationId: string; input: CreateDecisionInput },
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<IntelligenceDecision> {
  const { organizationId, input } = params;
  return apiRequest<IntelligenceDecision>('/intelligence/decisions', {
    method: 'POST',
    query: { organization_id: organizationId },
    headers: { 'Idempotency-Key': idempotencyKey },
    body: {
      scope: input.scope,
      site_id: input.siteId ?? null,
      as_of: input.asOf,
      window_days: input.windowDays,
      attention_reference: input.attentionReference,
      decision: input.decision,
      rationale: input.rationale,
      linked_action_id: input.linkedActionId ?? null,
    },
    signal,
  });
}
