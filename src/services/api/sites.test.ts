import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from './client';
import { listSites, type Site } from './sites';

vi.mock('./client', () => ({
  apiRequest: vi.fn(),
}));

function makeSites(count: number, offset = 0): Site[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `site-${offset + index}`,
    name: `Site ${offset + index}`,
    location: null,
    country: null,
    status: 'ACTIVE',
    organization_id: 'org-1',
  }));
}

describe('listSites pagination', () => {
  beforeEach(() => vi.clearAllMocks());

  it('requests the API maximum page size and continues until a short page', async () => {
    vi.mocked(apiRequest)
      .mockResolvedValueOnce(makeSites(500))
      .mockResolvedValueOnce(makeSites(2, 500));

    const result = await listSites('org-1');

    expect(result).toHaveLength(502);
    expect(apiRequest).toHaveBeenNthCalledWith(1, '/organizations/org-1/sites', {
      query: { skip: 0, limit: 500 },
      signal: undefined,
    });
    expect(apiRequest).toHaveBeenNthCalledWith(2, '/organizations/org-1/sites', {
      query: { skip: 500, limit: 500 },
      signal: undefined,
    });
  });

  it('returns immediately when the first page is shorter than the page size', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(makeSites(2));

    await expect(listSites('org-1')).resolves.toHaveLength(2);
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('does not issue a request when the supplied signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(listSites('org-1', controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
