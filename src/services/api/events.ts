/**
 * Events service — thin typed wrappers around the real backend endpoints
 * added in the Enterprise Read API & Browser Integration Foundation v0.1
 * milestone (`backend/app/api/v1/events.py`). Response shapes mirror
 * `SafetyEventSummaryRead`/`SafetyEventDetailRead`/`EventListRead`
 * field-for-field — nothing here is invented. See
 * `src/features/events/apiEventRepository.ts` for how these are adapted
 * onto the screens' existing `SafetyEventSummary`/`SafetyEventDetail`
 * shapes.
 */
import { apiRequest } from './client';

export interface EventSummaryResponse {
  id: string;
  event_time: string;
  event_type: string;
  event_subtype: string | null;
  site_id: string | null;
  site_name: string | null;
  status: string | null;
  severity: string | null;
  source_system: string;
  source_record_id: string;
  data_quality_status: string;
}

export interface EventListResponse {
  items: EventSummaryResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface EventProvenanceResponse {
  organization_id: string;
  source_system: string;
  source_record_id: string;
  source_record_version: string | null;
  source_schema_version: string | null;
  ingestion_batch_id: string;
  ingestion_source_id: string | null;
  data_source_name: string | null;
  ingestion_time: string;
  normalization_version: string;
  schema_version: string;
  correlation_id: string | null;
}

export interface EventDetailResponse extends EventSummaryResponse {
  organization_id: string;
  period_end: string | null;
  reported_time: string | null;
  potential_severity: string | null;
  description: string | null;
  location: string | null;
  project: string | null;
  department: string | null;
  contractor: string | null;
  activity: string | null;
  attributes: Record<string, unknown>;
  data_quality_issues: unknown[] | null;
  provenance: EventProvenanceResponse;
}

export interface ListEventsParams {
  organizationId: string;
  page: number;
  pageSize: number;
  eventType?: string;
  siteId?: string;
  status?: string;
  search?: string;
  signal?: AbortSignal;
}

export function listEvents(params: ListEventsParams): Promise<EventListResponse> {
  const { organizationId, page, pageSize, eventType, siteId, status, search, signal } = params;
  return apiRequest<EventListResponse>('/events', {
    query: {
      organization_id: organizationId,
      page,
      page_size: pageSize,
      event_type: eventType,
      site_id: siteId,
      status,
      search,
    },
    signal,
  });
}

export function getEvent(
  organizationId: string,
  eventId: string,
  signal?: AbortSignal,
): Promise<EventDetailResponse> {
  return apiRequest<EventDetailResponse>(`/events/${eventId}`, {
    query: { organization_id: organizationId },
    signal,
  });
}
