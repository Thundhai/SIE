import { FIXTURE_EVENTS, buildFixtureDetail } from '../../fixtures/events';
import type { Page } from '../../types/common';
import type { SafetyEventDetail, SafetyEventSummary } from '../../types/events';
import type { EventListParams, EventRepository, SiteOption } from './eventRepository';

const FIXTURE_SITE_OPTIONS: SiteOption[] = [
  { value: 'Project North', label: 'Project North' },
  { value: 'Bayview Terminal', label: 'Bayview Terminal' },
  { value: 'Riverside Plant', label: 'Riverside Plant' },
];

/**
 * `EventRepository` backed by `src/fixtures/events.ts` — see
 * `src/fixtures/README.md`. A small artificial delay is included by
 * default so the Events/Event Detail screens' loading states are
 * genuinely exercised during normal use, not just in tests (tests pass
 * `latencyMs: 0` for determinism).
 */
export class FixtureEventRepository implements EventRepository {
  readonly isFixtureBacked = true;

  constructor(private readonly latencyMs = 250) {}

  async listSiteOptions(): Promise<SiteOption[]> {
    return FIXTURE_SITE_OPTIONS;
  }

  private async delay(): Promise<void> {
    if (this.latencyMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.latencyMs));
    }
  }

  async list(params: EventListParams): Promise<Page<SafetyEventSummary>> {
    await this.delay();

    const search = params.search?.trim().toLowerCase();
    const filtered = FIXTURE_EVENTS.filter((event) => {
      if (params.status && event.status !== params.status) return false;
      if (params.site && event.site !== params.site) return false;
      if (search) {
        const haystack = `${event.title} ${event.eventType} ${event.subtype ?? ''} ${event.site}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });

    const start = (params.page - 1) * params.pageSize;
    const items = filtered.slice(start, start + params.pageSize);

    return { items, total: filtered.length, page: params.page, pageSize: params.pageSize };
  }

  async getById(id: string): Promise<SafetyEventDetail | null> {
    await this.delay();
    const summary = FIXTURE_EVENTS.find((event) => event.id === id);
    if (!summary) return null;
    return buildFixtureDetail(summary);
  }
}
