import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { ApiActionRepository } from './apiActionRepository';

vi.mock('../../services/api/actions', () => ({
  listActions: vi.fn(),
  getAction: vi.fn(),
  createAction: vi.fn(),
  updateAction: vi.fn(),
  updateActionStatus: vi.fn(),
}));
vi.mock('../../services/api/sites', () => ({
  listSites: vi.fn(),
}));
vi.mock('../../services/api/organizations', () => ({
  listMembers: vi.fn(),
}));

import { createAction, getAction, listActions, updateAction, updateActionStatus } from '../../services/api/actions';
import { listMembers } from '../../services/api/organizations';
import { listSites } from '../../services/api/sites';

const ORG_ID = 'org-1';

const ACTION_RESPONSE = {
  id: 'action-1',
  organization_id: ORG_ID,
  site_id: 'site-1',
  site_name: 'North Yard',
  source_event_id: 'evt-1',
  title: 'Review reversing procedure',
  description: 'Follow up on the reversing incident.',
  action_type: 'CORRECTIVE' as const,
  priority: 'HIGH' as const,
  status: 'OPEN' as const,
  owner_user_id: 'user-1',
  owner_name: 'Jordan Blake',
  due_date: '2026-03-10T00:00:00Z',
  created_by_user_id: 'user-2',
  created_by_api_client_id: null,
  created_at: '2026-02-18T09:15:00Z',
  updated_at: '2026-02-18T09:15:00Z',
  completed_at: null,
  cancelled_at: null,
  external_reference: 'CAPA-2201',
  attributes: {},
};

describe('ApiActionRepository', () => {
  it('is not fixture-backed', () => {
    expect(new ApiActionRepository(ORG_ID).isFixtureBacked).toBe(false);
  });

  it('list() maps the real response onto SafetyAction and forwards every filter', async () => {
    vi.mocked(listActions).mockResolvedValue({ items: [ACTION_RESPONSE], total: 1, page: 1, page_size: 10 });

    const page = await new ApiActionRepository(ORG_ID).list({
      page: 1,
      pageSize: 10,
      status: 'OPEN',
      priority: 'HIGH',
      actionType: 'CORRECTIVE',
      site: 'site-1',
      sourceEventId: 'evt-1',
      search: 'reversing',
    });

    expect(listActions).toHaveBeenCalledWith({
      organizationId: ORG_ID,
      page: 1,
      pageSize: 10,
      status: 'OPEN',
      priority: 'HIGH',
      actionType: 'CORRECTIVE',
      siteId: 'site-1',
      sourceEventId: 'evt-1',
      search: 'reversing',
    });
    expect(page.total).toBe(1);
    expect(page.items[0]).toMatchObject({
      id: 'action-1',
      title: 'Review reversing procedure',
      status: 'OPEN',
      priority: 'HIGH',
      ownerName: 'Jordan Blake',
      siteName: 'North Yard',
      sourceEventId: 'evt-1',
    });
  });

  it('getById() returns the full detail', async () => {
    vi.mocked(getAction).mockResolvedValue(ACTION_RESPONSE);

    const detail = await new ApiActionRepository(ORG_ID).getById('action-1');

    expect(getAction).toHaveBeenCalledWith(ORG_ID, 'action-1');
    expect(detail).toMatchObject({ id: 'action-1', title: 'Review reversing procedure' });
  });

  it('getById() returns null for a 404 (nonexistent or cross-tenant) rather than throwing', async () => {
    vi.mocked(getAction).mockRejectedValue(new ApiError('Action not found.', { status: 404 }));

    const detail = await new ApiActionRepository(ORG_ID).getById('does-not-exist');

    expect(detail).toBeNull();
  });

  it('getById() rethrows a non-404 failure rather than silently treating it as not-found', async () => {
    vi.mocked(getAction).mockRejectedValue(new ApiError('Server error.', { status: 500 }));

    await expect(new ApiActionRepository(ORG_ID).getById('action-1')).rejects.toThrow('Server error.');
  });

  it('create() forwards a real Idempotency-Key and every create field to the API client', async () => {
    vi.mocked(createAction).mockResolvedValue(ACTION_RESPONSE);

    await new ApiActionRepository(ORG_ID).create(
      { title: 'Review reversing procedure', actionType: 'CORRECTIVE', priority: 'HIGH', sourceEventId: 'evt-1' },
      'idempotency-key-123',
    );

    expect(createAction).toHaveBeenCalledWith(
      ORG_ID,
      expect.objectContaining({ title: 'Review reversing procedure', action_type: 'CORRECTIVE', source_event_id: 'evt-1' }),
      'idempotency-key-123',
    );
  });

  it('update() never sends owner_user_id, source_event_id, organization_id, or status — only PATCH-supported fields', async () => {
    vi.mocked(updateAction).mockResolvedValue(ACTION_RESPONSE);

    await new ApiActionRepository(ORG_ID).update('action-1', { title: 'New title', priority: 'CRITICAL' });

    const [, , body] = vi.mocked(updateAction).mock.calls[0];
    expect(body).not.toHaveProperty('owner_user_id');
    expect(body).not.toHaveProperty('source_event_id');
    expect(body).not.toHaveProperty('organization_id');
    expect(body).not.toHaveProperty('status');
    expect(body).toMatchObject({ title: 'New title', priority: 'CRITICAL' });
  });

  it('reassign() sets owner_user_id via the same PATCH endpoint, and can clear it', async () => {
    vi.mocked(updateAction).mockResolvedValue(ACTION_RESPONSE);

    await new ApiActionRepository(ORG_ID).reassign('action-1', 'user-9');
    expect(updateAction).toHaveBeenLastCalledWith(ORG_ID, 'action-1', { owner_user_id: 'user-9' });

    await new ApiActionRepository(ORG_ID).reassign('action-1', null);
    expect(updateAction).toHaveBeenLastCalledWith(ORG_ID, 'action-1', { owner_user_id: null });
  });

  it('updateStatus() forwards the target status and optional comment, never assuming success before the call resolves', async () => {
    vi.mocked(updateActionStatus).mockResolvedValue({ ...ACTION_RESPONSE, status: 'IN_PROGRESS' });

    const updated = await new ApiActionRepository(ORG_ID).updateStatus('action-1', 'IN_PROGRESS', 'Started work.');

    expect(updateActionStatus).toHaveBeenCalledWith(ORG_ID, 'action-1', 'IN_PROGRESS', 'Started work.');
    expect(updated.status).toBe('IN_PROGRESS');
  });

  it('updateStatus() rejects and never returns a value on a backend-refused transition', async () => {
    vi.mocked(updateActionStatus).mockRejectedValue(
      new ApiError('Cannot transition from COMPLETED to OPEN.', { status: 409 }),
    );

    await expect(new ApiActionRepository(ORG_ID).updateStatus('action-1', 'OPEN')).rejects.toThrow(
      'Cannot transition from COMPLETED to OPEN.',
    );
  });

  it('listSiteOptions() maps real sites to id/name option pairs', async () => {
    vi.mocked(listSites).mockResolvedValue([
      { id: 'site-1', name: 'North Yard', location: null, country: null, status: 'active', organization_id: ORG_ID },
    ]);

    const options = await new ApiActionRepository(ORG_ID).listSiteOptions();

    expect(options).toEqual([{ value: 'site-1', label: 'North Yard' }]);
  });

  it('listOwnerOptions() labels active members honestly by role and id fragment — never a fabricated name', async () => {
    vi.mocked(listMembers).mockResolvedValue([
      { id: 'm1', user_id: 'user-abcdefgh-1234', organization_id: ORG_ID, role: 'HSE_MANAGER', status: 'ACTIVE' },
      { id: 'm2', user_id: 'user-suspended', organization_id: ORG_ID, role: 'SITE_SUPERVISOR', status: 'SUSPENDED' },
    ]);

    const options = await new ApiActionRepository(ORG_ID).listOwnerOptions();

    expect(options).toEqual([{ value: 'user-abcdefgh-1234', label: 'HSE_MANAGER · user-abc' }]);
  });
});
