import type { ActionPriority, ActionStatus, ActionType, SafetyAction } from '../types/actions';

/**
 * Fixture safety-action data — SIE Milestone 18: Actions & Intervention
 * UX & API Integration v0.1.
 *
 * FICTIONAL DATA ONLY. No real enterprise records, owner names, or
 * titles appear anywhere in this file — every id, title, owner, and
 * comment below is invented for this milestone, mirroring
 * `src/fixtures/events.ts`'s own precedent exactly. This file exists
 * solely so the Actions/Action Detail screens have something honest to
 * show when no organization is established (no dev identity configured,
 * or it failed to resolve against the backend) — see
 * `FixtureActionRepository` and `src/fixtures/README.md`. It must never
 * be imported by anything outside `src/features/actions/` and its own
 * repository.
 */

const SITES = ['Project North', 'Bayview Terminal', 'Riverside Plant'] as const;

const OWNERS = ['Jordan Blake', 'Priya Anand', 'Marcus Feld', 'Amara Osei'] as const;

interface FixtureActionSeed {
  id: string;
  title: string;
  description: string;
  actionType: ActionType;
  priority: ActionPriority;
  status: ActionStatus;
  site: (typeof SITES)[number];
  owner: (typeof OWNERS)[number] | null;
  dueDate: string | null;
  sourceEventId: string | null;
  externalReference: string | null;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  cancelledAt: string | null;
}

const SEEDS: FixtureActionSeed[] = [
  {
    id: 'ACT-2001',
    // Distinct from the legacy Events fixture's own unrelated
    // `relatedRecords` example entry for this same event id
    // (`src/fixtures/events.ts`'s "Review reversing procedure at
    // laydown area") — the two are separate, deliberately
    // non-identical illustrative records (see `RelatedActionSection`'s
    // own docstring for why they're two different mechanisms).
    title: 'Review reversing procedure at the Project North laydown area',
    description:
      'Following a reversing vehicle incident, review and reissue the site reversing procedure with an updated banksman requirement.',
    actionType: 'CORRECTIVE',
    priority: 'HIGH',
    status: 'IN_PROGRESS',
    site: 'Project North',
    owner: 'Jordan Blake',
    dueDate: '2026-03-10',
    sourceEventId: 'EVT-1001',
    externalReference: 'CAPA-2201',
    createdAt: '2026-02-18T09:15:00Z',
    updatedAt: '2026-02-20T14:02:00Z',
    completedAt: null,
    cancelledAt: null,
  },
  {
    id: 'ACT-2002',
    title: 'Install edge protection at Bayview scaffold bay 4',
    description: 'Missing edge protection identified during a working-at-height observation. Install and inspect.',
    actionType: 'CORRECTIVE',
    priority: 'CRITICAL',
    status: 'OPEN',
    site: 'Bayview Terminal',
    owner: 'Priya Anand',
    dueDate: '2026-02-25',
    sourceEventId: 'EVT-1004',
    externalReference: null,
    createdAt: '2026-02-20T11:40:00Z',
    updatedAt: '2026-02-20T11:40:00Z',
    completedAt: null,
    cancelledAt: null,
  },
  {
    id: 'ACT-2003',
    title: 'Retrain electrical isolation procedure',
    description: 'Refresher training for the crew involved in the isolation procedure deviation.',
    actionType: 'PREVENTIVE',
    priority: 'MEDIUM',
    status: 'BLOCKED',
    site: 'Riverside Plant',
    owner: 'Marcus Feld',
    dueDate: '2026-03-01',
    sourceEventId: 'EVT-1006',
    externalReference: null,
    createdAt: '2026-02-16T08:30:00Z',
    updatedAt: '2026-02-22T09:10:00Z',
    completedAt: null,
    cancelledAt: null,
  },
  {
    id: 'ACT-2004',
    title: 'Audit permit documentation completeness',
    description: 'Follow-up review of permit records after an audit finding of incomplete documentation.',
    actionType: 'INVESTIGATION',
    priority: 'MEDIUM',
    status: 'COMPLETED',
    site: 'Riverside Plant',
    owner: 'Amara Osei',
    dueDate: '2026-02-15',
    sourceEventId: 'EVT-1011',
    externalReference: 'CAPA-2154',
    createdAt: '2026-02-03T10:00:00Z',
    updatedAt: '2026-02-14T16:45:00Z',
    completedAt: '2026-02-14T16:45:00Z',
    cancelledAt: null,
  },
  {
    id: 'ACT-2005',
    title: 'Update lockout/tagout signage',
    description: 'General housekeeping follow-up — replace faded lockout/tagout signage across the plant.',
    actionType: 'CONTROL_IMPROVEMENT',
    priority: 'LOW',
    status: 'CANCELLED',
    site: 'Riverside Plant',
    owner: null,
    dueDate: null,
    sourceEventId: null,
    externalReference: null,
    createdAt: '2026-01-20T09:00:00Z',
    updatedAt: '2026-01-28T13:20:00Z',
    completedAt: null,
    cancelledAt: '2026-01-28T13:20:00Z',
  },
  {
    id: 'ACT-2006',
    title: 'Confirm spill kit inventory at Bayview',
    description: 'Follow-up check on spill kit stock levels after a minor contained environmental event.',
    actionType: 'FOLLOW_UP',
    priority: 'LOW',
    status: 'OPEN',
    site: 'Bayview Terminal',
    owner: 'Priya Anand',
    dueDate: '2026-03-05',
    sourceEventId: 'EVT-1012',
    externalReference: null,
    createdAt: '2026-01-31T10:20:00Z',
    updatedAt: '2026-01-31T10:20:00Z',
    completedAt: null,
    cancelledAt: null,
  },
];

export const FIXTURE_ACTIONS: SafetyAction[] = SEEDS.map((seed) => ({
  id: seed.id,
  siteId: seed.site,
  siteName: seed.site,
  sourceEventId: seed.sourceEventId,
  title: seed.title,
  description: seed.description,
  actionType: seed.actionType,
  priority: seed.priority,
  status: seed.status,
  ownerUserId: seed.owner,
  ownerName: seed.owner,
  dueDate: seed.dueDate,
  createdByUserId: null,
  createdAt: seed.createdAt,
  updatedAt: seed.updatedAt,
  completedAt: seed.completedAt,
  cancelledAt: seed.cancelledAt,
  externalReference: seed.externalReference,
}));

export const FIXTURE_ACTION_SITE_OPTIONS = SITES.map((site) => ({ value: site, label: site }));

export const FIXTURE_ACTION_OWNER_OPTIONS = OWNERS.map((owner) => ({ value: owner, label: owner }));
