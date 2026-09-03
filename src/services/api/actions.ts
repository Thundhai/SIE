/**
 * Actions service — thin typed wrappers around the real backend
 * endpoints built in SIE Milestone 17 (Actions & Intervention Foundation
 * v0.1 — `backend/app/api/v1/actions.py`) and frozen there unchanged.
 * Response shapes mirror `SafetyActionRead`/`ActionListRead`
 * (`backend/app/schemas/actions.py`) field-for-field — nothing here is
 * invented. See `src/features/actions/apiActionRepository.ts` for how
 * these are adapted onto the screens' own `SafetyAction` shape.
 */
import { apiRequest } from './client';

export type ActionStatusValue = 'OPEN' | 'IN_PROGRESS' | 'BLOCKED' | 'COMPLETED' | 'CANCELLED';
export type ActionPriorityValue = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type ActionTypeValue = 'CORRECTIVE' | 'PREVENTIVE' | 'INVESTIGATION' | 'FOLLOW_UP' | 'CONTROL_IMPROVEMENT' | 'OTHER';

export interface ActionResponse {
  id: string;
  organization_id: string;
  site_id: string | null;
  site_name: string | null;
  source_event_id: string | null;
  title: string;
  description: string | null;
  action_type: ActionTypeValue;
  priority: ActionPriorityValue;
  status: ActionStatusValue;
  owner_user_id: string | null;
  owner_name: string | null;
  due_date: string | null;
  created_by_user_id: string | null;
  created_by_api_client_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
  external_reference: string | null;
  attributes: Record<string, unknown>;
}

export interface ActionListResponse {
  items: ActionResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ListActionsParams {
  organizationId: string;
  page: number;
  pageSize: number;
  status?: ActionStatusValue;
  priority?: ActionPriorityValue;
  actionType?: ActionTypeValue;
  siteId?: string;
  sourceEventId?: string;
  ownerUserId?: string;
  search?: string;
  signal?: AbortSignal;
}

export function listActions(params: ListActionsParams): Promise<ActionListResponse> {
  const {
    organizationId,
    page,
    pageSize,
    status,
    priority,
    actionType,
    siteId,
    sourceEventId,
    ownerUserId,
    search,
    signal,
  } = params;
  return apiRequest<ActionListResponse>('/actions', {
    query: {
      organization_id: organizationId,
      page,
      page_size: pageSize,
      status,
      priority,
      action_type: actionType,
      site_id: siteId,
      source_event_id: sourceEventId,
      owner_user_id: ownerUserId,
      search,
    },
    signal,
  });
}

export function getAction(organizationId: string, actionId: string, signal?: AbortSignal): Promise<ActionResponse> {
  return apiRequest<ActionResponse>(`/actions/${actionId}`, { query: { organization_id: organizationId }, signal });
}

export interface CreateActionBody {
  title: string;
  description?: string;
  action_type: ActionTypeValue;
  priority?: ActionPriorityValue;
  owner_user_id?: string;
  site_id?: string;
  due_date?: string;
  source_event_id?: string;
  external_reference?: string;
}

/** `idempotencyKey` is required, not optional — every create call in
 * this frontend goes through the backend's real `Idempotency-Key`
 * mechanism (`backend/app/core/idempotency.py`), never a second,
 * client-invented one (milestone §4/§14). Callers generate one key per
 * logical create attempt (e.g. `crypto.randomUUID()` once when a create
 * form/dialog opens) and reuse it across retries of that same attempt —
 * see `src/features/actions/apiActionRepository.ts::create()`. */
export function createAction(
  organizationId: string,
  body: CreateActionBody,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<ActionResponse> {
  return apiRequest<ActionResponse>('/actions', {
    method: 'POST',
    query: { organization_id: organizationId },
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    signal,
  });
}

export interface UpdateActionBody {
  title?: string;
  description?: string | null;
  action_type?: ActionTypeValue;
  priority?: ActionPriorityValue;
  owner_user_id?: string | null;
  site_id?: string | null;
  due_date?: string | null;
  external_reference?: string | null;
}

export function updateAction(
  organizationId: string,
  actionId: string,
  body: UpdateActionBody,
  signal?: AbortSignal,
): Promise<ActionResponse> {
  return apiRequest<ActionResponse>(`/actions/${actionId}`, {
    method: 'PATCH',
    query: { organization_id: organizationId },
    body,
    signal,
  });
}

export function updateActionStatus(
  organizationId: string,
  actionId: string,
  status: ActionStatusValue,
  comment?: string,
  signal?: AbortSignal,
): Promise<ActionResponse> {
  return apiRequest<ActionResponse>(`/actions/${actionId}/status`, {
    method: 'POST',
    query: { organization_id: organizationId },
    body: { status, comment },
    signal,
  });
}
