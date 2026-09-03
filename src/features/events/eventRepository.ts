import type { Page } from '../../types/common';
import type { EventStatus, SafetyEventDetail, SafetyEventSummary } from '../../types/events';

export interface EventListParams {
  page: number;
  pageSize: number;
  search?: string;
  status?: EventStatus;
  site?: string;
}

/**
 * The Events/Event Detail screens' one data-access seam. Both screens
 * depend on this interface, never on a concrete implementation — so
 * swapping `FixtureEventRepository` for a future `ApiEventRepository`
 * (once the backend adds `GET /events`/`GET /events/{id}` — see
 * `docs/FRONTEND_ARCHITECTURE.md`) changes exactly one line
 * (`useEventRepository.ts`), not the screens themselves.
 */
export interface EventRepository {
  list(params: EventListParams): Promise<Page<SafetyEventSummary>>;
  getById(id: string): Promise<SafetyEventDetail | null>;
}
