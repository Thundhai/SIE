/**
 * Enterprise intelligence service — thin typed wrappers around the real,
 * already-built backend endpoints (`backend/app/api/v1/intelligence.py`'s
 * `GET /intelligence/enterprise` and `GET /intelligence/sites/{site_id}`,
 * SIE Milestone 22/23). Response shapes mirror
 * `EnterpriseIntelligenceRead` (`backend/app/schemas/enterprise_intelligence.py`)
 * field-for-field — nothing here is invented, and no calculation is
 * repeated in TypeScript. This is the ONE source of truth the Intelligence
 * workspace (and Home's "Enterprise risk"/"What is changing"/"Needs
 * attention" sections) reads from — see `src/features/intelligence/`.
 */
import { apiRequest } from './client';

export interface RiskScoreComponent {
  key: string;
  label: string;
  raw_score: number;
  weight: number;
  normalized_weight: number;
  contribution: number;
}

export interface RiskScore {
  score: number | null;
  classification: string | null;
  version: string;
  components: RiskScoreComponent[];
  insufficient_data_reason: string | null;
}

export interface DataSufficiency {
  status: string;
  event_count: number;
}

export interface EnterpriseTrend {
  classification: string;
  metric: string;
  current_value: number;
  previous_value: number;
  absolute_change: number;
  percentage_change: number | null;
  current_period_start: string;
  current_period_end: string;
  previous_period_start: string;
  previous_period_end: string;
  calculation_version: string;
}

export interface EnterpriseIndicator {
  key: string;
  label: string;
  value: number;
  category: string;
  period_start: string;
  period_end: string;
  window_days: number;
  previous_value: number;
  absolute_change: number;
  percentage_change: number | null;
  trend_direction: string | null;
  unavailable_reason: string | null;
  calculation_version: string;
}

export interface RecurrencePattern {
  pattern_key: string;
  scope: string;
  site_id: string;
  site_label: string;
  event_type: string;
  event_subtype: string | null;
  count: number;
  first_seen: string;
  last_seen: string;
  window_start: string;
  window_end: string;
  window_days: number;
  supporting_event_ids: string[];
  classification: string;
  calculation_version: string;
}

export interface ConcentrationContributor {
  dimension: string;
  key: string;
  label: string;
  count: number;
  total: number;
  percentage: number;
  classification: string;
  calculation_version: string;
}

export interface EnterpriseAnomaly {
  metric: string;
  label: string;
  status: string;
  direction: string;
  current_value: number;
  baseline_mean: number | null;
  baseline_stdev: number | null;
  z_score: number | null;
  baseline_period_count: number;
  current_period_start: string;
  current_period_end: string;
  window_days: number;
  supporting_event_count: number;
  baseline_window_start: string | null;
  baseline_window_end: string | null;
  supporting_event_ids: string[];
  calculation_version: string;
}

export interface EnterpriseAssociation {
  metric_a: string;
  metric_b: string;
  label_a: string;
  label_b: string;
  classification: string;
  correlation_coefficient: number | null;
  period_count: number;
  period_start: string | null;
  period_end: string | null;
  window_days: number;
  values_a: number[];
  values_b: number[];
  supporting_event_ids: string[];
  calculation_version: string;
}

export interface ExplanationItem {
  code: string;
  message: string;
  value: number | null;
  baseline: number | null;
  contribution: number | null;
  evidence_reference: string;
}

export interface IntelligenceProvenance {
  organization_id: string;
  scope: string;
  entity_id: string | null;
  as_of: string;
  window_start: string;
  window_end: string;
  window_days: number;
  generated_at: string;
  event_count: number;
  evidence_sample_event_ids: string[];
  total_supporting_events: number;
  calculation_versions: Record<string, string>;
}

export interface ActionsContext {
  open_action_count: number;
  overdue_action_count: number;
  high_priority_action_count: number;
}

export interface EnterpriseIntelligence {
  scope: string;
  organization_id: string;
  entity_id: string | null;
  as_of: string;
  window_days: number;
  data_sufficiency: DataSufficiency;
  deterministic_risk: RiskScore;
  trend: EnterpriseTrend;
  indicators: EnterpriseIndicator[];
  patterns: RecurrencePattern[];
  concentrations: ConcentrationContributor[];
  anomalies: EnterpriseAnomaly[];
  associations: EnterpriseAssociation[];
  explanations: ExplanationItem[];
  provenance: IntelligenceProvenance;
  actions_context: ActionsContext | null;
}

export function getEnterpriseIntelligence(
  params: { organizationId: string; windowDays?: number },
  signal?: AbortSignal,
): Promise<EnterpriseIntelligence> {
  return apiRequest<EnterpriseIntelligence>('/intelligence/enterprise', {
    query: { organization_id: params.organizationId, window_days: params.windowDays },
    signal,
  });
}

export function getSiteIntelligence(
  params: { organizationId: string; siteId: string; windowDays?: number },
  signal?: AbortSignal,
): Promise<EnterpriseIntelligence> {
  return apiRequest<EnterpriseIntelligence>(`/intelligence/sites/${params.siteId}`, {
    query: { organization_id: params.organizationId, window_days: params.windowDays },
    signal,
  });
}
