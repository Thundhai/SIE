/**
 * Field Intelligence Context service — SIE Milestone 32/41A/42. Thin
 * typed wrappers around `GET /intelligence/context` and
 * `GET /intelligence/sites/{site_id}/context`
 * (`backend/app/api/v1/intelligence.py`). Mirrors
 * `FieldIntelligenceContextRead` (`backend/app/schemas/field_intelligence_context.py`)
 * field-for-field.
 *
 * **Five independent, never-merged categories** (`backend/docs/
 * SIE_FIELD_INTELLIGENCE_CONTEXT_V0_1.md` §7, extended by SIE Milestone
 * 41A's `organizational_memory`): Observed (what actually happened),
 * Deterministic (patterns/trends/anomalies/risk — reuses
 * `EnterpriseIntelligence` from `./intelligence.ts` verbatim, never a
 * second definition), Predictive (model-derived signal, site-scope
 * only — see `PredictiveSignalOutcome`'s own note below), Knowledge
 * (retrieval-grounded evidence, `NOT_QUERIED` unless a query is
 * supplied), and Organizational Memory (governed learning, SIE
 * Milestone 40/41). A component must render these as visibly distinct
 * sections, never blur an observed fact, a model score, or accepted
 * memory into one undifferentiated feed (SIE Milestone 42 spec §8).
 */
import { apiRequest } from './client';
import type { IntegratedMemory } from './memoryIntegration';
import type { EnterpriseIntelligence } from './intelligence';

export interface ObservedFinding {
  finding_id: string;
  title: string;
  status: string;
  risk_area_label: string;
  inherent_risk_classification: string | null;
  residual_risk_classification: string | null;
  assessment_id: string;
  site_id: string | null;
  created_at: string;
}

export interface ObservedAction {
  action_id: string;
  title: string;
  status: string;
  priority: string;
  due_date: string | null;
  site_id: string | null;
}

export interface ObservedActionsSummary {
  open_action_count: number;
  overdue_action_count: number;
  high_priority_action_count: number;
}

export interface ObservedFact {
  outcome: 'OK' | 'UNAVAILABLE';
  unavailable_reason: string | null;
  event_count: number;
  evidence_sample_event_ids: string[];
  open_finding_count: number;
  open_finding_sample: ObservedFinding[];
  open_finding_control_count: number;
  actions: ObservedActionsSummary | null;
  open_action_sample: ObservedAction[];
}

export interface PredictiveContextValue {
  prediction_id: string;
  prediction_time: string;
  outcome: string;
  risk_score: number | null;
  probability: number | null;
  risk_category: string | null;
  model_version: string | null;
}

export interface PredictiveSignal {
  /** `NOT_AVAILABLE` at organization scope is expected, not an error —
   * `PredictiveContext` is site-scoped only
   * (`app/intelligence/context_composition.py::_predictive_signal()`).
   * View a specific site's context to see a real predictive value when
   * one has been recorded. `EXCLUDED_GENERATED_AFTER_AS_OF` means a
   * prediction exists but was generated after the requested `as_of` —
   * correctly withheld rather than shown as contemporaneous. */
  outcome: 'AVAILABLE' | 'NOT_AVAILABLE' | 'EXCLUDED_GENERATED_AFTER_AS_OF';
  value: PredictiveContextValue | null;
}

export interface KnowledgeEvidenceResult {
  rank: number;
  content: string;
  relevance: string;
  source: string;
  document: string;
  location: string | null;
  verification_status: string;
}

export interface KnowledgeEvidence {
  outcome: 'RESULTS' | 'NO_RELEVANT_EVIDENCE' | 'NOT_QUERIED' | 'UNAVAILABLE';
  unavailable_reason: string | null;
  query: string | null;
  results: KnowledgeEvidenceResult[];
  result_count: number;
}

export interface OrganizationalMemoryContext {
  outcome: 'OK' | 'UNAVAILABLE';
  unavailable_reason: string | null;
  items: IntegratedMemory[];
  calculation_version: string;
}

export interface OperationalScopeSite {
  id: string;
  name: string;
}

export interface OperationalScopeProject {
  id: string;
  name: string;
  code: string | null;
  status: string;
  site_ids: string[];
  filtered: boolean;
}

export interface OperationalScope {
  level: 'ORGANIZATION' | 'SITE';
  site: OperationalScopeSite | null;
  project: OperationalScopeProject | null;
}

export interface FieldIntelligenceContext {
  scope: string;
  organization_id: string;
  entity_id: string | null;
  as_of: string;
  window_days: number;
  generated_at: string;
  observed: ObservedFact;
  /** SIE Milestone 32's own design: reuses `EnterpriseIntelligenceRead`
   * verbatim rather than a second definition of indicators/trend/
   * anomalies/risk. */
  deterministic: EnterpriseIntelligence;
  predictive: PredictiveSignal;
  knowledge: KnowledgeEvidence;
  organizational_memory: OrganizationalMemoryContext;
  calculation_versions: Record<string, string>;
  operational_scope: OperationalScope | null;
}

export function getFieldIntelligenceContext(
  params: { organizationId: string; windowDays?: number; asOf?: string; projectId?: string },
  signal?: AbortSignal,
): Promise<FieldIntelligenceContext> {
  return apiRequest<FieldIntelligenceContext>('/intelligence/context', {
    query: {
      organization_id: params.organizationId,
      window_days: params.windowDays,
      as_of: params.asOf,
      project_id: params.projectId,
    },
    signal,
  });
}

export function getSiteFieldIntelligenceContext(
  params: { organizationId: string; siteId: string; windowDays?: number; asOf?: string },
  signal?: AbortSignal,
): Promise<FieldIntelligenceContext> {
  return apiRequest<FieldIntelligenceContext>(`/intelligence/sites/${params.siteId}/context`, {
    query: { organization_id: params.organizationId, window_days: params.windowDays, as_of: params.asOf },
    signal,
  });
}
