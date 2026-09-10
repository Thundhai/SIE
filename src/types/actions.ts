/**
 * Actions/Intervention domain types — SIE Milestone 18: Actions &
 * Intervention UX & API Integration v0.1. Adopted by both
 * `FixtureActionRepository` and the real `ApiActionRepository` through
 * the shared `ActionRepository` interface
 * (`src/features/actions/actionRepository.ts`), so `ActionsPage`/
 * `ActionDetailPage` never reshape around which one is active — mirrors
 * `types/events.ts`'s own pattern exactly.
 *
 * Unlike `SafetyEventSummary.status` (deliberately free text — see
 * `types/events.ts`'s own docstring), `ActionStatus`/`ActionPriority`/
 * `ActionType` ARE governed, closed vocabularies on the backend
 * (`backend/app/models/safety_action_enums.py`'s own docstring is
 * explicit about this), so these are real closed unions here, matching
 * the backend's native enum values verbatim — never invented, never
 * loosened to `string`.
 */

export type ActionStatus = 'OPEN' | 'IN_PROGRESS' | 'BLOCKED' | 'COMPLETED' | 'CANCELLED';
export type ActionPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type ActionType = 'CORRECTIVE' | 'PREVENTIVE' | 'INVESTIGATION' | 'FOLLOW_UP' | 'CONTROL_IMPROVEMENT' | 'OTHER';

/**
 * One action, in full — mirrors `SafetyActionRead`
 * (`backend/app/schemas/actions.py`) field-for-field, camelCased.
 * `organization_id`/`created_by_api_client_id` are intentionally left
 * off this screen-facing shape: the organization is already implied by
 * the active session (never a user-editable field — §10), and which
 * caller created an action is not information either screen needs to
 * render. Internal database ids (`id`) ARE present, since the screens
 * need it to route/link, but it is never displayed as the record's
 * primary user-facing label — see `ActionDetailPage`'s own layout.
 */
export interface SafetyAction {
  id: string;
  siteId: string | null;
  siteName: string | null;
  sourceEventId: string | null;
  title: string;
  description: string | null;
  actionType: ActionType;
  priority: ActionPriority;
  status: ActionStatus;
  ownerUserId: string | null;
  /** Resolved server-side (`SafetyActionRead.owner_name`) — always the
   * real assignee name once an owner is set. See
   * `ApiActionRepository.listOwnerOptions()`'s own docstring for why
   * the *candidate list* for reassignment can't offer the same. */
  ownerName: string | null;
  dueDate: string | null;
  createdByUserId: string | null;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  cancelledAt: string | null;
  externalReference: string | null;
}
