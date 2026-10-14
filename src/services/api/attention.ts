/**
 * Attention service — SIE Milestone 33. Thin typed wrappers around the
 * real, already-built backend endpoints (`backend/app/api/v1/intelligence.py`'s
 * `GET /intelligence/attention` and `GET /intelligence/sites/{site_id}/attention`),
 * both wired to the Commercial Core HTTP boundary (Task 01D-B) and live
 * on this deployment today. Mirrors `AttentionResultDTO`
 * (`backend/vendor/sie_contract/src/sie_contract/attention.py`) field-for-
 * field, including its nested `AsOfWindow`/`EvidenceReference` shapes
 * (`sie_contract/common.py`) — nothing here is invented, and the
 * backend's own deterministic priority ordering is never re-sorted or
 * re-derived on this side (SIE Milestone 33 spec: "Do not invent
 * alternative ranking logic in the frontend").
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

export type AttentionScope = 'organization' | 'site';

/** Mirrors `sie_contract.common.AsOfWindow` — a single nested temporal
 * envelope, never three flattened fields. `as_of` is the point in time
 * the output is valid as of; `generated_at` is when the computation
 * actually ran (may be later, e.g. for a historical query); the two are
 * never assumed equal. */
export interface AttentionAsOfWindow {
  as_of: string;
  generated_at: string;
  window_days: number | null;
}

/** Mirrors `sie_contract.common.EvidenceType`. */
export type AttentionEvidenceType =
  | 'safety_event'
  | 'risk_assessment_finding'
  | 'risk_assessment_control'
  | 'safety_action'
  | 'knowledge_document'
  | 'organizational_memory';

/** Mirrors `sie_contract.common.EvidenceReference` — a pointer to
 * something that justifies the item, resolved through Public SIE's own
 * existing read APIs for that entity type; never the full entity, never
 * the internal query/scoring that found it. */
export interface AttentionEvidenceReference {
  evidence_type: AttentionEvidenceType;
  reference_id: string;
  label: string | null;
}

export interface AttentionItem {
  category: AttentionCategory;
  priority: AttentionPriority;
  title: string;
  explanation: string;
  scope: AttentionScope;
  /** The site this item concerns when `scope` is `'site'`; `null` for an
   * organization-wide item. Note there is no `site_label` on the real
   * contract (`AttentionItemDTO` carries only the id) — a caller resolves
   * a display name itself, e.g. against an already-fetched site list. */
  site_id: string | null;
  as_of: AttentionAsOfWindow;
  evidence: AttentionEvidenceReference[];
  limitation: string | null;
  /** Stable, deterministic reference for this exact item. Not used by
   * this delivery (decision recording is out of scope — see
   * `AttentionList.tsx`'s own docstring) but kept on the type since it
   * is a real field the backend always returns. */
  reference: string;
}

export interface AttentionCategoryStatus {
  category: string;
  status: 'EVALUATED' | 'UNAVAILABLE' | 'NOT_EVALUATED';
  reason: string | null;
  item_count: number;
}

export interface AttentionResult {
  organization_id: string;
  scope: AttentionScope;
  /** The site_id when scope is 'site'; null when scope is 'organization'
   * (mirrors `AttentionResultDTO.entity_id`). */
  entity_id: string | null;
  as_of: AttentionAsOfWindow;
  /** Already sorted by the backend (priority band, then category, then
   * title) — render in this exact order. */
  items: AttentionItem[];
  category_status: AttentionCategoryStatus[];
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
