import type { DocumentReferenceRecord, EvidenceRecord, RelatedRecordItem } from './evidence';

/**
 * Event domain types — shaped after the backend's real, existing
 * `SafetyEvent` model/canonical event vocabulary
 * (`backend/app/intelligence/enums.py::SafetyEventType`,
 * `backend/app/models/safety_event.py`) so that the eventual real
 * `GET /events`/`GET /events/{id}` endpoint (not built yet — see
 * `src/fixtures/README.md`) can be adopted by simply swapping the
 * repository implementation feeding these same shapes, not by
 * reshaping the screens.
 */

export type EventStatus = 'open' | 'under_review' | 'closed' | 'quarantined';

export interface SafetyEventSummary {
  id: string;
  /** ISO 8601. */
  date: string;
  title: string;
  /** Mirrors SafetyEventType values loosely (e.g. "Incident",
   * "Observation") for realism — never invented beyond the backend's
   * own real vocabulary. */
  eventType: string;
  subtype?: string;
  site: string;
  status: EventStatus;
  sourceSystem: string;
}

export interface SafetyEventDetail extends SafetyEventSummary {
  narrative: string;
  relatedRecords: RelatedRecordItem[];
  evidence: EvidenceRecord[];
  /** `null` when there isn't enough evidence for SIE to state a finding
   * — see InsightPanel's own "insufficient evidence" fallback. */
  finding: string | null;
  findingContext?: string;
  relevantKnowledge: DocumentReferenceRecord[];
}
