/**
 * Intelligence analytics service — thin typed wrappers around the real,
 * already-authenticated backend endpoints
 * (`backend/app/api/v1/intelligence.py`). Response shapes mirror
 * `AnalyticsSummaryRead`/`RiskSignalRead` (`backend/app/schemas/intelligence.py`)
 * field-for-field. This is the ONLY data source the Home screen uses —
 * there is no fixture fallback for analytics, because a real endpoint
 * exists (see src/fixtures/README.md for the fixture-vs-API boundary
 * rule this milestone follows).
 */
import { apiRequest } from './client';

export interface FeatureValue {
  name: string;
  value: number | null;
  window_days: number;
  as_of: string;
  entity_type: string;
  entity_id: string | null;
  source_event_ids: string[];
  calculation_version: string;
  data_quality: string;
  exposure_basis: number | null;
  unavailable_reason: string | null;
}

export interface IndicatorValue {
  name: string;
  category: string;
  feature: FeatureValue;
}

export interface RiskSignal {
  signal_type: string;
  severity: string;
  observed_period_start: string;
  observed_period_end: string;
  entity_type: string;
  entity_id: string | null;
  supporting_features: Record<string, number | null>;
  supporting_event_ids: string[];
  data_quality: string;
  calculation_version: string;
}

export interface SourceReliability {
  source_system: string;
  record_count: number;
  valid_count: number;
  partial_count: number;
  invalid_count: number;
  quarantined_count: number;
  latest_event_time: string | null;
  latest_ingestion_time: string | null;
  is_stale: boolean;
  freshness_threshold_days: number;
}

export interface AnalyticsSummary {
  organization_id: string;
  entity_type: string;
  entity_id: string | null;
  as_of: string;
  window_days: number;
  event_count: number;
  data_sufficiency: string;
  features: Record<string, FeatureValue>;
  indicators: IndicatorValue[];
  signals: RiskSignal[];
  source_reliability: SourceReliability[];
}

export function getAnalyticsSummary(
  params: { organizationId: string; siteId?: string; windowDays?: number },
  signal?: AbortSignal,
): Promise<AnalyticsSummary> {
  return apiRequest<AnalyticsSummary>('/intelligence/analytics/summary', {
    query: {
      organization_id: params.organizationId,
      site_id: params.siteId,
      window_days: params.windowDays,
    },
    signal,
  });
}

export function getAnalyticsSignals(
  params: { organizationId: string; siteId?: string; windowDays?: number },
  signal?: AbortSignal,
): Promise<RiskSignal[]> {
  return apiRequest<RiskSignal[]>('/intelligence/analytics/signals', {
    query: {
      organization_id: params.organizationId,
      site_id: params.siteId,
      window_days: params.windowDays,
    },
    signal,
  });
}
