import { FIXTURE_ACTIONS, FIXTURE_ACTION_OWNER_OPTIONS, FIXTURE_ACTION_SITE_OPTIONS } from '../../fixtures/actions';
import type { Page } from '../../types/common';
import type { ActionStatus, SafetyAction } from '../../types/actions';
import { isAllowedActionTransition } from './actionStatus';
import type { ActionListParams, ActionOption, ActionRepository, CreateActionInput, UpdateActionInput } from './actionRepository';

let nextFixtureId = FIXTURE_ACTIONS.length + 1;

/**
 * `ActionRepository` backed by `src/fixtures/actions.ts` — mirrors
 * `FixtureEventRepository`'s own role and its small artificial delay
 * (so loading states are genuinely exercised outside tests, which pass
 * `latencyMs: 0` for determinism). Unlike the read-only Events fixture,
 * this one holds real mutable in-memory state: the Actions screens
 * support create/edit/status-change/reassignment even without a
 * backend, so local development without one still has a working
 * (if non-persistent) domain to exercise — including the SAME status
 * transition rules the real backend enforces (see
 * `actionStatus.ts::isAllowedActionTransition`), so an invalid
 * transition fails the same honest way here as it would against the
 * real API.
 */
export class FixtureActionRepository implements ActionRepository {
  readonly isFixtureBacked = true;

  private items: SafetyAction[];

  constructor(private readonly latencyMs = 250) {
    // Cloned once per instance so mutations in one test/session never
    // leak into FIXTURE_ACTIONS itself or another instance.
    this.items = FIXTURE_ACTIONS.map((action) => ({ ...action }));
  }

  private async delay(): Promise<void> {
    if (this.latencyMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.latencyMs));
    }
  }

  async list(params: ActionListParams): Promise<Page<SafetyAction>> {
    await this.delay();

    const search = params.search?.trim().toLowerCase();
    const filtered = this.items.filter((action) => {
      if (params.status && action.status !== params.status) return false;
      if (params.priority && action.priority !== params.priority) return false;
      if (params.actionType && action.actionType !== params.actionType) return false;
      if (params.site && action.siteName !== params.site) return false;
      if (params.sourceEventId && action.sourceEventId !== params.sourceEventId) return false;
      if (search) {
        const haystack = `${action.title} ${action.description ?? ''} ${action.externalReference ?? ''}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });

    const start = (params.page - 1) * params.pageSize;
    const items = filtered.slice(start, start + params.pageSize);
    return { items, total: filtered.length, page: params.page, pageSize: params.pageSize };
  }

  async getById(id: string): Promise<SafetyAction | null> {
    await this.delay();
    return this.items.find((action) => action.id === id) ?? null;
  }

  async create(input: CreateActionInput, _idempotencyKey?: string): Promise<SafetyAction> {
    void _idempotencyKey; // no real dedup to perform without a backend — see this class's own docstring.
    await this.delay();
    const now = new Date().toISOString();
    const owner = input.ownerUserId
      ? (FIXTURE_ACTION_OWNER_OPTIONS.find((option) => option.value === input.ownerUserId) ?? null)
      : null;
    const site = input.siteId ? (FIXTURE_ACTION_SITE_OPTIONS.find((option) => option.value === input.siteId) ?? null) : null;
    const action: SafetyAction = {
      id: `ACT-FX-${nextFixtureId++}`,
      siteId: site?.value ?? null,
      siteName: site?.label ?? null,
      sourceEventId: input.sourceEventId ?? null,
      title: input.title,
      description: input.description ?? null,
      actionType: input.actionType,
      priority: input.priority ?? 'MEDIUM',
      status: 'OPEN',
      ownerUserId: owner?.value ?? null,
      ownerName: owner?.label ?? null,
      dueDate: input.dueDate ?? null,
      createdByUserId: null,
      createdAt: now,
      updatedAt: now,
      completedAt: null,
      cancelledAt: null,
      externalReference: input.externalReference ?? null,
    };
    this.items = [action, ...this.items];
    return action;
  }

  async update(id: string, input: UpdateActionInput): Promise<SafetyAction> {
    await this.delay();
    const action = this.mustFind(id);
    const site = input.siteId !== undefined ? FIXTURE_ACTION_SITE_OPTIONS.find((option) => option.value === input.siteId) : undefined;
    const updated: SafetyAction = {
      ...action,
      title: input.title ?? action.title,
      description: input.description !== undefined ? input.description : action.description,
      actionType: input.actionType ?? action.actionType,
      priority: input.priority ?? action.priority,
      siteId: input.siteId !== undefined ? (input.siteId ?? null) : action.siteId,
      siteName: input.siteId !== undefined ? (site?.label ?? null) : action.siteName,
      dueDate: input.dueDate !== undefined ? input.dueDate : action.dueDate,
      externalReference: input.externalReference !== undefined ? input.externalReference : action.externalReference,
      updatedAt: new Date().toISOString(),
    };
    this.replace(updated);
    return updated;
  }

  async reassign(id: string, ownerUserId: string | null): Promise<SafetyAction> {
    await this.delay();
    const action = this.mustFind(id);
    const owner = ownerUserId ? (FIXTURE_ACTION_OWNER_OPTIONS.find((option) => option.value === ownerUserId) ?? null) : null;
    const updated: SafetyAction = {
      ...action,
      ownerUserId: owner?.value ?? null,
      ownerName: owner?.label ?? null,
      updatedAt: new Date().toISOString(),
    };
    this.replace(updated);
    return updated;
  }

  async updateStatus(id: string, nextStatus: ActionStatus): Promise<SafetyAction> {
    await this.delay();
    const action = this.mustFind(id);
    if (!isAllowedActionTransition(action.status, nextStatus)) {
      throw new Error(`Cannot change status from ${action.status} to ${nextStatus}.`);
    }
    const now = new Date().toISOString();
    const updated: SafetyAction = {
      ...action,
      status: nextStatus,
      completedAt: nextStatus === 'COMPLETED' ? now : action.completedAt,
      cancelledAt: nextStatus === 'CANCELLED' ? now : action.cancelledAt,
      updatedAt: now,
    };
    this.replace(updated);
    return updated;
  }

  async listSiteOptions(): Promise<ActionOption[]> {
    return FIXTURE_ACTION_SITE_OPTIONS;
  }

  async listOwnerOptions(): Promise<ActionOption[]> {
    return FIXTURE_ACTION_OWNER_OPTIONS;
  }

  private mustFind(id: string): SafetyAction {
    const action = this.items.find((item) => item.id === id);
    if (!action) throw new Error('Action not found.');
    return action;
  }

  private replace(updated: SafetyAction): void {
    this.items = this.items.map((item) => (item.id === updated.id ? updated : item));
  }
}
