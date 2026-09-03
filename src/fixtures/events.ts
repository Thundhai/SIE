import type { EventStatus, SafetyEventDetail, SafetyEventSummary } from '../types/events';

/**
 * Fixture safety-event data — SIE Frontend Foundation v0.1.
 *
 * FICTIONAL DATA ONLY. No real enterprise records, site names, or
 * narratives appear anywhere in this file — every id, title, site, and
 * narrative below is invented for this milestone. This file exists
 * solely because the backend has no human-facing `GET /events` or
 * `GET /events/{id}` endpoint yet (see src/fixtures/README.md and the
 * milestone's own completion report, "known backend gaps"). It must
 * never be imported by anything outside `src/features/events/` and its
 * own repository — see `FixtureEventRepository`.
 */

const SITES = ['Project North', 'Bayview Terminal', 'Riverside Plant'] as const;
const SOURCE_SYSTEMS = ['Manual Entry', 'Field App', 'Contractor Portal'] as const;

interface FixtureEventSeed {
  id: string;
  date: string;
  title: string;
  eventType: string;
  subtype?: string;
  site: (typeof SITES)[number];
  status: EventStatus;
  sourceSystem: (typeof SOURCE_SYSTEMS)[number];
}

const SEEDS: FixtureEventSeed[] = [
  { id: 'EVT-1001', date: '2026-02-18', title: 'Vehicle incident — reversing collision', eventType: 'Incident', subtype: 'Vehicle', site: 'Project North', status: 'under_review', sourceSystem: 'Field App' },
  { id: 'EVT-1002', date: '2026-02-14', title: 'Vehicle observation — speeding on site road', eventType: 'Observation', subtype: 'Vehicle', site: 'Project North', status: 'closed', sourceSystem: 'Manual Entry' },
  { id: 'EVT-1003', date: '2026-01-29', title: 'Vehicle incident — near-miss with pedestrian', eventType: 'Incident', subtype: 'Vehicle', site: 'Project North', status: 'closed', sourceSystem: 'Field App' },
  { id: 'EVT-1004', date: '2026-02-20', title: 'Working at height — missing edge protection', eventType: 'Observation', subtype: 'Working at Height', site: 'Bayview Terminal', status: 'open', sourceSystem: 'Field App' },
  { id: 'EVT-1005', date: '2026-02-17', title: 'PPE non-compliance — hard hat not worn', eventType: 'Observation', subtype: 'PPE', site: 'Riverside Plant', status: 'closed', sourceSystem: 'Manual Entry' },
  { id: 'EVT-1006', date: '2026-02-16', title: 'Electrical isolation procedure not followed', eventType: 'Incident', subtype: 'Electrical', site: 'Riverside Plant', status: 'under_review', sourceSystem: 'Contractor Portal' },
  { id: 'EVT-1007', date: '2026-02-12', title: 'Near miss — dropped tool from height', eventType: 'Near Miss', site: 'Bayview Terminal', status: 'closed', sourceSystem: 'Field App' },
  { id: 'EVT-1008', date: '2026-02-10', title: 'Lifting operation — load chart exceeded', eventType: 'Incident', subtype: 'Lifting', site: 'Bayview Terminal', status: 'closed', sourceSystem: 'Manual Entry' },
  { id: 'EVT-1009', date: '2026-02-08', title: 'Housekeeping deficiency — blocked walkway', eventType: 'Observation', subtype: 'Housekeeping', site: 'Riverside Plant', status: 'closed', sourceSystem: 'Manual Entry' },
  { id: 'EVT-1010', date: '2026-02-05', title: 'Positive observation — correct fall protection use', eventType: 'Observation', subtype: 'Positive', site: 'Project North', status: 'closed', sourceSystem: 'Field App' },
  { id: 'EVT-1011', date: '2026-02-03', title: 'Audit finding — incomplete permit documentation', eventType: 'Audit Finding', site: 'Riverside Plant', status: 'open', sourceSystem: 'Contractor Portal' },
  { id: 'EVT-1012', date: '2026-01-30', title: 'Environmental event — minor spill contained', eventType: 'Incident', subtype: 'Environmental', site: 'Bayview Terminal', status: 'closed', sourceSystem: 'Field App' },
  { id: 'EVT-1013', date: '2026-01-27', title: 'Procedure violation — lockout tag missing', eventType: 'Observation', subtype: 'Procedure Violation', site: 'Riverside Plant', status: 'closed', sourceSystem: 'Manual Entry' },
  { id: 'EVT-1014', date: '2026-01-22', title: 'First aid case — minor laceration', eventType: 'Incident', subtype: 'First Aid Case', site: 'Project North', status: 'closed', sourceSystem: 'Field App' },
  { id: 'EVT-1015', date: '2026-01-19', title: 'Unrecognized source term — awaiting classification', eventType: 'Unclassified', site: 'Bayview Terminal', status: 'quarantined', sourceSystem: 'Contractor Portal' },
  { id: 'EVT-1016', date: '2026-01-15', title: 'Property damage — equipment contact with structure', eventType: 'Incident', subtype: 'Property Damage', site: 'Riverside Plant', status: 'closed', sourceSystem: 'Manual Entry' },
  { id: 'EVT-1017', date: '2026-01-12', title: 'Vehicle observation — seatbelt not worn', eventType: 'Observation', subtype: 'Vehicle', site: 'Project North', status: 'closed', sourceSystem: 'Field App' },
  { id: 'EVT-1018', date: '2026-01-08', title: 'Emergency preparedness — drill completed', eventType: 'Observation', subtype: 'Emergency Preparedness', site: 'Bayview Terminal', status: 'closed', sourceSystem: 'Manual Entry' },
];

export const FIXTURE_EVENTS: SafetyEventSummary[] = SEEDS.map(({ id, date, title, eventType, subtype, site, status, sourceSystem }) => ({
  id,
  date,
  title,
  eventType,
  subtype,
  site,
  status,
  sourceSystem,
}));

/** Rich detail exists only for a few illustrative events (the vehicle
 * trio, deliberately, to demonstrate the evidence-grounded finding
 * pattern §16 describes verbatim). Every other event gets an honest
 * generic detail with no fabricated finding — see the fallback in
 * `buildDetail()` below. */
const DETAIL_OVERRIDES: Record<string, Pick<SafetyEventDetail, 'narrative' | 'finding' | 'findingContext' | 'evidence' | 'relatedRecords' | 'relevantKnowledge'>> = {
  'EVT-1001': {
    narrative:
      'A site vehicle reversing from the laydown area made contact with a parked trailer. No injuries were reported. The reversing alarm was functional; a banksman was not present at the time.',
    finding: 'Vehicle-related events have increased over the selected period at this site.',
    findingContext: 'Based on the last 90 days of recorded events at Project North.',
    evidence: [
      { reference: 'E1', title: 'Vehicle incident', context: 'Project North', href: '/events/EVT-1001' },
      { reference: 'E2', title: 'Vehicle observation', context: 'Project North', href: '/events/EVT-1002' },
      { reference: 'E3', title: 'Previous vehicle incident', context: 'Project North', href: '/events/EVT-1003' },
    ],
    relatedRecords: [{ id: 'ACT-2201', title: 'Review reversing procedure at laydown area', type: 'Corrective action (planned)' }],
    relevantKnowledge: [
      { id: 'DOC-401', title: 'Site Vehicle Movement Procedure', source: 'HSE Management System', verificationStatus: 'verified' },
    ],
  },
  'EVT-1002': {
    narrative: 'A site vehicle was observed exceeding the posted 10 mph limit on the internal haul road.',
    finding: 'Vehicle-related events have increased over the selected period at this site.',
    findingContext: 'Based on the last 90 days of recorded events at Project North.',
    evidence: [
      { reference: 'E1', title: 'Vehicle incident', context: 'Project North', href: '/events/EVT-1001' },
      { reference: 'E2', title: 'Vehicle observation', context: 'Project North', href: '/events/EVT-1002' },
      { reference: 'E3', title: 'Previous vehicle incident', context: 'Project North', href: '/events/EVT-1003' },
    ],
    relatedRecords: [],
    relevantKnowledge: [],
  },
  'EVT-1003': {
    narrative: 'A delivery vehicle came within close proximity of a pedestrian crossing point. No contact occurred.',
    finding: 'Vehicle-related events have increased over the selected period at this site.',
    findingContext: 'Based on the last 90 days of recorded events at Project North.',
    evidence: [
      { reference: 'E1', title: 'Vehicle incident', context: 'Project North', href: '/events/EVT-1001' },
      { reference: 'E2', title: 'Vehicle observation', context: 'Project North', href: '/events/EVT-1002' },
      { reference: 'E3', title: 'Previous vehicle incident', context: 'Project North', href: '/events/EVT-1003' },
    ],
    relatedRecords: [],
    relevantKnowledge: [],
  },
};

export function buildFixtureDetail(summary: SafetyEventSummary): SafetyEventDetail {
  const override = DETAIL_OVERRIDES[summary.id];
  return {
    ...summary,
    narrative: override?.narrative ?? 'No narrative was recorded for this event.',
    finding: override?.finding ?? null,
    findingContext: override?.findingContext,
    evidence: override?.evidence ?? [],
    relatedRecords: override?.relatedRecords ?? [],
    relevantKnowledge: override?.relevantKnowledge ?? [],
  };
}
