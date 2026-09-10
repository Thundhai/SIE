import { listMembers } from '../../services/api/organizations';
import { ApiError } from '../../services/api/errors';
import {
  type ActionResponse,
  type CreateActionBody,
  type UpdateActionBody,
  createAction as apiCreateAction,
  getAction,
  listActions,
  updateAction,
  updateActionStatus,
} from '../../services/api/actions';
import { listSites } from '../../services/api/sites';
import type { Page } from '../../types/common';
import type { ActionStatus, SafetyAction } from '../../types/actions';
import type { ActionListParams, ActionOption, ActionRepository, CreateActionInput, UpdateActionInput } from './actionRepository';

/**
 * `ActionRepository` backed by the real backend
 * (`POST/GET/PATCH /api/v1/actions`, `POST /api/v1/actions/{id}/status`
 * — SIE Milestone 17: Actions & Intervention Foundation v0.1, frozen
 * unchanged by this milestone). Adopted by `ActionsPage`/
 * `ActionDetailPage` through the exact same interface
 * `FixtureActionRepository` implements — see `useActionRepository.ts`
 * for which one is actually selected. Mirrors `ApiEventRepository`'s
 * own structure exactly.
 */
export class ApiActionRepository implements ActionRepository {
  readonly isFixtureBacked = false;

  constructor(private readonly organizationId: string) {}

  async list(params: ActionListParams): Promise<Page<SafetyAction>> {
    const response = await listActions({
      organizationId: this.organizationId,
      page: params.page,
      pageSize: params.pageSize,
      status: params.status,
      priority: params.priority,
      actionType: params.actionType,
      siteId: params.site,
      sourceEventId: params.sourceEventId,
      search: params.search,
    });
    return {
      items: response.items.map(toDomain),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
    };
  }

  async getById(id: string): Promise<SafetyAction | null> {
    try {
      return toDomain(await getAction(this.organizationId, id));
    } catch (error) {
      // Mirrors ApiEventRepository.getById()'s own handling — a 404 here
      // covers both "no such action" and "belongs to another tenant"
      // identically, per the backend's own deliberate tenant-isolation
      // behavior (milestone §10 / actions.py's own docstring).
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }

  async create(input: CreateActionInput, idempotencyKey: string): Promise<SafetyAction> {
    const body: CreateActionBody = {
      title: input.title,
      description: input.description,
      action_type: input.actionType,
      priority: input.priority,
      owner_user_id: input.ownerUserId,
      site_id: input.siteId,
      due_date: input.dueDate,
      source_event_id: input.sourceEventId,
      external_reference: input.externalReference,
    };
    return toDomain(await apiCreateAction(this.organizationId, body, idempotencyKey));
  }

  async update(id: string, input: UpdateActionInput): Promise<SafetyAction> {
    const body: UpdateActionBody = {
      title: input.title,
      description: input.description,
      action_type: input.actionType,
      priority: input.priority,
      site_id: input.siteId,
      due_date: input.dueDate,
      external_reference: input.externalReference,
    };
    return toDomain(await updateAction(this.organizationId, id, body));
  }

  async reassign(id: string, ownerUserId: string | null): Promise<SafetyAction> {
    return toDomain(await updateAction(this.organizationId, id, { owner_user_id: ownerUserId }));
  }

  async updateStatus(id: string, nextStatus: ActionStatus, comment?: string): Promise<SafetyAction> {
    return toDomain(await updateActionStatus(this.organizationId, id, nextStatus, comment));
  }

  async listSiteOptions(): Promise<ActionOption[]> {
    const sites = await listSites(this.organizationId);
    return sites.map((site) => ({ value: site.id, label: site.name }));
  }

  /**
   * `GET /organizations/{id}/members` returns `OrganizationMembershipRead`
   * — `id`/`user_id`/`organization_id`/`role`/`status` only, no name or
   * email (`backend/app/schemas/organization_membership.py`), and the
   * backend has no `GET /users`/`GET /users/{id}` endpoint anywhere to
   * resolve one from. This milestone's own spec (§14) is explicit that
   * backend changes should be avoided unless integration exposes a
   * genuine *contract defect* — a name field the membership endpoint
   * never promised isn't one, so rather than adding a new endpoint or
   * field, candidates here are labeled honestly by role and a short id
   * fragment (`"HSE_MANAGER · 3f9a21b0"`), never a fabricated name.
   * Once an owner is actually assigned, the real name IS shown —
   * `SafetyActionRead.owner_name` is resolved server-side from the
   * User row directly (`app/api/v1/actions.py::_to_read`), so only the
   * *candidate list* for reassignment carries this limitation. See the
   * milestone's own completion report, "known limitations".
   */
  async listOwnerOptions(): Promise<ActionOption[]> {
    const members = await listMembers(this.organizationId);
    return members
      .filter((member) => member.status === 'ACTIVE')
      .map((member) => ({ value: member.user_id, label: `${member.role} · ${member.user_id.slice(0, 8)}` }));
  }
}

function toDomain(action: ActionResponse): SafetyAction {
  return {
    id: action.id,
    siteId: action.site_id,
    siteName: action.site_name,
    sourceEventId: action.source_event_id,
    title: action.title,
    description: action.description,
    actionType: action.action_type,
    priority: action.priority,
    status: action.status,
    ownerUserId: action.owner_user_id,
    ownerName: action.owner_name,
    dueDate: action.due_date,
    createdByUserId: action.created_by_user_id,
    createdAt: action.created_at,
    updatedAt: action.updated_at,
    completedAt: action.completed_at,
    cancelledAt: action.cancelled_at,
    externalReference: action.external_reference,
  };
}
