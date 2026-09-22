/**
 * Field Outcome Foundation service — SIE Milestone 37/42. Thin typed
 * wrappers around the real, already-built, already-tested backend
 * endpoints (`backend/app/api/v1/intelligence_outcomes.py`'s
 * `POST /intelligence/outcomes` and `GET /intelligence/outcomes`).
 * Mirrors `IntelligenceOutcomeCreate`/`IntelligenceOutcomeRead`
 * (`backend/app/schemas/intelligence_outcome.py`) field-for-field —
 * nothing here is invented, and no field the backend does not accept is
 * offered.
 *
 * **"What actually happened?", never "what did we decide?"** — an
 * outcome always references an existing `IntelligenceDecision` by
 * `decision_id`; this module never creates, infers, or mutates a
 * decision. It also never creates a `SafetyAction` — `linked_action_id`
 * may only reference one that already exists (SIE Milestone 42 spec:
 * "Do NOT implement automatic action creation").
 */
import { apiRequest } from './client';

/** Mirrors `app/models/intelligence_outcome_enums.py::IntelligenceOutcomeClassification` — the real, closed, four-value vocabulary. */
export type IntelligenceOutcomeClassification = 'EFFECTIVE' | 'PARTIALLY_EFFECTIVE' | 'INEFFECTIVE' | 'NO_OUTCOME_RECORDED';

export interface IntelligenceOutcomeDecisionSummary {
  id: string;
  attention_reference: string;
  decision: string;
}

export interface IntelligenceOutcomeActionSummary {
  id: string;
  title: string;
  status: string;
}

export interface IntelligenceOutcome {
  id: string;
  organization_id: string;
  decision_id: string;
  decision: IntelligenceOutcomeDecisionSummary | null;
  site_id: string | null;
  site_label: string | null;
  linked_action_id: string | null;
  linked_action: IntelligenceOutcomeActionSummary | null;
  classification: IntelligenceOutcomeClassification;
  summary: string;
  evidence_event_ids: string[];
  outcome_at: string;
  recorded_by_user_id: string | null;
  recorded_by_api_client_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IntelligenceOutcomeList {
  items: IntelligenceOutcome[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateOutcomeInput {
  /** The `IntelligenceDecision` this outcome reports the result of —
   * never client-invented, always the id of a decision the user is
   * already looking at. */
  decisionId: string;
  classification: IntelligenceOutcomeClassification;
  summary: string;
  /** The real-world instant the outcome became observable — never
   * "now" supplied blindly; must not be in the future (backend-enforced,
   * `reject_future_outcome_at()`). */
  outcomeAt: string;
  linkedActionId?: string;
}

export function listOutcomes(
  params: {
    organizationId: string;
    decisionId?: string;
    page?: number;
    pageSize?: number;
    /** Reverse lookup: which Intelligence Outcome(s) named this
     * SafetyAction — mirrors the backend's own already-built
     * `linked_action_id` query filter (SIE Operational Linkage Audit,
     * finding #1). Used by `ActionIntelligenceReferences.tsx`. */
    linkedActionId?: string;
  },
  signal?: AbortSignal,
): Promise<IntelligenceOutcomeList> {
  return apiRequest<IntelligenceOutcomeList>('/intelligence/outcomes', {
    query: {
      organization_id: params.organizationId,
      decision_id: params.decisionId,
      page: params.page,
      page_size: params.pageSize,
      linked_action_id: params.linkedActionId,
    },
    signal,
  });
}

export function createOutcome(
  params: { organizationId: string; input: CreateOutcomeInput },
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<IntelligenceOutcome> {
  const { organizationId, input } = params;
  return apiRequest<IntelligenceOutcome>('/intelligence/outcomes', {
    method: 'POST',
    query: { organization_id: organizationId },
    headers: { 'Idempotency-Key': idempotencyKey },
    body: {
      decision_id: input.decisionId,
      classification: input.classification,
      summary: input.summary,
      outcome_at: input.outcomeAt,
      linked_action_id: input.linkedActionId ?? null,
    },
    signal,
  });
}
