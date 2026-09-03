import type { DocumentReferenceRecord, EvidenceRecord, RelatedRecordItem } from './evidence';

/**
 * Event domain types — shaped after the backend's real, existing
 * `SafetyEvent` model/canonical event vocabulary
 * (`backend/app/intelligence/enums.py::SafetyEventType`,
 * `backend/app/models/safety_event.py`), adopted by both
 * `FixtureEventRepository` and the real `ApiEventRepository` (SIE
 * Enterprise Read API & Browser Integration Foundation v0.1 —
 * `GET /events`/`GET /events/{id}`, see
 * `src/features/events/apiEventRepository.ts`) through the shared
 * `EventRepository` interface, so the screens never reshape around
 * which one is active.
 *
 * `status` on `SafetyEventSummary`/`SafetyEventDetail` is a plain
 * `string`, not a closed union: the real `SafetyEvent.status` column is
 * free text (no backend governance/ontology constrains it, unlike
 * `event_type`/`event_subtype` — see `docs/ENTERPRISE_API.md`), so
 * forcing it into a fixed set of values here would mean either
 * fabricating a mapping the backend doesn't have, or silently dropping
 * real statuses that don't happen to match the fixture's four examples
 * (§16's "never transform values to match fixture examples"). See
 * `src/features/events/eventStatus.ts` for how an arbitrary status
 * string is still rendered with a sensible tone/label.
 */

/** The fixture's own four example statuses — used as the Events screen's
 * filter candidates (a real, working `status` query-param value either
 * way), not as a constraint on what `SafetyEventSummary.status` may
 * contain. */
export type EventStatus = 'open' | 'under_review' | 'closed' | 'quarantined';

export interface SafetyEventSummary {
  id: string;
  /** ISO 8601. */
  date: string;
  /** A short, human-readable label for the row. The fixture data
   * supplies a real incident-report-style title; the real API has no
   * such free-text summary field in its list response (by design — see
   * `SafetyEventSummaryRead`'s own docstring, which deliberately omits
   * privacy-sensitive free text from the list view), so
   * `ApiEventRepository` derives this from the event's own canonical
   * `event_type` instead of inventing one. */
  title: string;
  /** Mirrors the backend's own canonical event-type vocabulary exactly
   * (e.g. "INCIDENT", "NEAR_MISS") when sourced from the real API —
   * never invented beyond it. */
  eventType: string;
  subtype?: string;
  site: string;
  /** See this module's own docstring — free text, not a closed union. */
  status: string;
  sourceSystem: string;
}

/** Real backend provenance for one event — mirrors
 * `EventProvenanceRead` (`backend/app/schemas/events.py`) field-for-field.
 * `null` on fixture-backed detail (fixtures have no genuine ingestion
 * history to report). */
export interface EventProvenance {
  organizationId: string;
  sourceSystem: string;
  sourceRecordId: string;
  sourceRecordVersion: string | null;
  ingestionBatchId: string;
  dataSourceName: string | null;
  ingestionTime: string;
  correlationId: string | null;
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
  /** `null` for fixture-backed data — see `EventProvenance`'s own
   * docstring. */
  provenance: EventProvenance | null;
}
