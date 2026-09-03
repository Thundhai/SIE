import { ApiError } from '../../services/api/errors';
import {
  type EventDetailResponse,
  type EventSummaryResponse,
  getEvent,
  listEvents,
} from '../../services/api/events';
import { listSites } from '../../services/api/sites';
import type { Page } from '../../types/common';
import type { SafetyEventDetail, SafetyEventSummary } from '../../types/events';
import { formatCanonicalLabel } from './eventStatus';
import type { EventListParams, EventRepository, SiteOption } from './eventRepository';

/**
 * `EventRepository` backed by the real backend
 * (`GET /api/v1/events`/`GET /api/v1/events/{id}` — SIE Enterprise Read
 * API & Browser Integration Foundation v0.1). Adopted by `EventsPage`/
 * `EventDetailPage` through the exact same interface
 * `FixtureEventRepository` implements — see `useEventRepository.ts` for
 * which one is actually selected.
 *
 * **No evidence/knowledge references.** The real API's detail response
 * has no `evidence`/`relatedRecords`/`relevantKnowledge`/`finding`
 * fields at all (see `SafetyEventDetailRead`'s own docstring — there is
 * no real backend relationship to manufacture one from). This repository
 * maps that absence onto `evidence: []`, `relatedRecords: []`,
 * `relevantKnowledge: []`, `finding: null` — the exact shape
 * `InsightPanel` was already built to render as an honest "insufficient
 * evidence" state, not a redesign.
 */
export class ApiEventRepository implements EventRepository {
  readonly isFixtureBacked = false;

  constructor(private readonly organizationId: string) {}

  async list(params: EventListParams): Promise<Page<SafetyEventSummary>> {
    const response = await listEvents({
      organizationId: this.organizationId,
      page: params.page,
      pageSize: params.pageSize,
      status: params.status,
      search: params.search,
      siteId: params.site,
    });

    return {
      items: response.items.map(toSummary),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
    };
  }

  async getById(id: string): Promise<SafetyEventDetail | null> {
    try {
      const detail = await getEvent(this.organizationId, id);
      return toDetail(detail);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  }

  async listSiteOptions(): Promise<SiteOption[]> {
    const sites = await listSites(this.organizationId);
    return sites.map((site) => ({ value: site.id, label: site.name }));
  }
}

function toSummary(event: EventSummaryResponse): SafetyEventSummary {
  return {
    id: event.id,
    date: event.event_time,
    title: formatCanonicalLabel(event.event_type),
    eventType: event.event_type,
    subtype: event.event_subtype ?? undefined,
    site: event.site_name ?? 'Unassigned site',
    status: event.status ?? 'Unspecified',
    sourceSystem: event.source_system,
  };
}

function toDetail(event: EventDetailResponse): SafetyEventDetail {
  return {
    ...toSummary(event),
    narrative: event.description ?? 'No narrative was recorded for this event.',
    // No real evidence/knowledge relationship exists yet — see this
    // module's own docstring. InsightPanel renders this combination as
    // "insufficient evidence", never as a fabricated finding.
    finding: null,
    findingContext: undefined,
    evidence: [],
    relatedRecords: [],
    relevantKnowledge: [],
    provenance: {
      organizationId: event.provenance.organization_id,
      sourceSystem: event.provenance.source_system,
      sourceRecordId: event.provenance.source_record_id,
      sourceRecordVersion: event.provenance.source_record_version,
      ingestionBatchId: event.provenance.ingestion_batch_id,
      dataSourceName: event.provenance.data_source_name,
      ingestionTime: event.provenance.ingestion_time,
      correlationId: event.provenance.correlation_id,
    },
  };
}
