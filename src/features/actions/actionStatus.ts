import type { StatusTone } from '../../types/common';
import type { PriorityLevel } from '../../components/ui/PriorityBadge';
import type { ActionPriority, ActionStatus, ActionType } from '../../types/actions';

/**
 * Status/priority/type tone-and-label mapping for the Actions screens —
 * mirrors `eventStatus.ts`'s own role. Unlike that module, the source
 * values here ARE closed, governed backend enums (see `types/actions.ts`'s
 * own docstring), so every mapping below is total (a `Record` over the
 * full union, not a partial lookup with a generic fallback) — there is
 * no "unknown status" case to design for.
 */

const STATUS_TONE: Record<ActionStatus, StatusTone> = {
  OPEN: 'informational',
  IN_PROGRESS: 'warning',
  BLOCKED: 'critical',
  COMPLETED: 'success',
  CANCELLED: 'neutral',
};

const STATUS_LABEL: Record<ActionStatus, string> = {
  OPEN: 'Open',
  IN_PROGRESS: 'In progress',
  BLOCKED: 'Blocked',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
};

export function actionStatusTone(status: ActionStatus): StatusTone {
  return STATUS_TONE[status];
}

export function actionStatusLabel(status: ActionStatus): string {
  return STATUS_LABEL[status];
}

const PRIORITY_LEVEL: Record<ActionPriority, PriorityLevel> = {
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
  CRITICAL: 'critical',
};

const PRIORITY_LABEL: Record<ActionPriority, string> = {
  LOW: 'Low',
  MEDIUM: 'Medium',
  HIGH: 'High',
  CRITICAL: 'Critical',
};

/** Maps the backend's UPPERCASE `ActionPriority` value onto
 * `PriorityBadge`'s own lowercase `PriorityLevel` prop — the shared
 * badge component is reused unchanged (§11), so the mapping lives here
 * instead. */
export function toPriorityLevel(priority: ActionPriority): PriorityLevel {
  return PRIORITY_LEVEL[priority];
}

const TYPE_LABEL: Record<ActionType, string> = {
  CORRECTIVE: 'Corrective',
  PREVENTIVE: 'Preventive',
  INVESTIGATION: 'Investigation',
  FOLLOW_UP: 'Follow-up',
  CONTROL_IMPROVEMENT: 'Control improvement',
  OTHER: 'Other',
};

export function actionTypeLabel(type: ActionType): string {
  return TYPE_LABEL[type];
}

export const ACTION_STATUS_OPTIONS: { value: ActionStatus; label: string }[] = (
  Object.keys(STATUS_LABEL) as ActionStatus[]
).map((value) => ({ value, label: STATUS_LABEL[value] }));

export const ACTION_PRIORITY_OPTIONS: { value: ActionPriority; label: string }[] = (
  Object.keys(PRIORITY_LABEL) as ActionPriority[]
).map((value) => ({ value, label: PRIORITY_LABEL[value] }));

export const ACTION_TYPE_OPTIONS: { value: ActionType; label: string }[] = (
  Object.keys(TYPE_LABEL) as ActionType[]
).map((value) => ({ value, label: TYPE_LABEL[value] }));

export const ACTION_TERMINAL_STATUSES: readonly ActionStatus[] = ['COMPLETED', 'CANCELLED'];

/**
 * A **non-authoritative UI convenience only**. Mirrors the backend's own
 * transition table (`app/models/safety_action_enums.py::_ALLOWED_TRANSITIONS`)
 * purely so the "Change status" control can hide obviously-invalid
 * target options and so `FixtureActionRepository` can behave the same
 * way the real API does when no backend is present. The real backend's
 * response to `POST /actions/{id}/status` remains the sole authority on
 * whether a transition actually succeeds — this table is never treated
 * as ground truth by `ApiActionRepository` or `ActionDetailPage`, which
 * always wait for that response (or its error) rather than assuming
 * success (milestone §6).
 */
const ALLOWED_TRANSITIONS: Record<ActionStatus, readonly ActionStatus[]> = {
  OPEN: ['IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED'],
  IN_PROGRESS: ['BLOCKED', 'COMPLETED', 'CANCELLED'],
  BLOCKED: ['IN_PROGRESS', 'COMPLETED', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
};

export function suggestedNextStatuses(current: ActionStatus): readonly ActionStatus[] {
  return ALLOWED_TRANSITIONS[current];
}

export function isAllowedActionTransition(current: ActionStatus, next: ActionStatus): boolean {
  return ALLOWED_TRANSITIONS[current].includes(next);
}
