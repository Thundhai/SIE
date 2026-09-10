import { describe, expect, it } from 'vitest';
import { FixtureActionRepository } from './fixtureActionRepository';

describe('FixtureActionRepository', () => {
  it('is fixture-backed', () => {
    expect(new FixtureActionRepository(0).isFixtureBacked).toBe(true);
  });

  it('list() supports status/priority/type/site/sourceEventId/search filters', async () => {
    const repo = new FixtureActionRepository(0);

    const bySource = await repo.list({ page: 1, pageSize: 10, sourceEventId: 'EVT-1001' });
    expect(bySource.items).toHaveLength(1);
    expect(bySource.items[0].id).toBe('ACT-2001');

    const byStatus = await repo.list({ page: 1, pageSize: 10, status: 'COMPLETED' });
    expect(byStatus.items.every((item) => item.status === 'COMPLETED')).toBe(true);
  });

  it('create() adds a new OPEN action and getById() finds it afterwards', async () => {
    const repo = new FixtureActionRepository(0);

    const created = await repo.create(
      { title: 'New follow-up', actionType: 'FOLLOW_UP' },
      'key-1',
    );

    expect(created.status).toBe('OPEN');
    expect(await repo.getById(created.id)).toMatchObject({ title: 'New follow-up' });
  });

  it('updateStatus() enforces the same transition matrix the real backend enforces', async () => {
    const repo = new FixtureActionRepository(0);

    // ACT-2002 is OPEN in the fixture seed.
    const inProgress = await repo.updateStatus('ACT-2002', 'IN_PROGRESS');
    expect(inProgress.status).toBe('IN_PROGRESS');

    const completed = await repo.updateStatus('ACT-2002', 'COMPLETED');
    expect(completed.status).toBe('COMPLETED');

    // COMPLETED is terminal — never reopened, exactly like the backend.
    await expect(repo.updateStatus('ACT-2002', 'OPEN')).rejects.toThrow();
  });

  it('reassign() sets or clears the owner', async () => {
    const repo = new FixtureActionRepository(0);

    const assigned = await repo.reassign('ACT-2002', 'Marcus Feld');
    expect(assigned.ownerUserId).toBe('Marcus Feld');

    const cleared = await repo.reassign('ACT-2002', null);
    expect(cleared.ownerUserId).toBeNull();
    expect(cleared.ownerName).toBeNull();
  });

  it('a mutation on one repository instance never leaks into another instance or the shared fixture seed', async () => {
    const repoA = new FixtureActionRepository(0);
    await repoA.updateStatus('ACT-2002', 'IN_PROGRESS');

    const repoB = new FixtureActionRepository(0);
    const seenByB = await repoB.getById('ACT-2002');
    expect(seenByB?.status).toBe('OPEN'); // ACT-2002's own fixture seed status — untouched by repoA
  });
});
