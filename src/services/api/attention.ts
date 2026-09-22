/**
 * Attention & Delivery service — SIE Milestone 33/42. Thin typed
 * wrappers around the real, already-built backend endpoints
 * (`backend/app/api/v1/intelligence.py`'s `GET /intelligence/attention`
 * and `GET /intelligence/sites/{site_id}/attention`). Mirrors
 * `AttentionResultRead` (`backend/app/schemas/attention.py`)
 * field-for-field — nothing here is invented, and the backend's own
 * deterministic priority ordering (`_sort_items()` in
 * `app/intelligence/attention.py`) is never re-sorted or re-derived on
 * this side (SIE Milestone 42 spec §5: "Do not invent alternative
 * ranking logic in the frontend").
 */
import { apiRequest } from './client';

export type AttentionCategory =
  | 'DETERIORATING_TREND'
  | 'SIGNIFICANT_ANOMALY'
  | 'RECURRING_PATTERN'
  | 'ELEVATED_RISK'
  | 'PREDICTIVE_RISK'
  | 'UNRESOLVED_FINDING'
  | 'OVERDUE_ACTIONS'
  | 'EVIDENCE_GAP';

export type AttentionPriority = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';

export interface AttentionEvidence {
  source: string;
  calculation_version: string | null;
  entity_ids: string[];
  event_ids: string[];
}

export interface AttentionItem {
  category: AttentionCategory;
  priority: AttentionPriority;
  title: string;
  explanation: string;
  scope: string;
  site_id: string | null;
  site_label: string | null;
  as_of: string;
  window_days: number;
  evidence: AttentionEvidence;
  limitation: string | null;
  /** Stable, deterministic reference for this exact item (SIE Milestone
   * 34) — echoed back verbatim as `attention_reference` when recording a
   * human decision (`POST /intelligence/decisions`). Never generated or
   * reconstructed client-side. */
  reference: string;
}

export interface AttentionCategoryStatus {
  category: string;
  status: 'EVALUATED' | 'UNAVAILABLE' | 'NOT_EVALUATED';
  reason: string | null;
  item_count: number;
}

export interface AttentionResult {
  scope: string;
  organization_id: string;
  entity_id: string | null;
  as_of: string;
  window_days: number;
  generated_at: string;
  /** Already sorted by the backend (priority band, then category, then
   * title) — render in this exact order. */
  items: AttentionItem[];
  category_statuses: AttentionCategoryStatus[];
  calculation_versions: Record<string, string>;
}

export function getAttention(
  params: { organizationId: string; windowDays?: number; asOf?: string },
  signal?: AbortSignal,
): Promise<AttentionResult> {
  return apiRequest<AttentionResult>('/intelligence/attention', {
    query: { organization_id: params.organizationId, window_days: params.windowDays, as_of: params.asOf },
    signal,
  });
}

export function getSiteAttention(
  params: { organizationId: string; siteId: string; windowDays?: number; asOf?: string },
  signal?: AbortSignal,
): Promise<AttentionResult> {
  return apiRequest<AttentionResult>(`/intelligence/sites/${params.siteId}/attention`, {
    query: { organization_id: params.organizationId, window_days: params.windowDays, as_of: params.asOf },
    signal,
  });
}
