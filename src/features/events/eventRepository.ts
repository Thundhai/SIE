import type { Page } from '../../types/common';
import type { EventStatus, SafetyEventDetail, SafetyEventSummary } from '../../types/events';

export interface EventListParams {
  page: number;
  pageSize: number;
  search?: string;
  status?: EventStatus;
  /** `FixtureEventRepository` matches this against a site's exact name;
   * `ApiEventRepository` treats it as a site id (see
   * `listSiteOptions()` below, whose `value` is the identifier each
   * implementation actually expects here). */
  site?: string;
}

export interface SiteOption {
  value: string;
  label: string;
}

/**
 * The Events/Event Detail screens' one data-access seam. Both screens
 * depend on this interface, never on a concrete implementation — so
 * swapping `FixtureEventRepository` for `ApiEventRepository` (SIE
 * Enterprise Read API & Browser Integration Foundation v0.1's real
 * `GET /events`/`GET /events/{id}` — see `apiEventRepository.ts`)
 * changes exactly one function (`useEventRepository.ts`), not the
 * screens themselves.
 */
export interface EventRepository {
  list(params: EventListParams): Promise<Page<SafetyEventSummary>>;
  getById(id: string): Promise<SafetyEventDetail | null>;
  /** Candidate values for the Events screen's site filter — real site
   * names/ids from the caller's own organization when backed by the API,
   * the fixture's own example site names otherwise. */
  listSiteOptions(): Promise<SiteOption[]>;
  /** `true` for `FixtureEventRepository` — the one thing the screens
   * themselves are allowed to know about which implementation is active,
   * so they can honestly disclose example data rather than presenting it
   * as live (§14). */
  readonly isFixtureBacked: boolean;
}
