import type { Page } from '../../types/common';
import type { ActionPriority, ActionStatus, ActionType, SafetyAction } from '../../types/actions';

export interface ActionListParams {
  page: number;
  pageSize: number;
  status?: ActionStatus;
  priority?: ActionPriority;
  actionType?: ActionType;
  /** `FixtureActionRepository` matches this against a site's exact name;
   * `ApiActionRepository` treats it as a site id — mirrors
   * `EventListParams.site`'s own convention (`eventRepository.ts`). */
  site?: string;
  /** Restricts the list to actions raised from one safety event — used
   * by Event Detail's "Related action" section (milestone §8), never by
   * the Actions list screen itself. */
  sourceEventId?: string;
  search?: string;
}

export interface ActionOption {
  value: string;
  label: string;
}

/** Only the fields the real `PATCH /actions/{id}` endpoint accepts
 * (`SafetyActionUpdate` — `backend/app/schemas/actions.py`).
 * `source_event_id`, `organization_id`, `status`, and every audit/
 * timestamp field are deliberately absent — the backend schema itself
 * forbids them (`extra="forbid"`), and this interface never offers a
 * way to attempt setting them (milestone §5). `owner_user_id` is
 * deliberately absent too — reassignment is its own capability, gated
 * on `intervention:assign` rather than `intervention:manage`, and goes
 * through `ActionRepository.reassign()` instead (milestone §7). */
export interface UpdateActionInput {
  title?: string;
  description?: string | null;
  actionType?: ActionType;
  priority?: ActionPriority;
  siteId?: string | null;
  dueDate?: string | null;
  externalReference?: string | null;
}

/** Only the fields the real `POST /actions` endpoint accepts
 * (`SafetyActionCreate`). `organization_id`/`status`/every audit field
 * are not part of this shape for the same reason as `UpdateActionInput`
 * above — the backend schema itself has no such fields to set. */
export interface CreateActionInput {
  title: string;
  description?: string;
  actionType: ActionType;
  priority?: ActionPriority;
  ownerUserId?: string;
  siteId?: string;
  dueDate?: string;
  /** Set once, at creation, from Event Detail's "Create action" flow
   * (milestone §8) — never editable afterwards (§5: the backend treats
   * `source_event_id` as immutable, and `UpdateActionInput` above has no
   * such field). */
  sourceEventId?: string;
  externalReference?: string;
}

/**
 * The Actions/Action Detail screens' one data-access seam — mirrors
 * `EventRepository`'s own role (`eventRepository.ts`) exactly. Both
 * screens depend on this interface, never on a concrete implementation,
 * so swapping `FixtureActionRepository` for `ApiActionRepository`
 * changes exactly one function (`useActionRepository.ts`).
 */
export interface ActionRepository {
  list(params: ActionListParams): Promise<Page<SafetyAction>>;
  getById(id: string): Promise<SafetyAction | null>;
  create(input: CreateActionInput, idempotencyKey: string): Promise<SafetyAction>;
  update(id: string, input: UpdateActionInput): Promise<SafetyAction>;
  /** Sets or clears `owner_user_id` — the one field `update()`
   * deliberately excludes (see `UpdateActionInput`'s own docstring).
   * Callers must check `intervention:assign` before offering this (see
   * `ActionDetailPage`'s own reassignment control) — the backend
   * enforces the same requirement independently and authoritatively. */
  reassign(id: string, ownerUserId: string | null): Promise<SafetyAction>;
  /** The backend's status transition matrix
   * (`is_allowed_action_transition()`) is the sole authority on whether
   * `status` may legally move from its current value to `nextStatus`;
   * this call either succeeds with the new persisted state or throws —
   * callers must never assume success before it resolves (milestone
   * §6). */
  updateStatus(id: string, nextStatus: ActionStatus, comment?: string): Promise<SafetyAction>;
  /** Candidate values for the Actions screen's site filter and the
   * create/edit forms' site picker. */
  listSiteOptions(): Promise<ActionOption[]>;
  /** Candidate assignees for the owner/reassignment picker. See
   * `ApiActionRepository.listOwnerOptions()`'s own docstring for why
   * the real implementation can only label these by role + a short id
   * fragment, not by name. */
  listOwnerOptions(): Promise<ActionOption[]>;
  /** `true` for `FixtureActionRepository` — the one thing the screens
   * themselves are allowed to know about which implementation is
   * active, so they can honestly disclose example data (§15). */
  readonly isFixtureBacked: boolean;
}
