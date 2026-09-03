import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from './client';
import { ApiError } from './errors';

describe('apiRequest', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.unstubAllEnvs();
  });

  it('parses a successful JSON response', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'org1', name: 'Test Org' }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );

    const result = await apiRequest<{ id: string; name: string }>('/organizations/org1');
    expect(result).toEqual({ id: 'org1', name: 'Test Org' });
  });

  it('normalizes the backend error contract ({ error: { code, message, request_id } }) into an ApiError', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: 'Organization not found', error: { code: 'RESOURCE_NOT_FOUND', message: 'Organization not found', request_id: 'req-123' } }),
        { status: 404, headers: { 'Content-Type': 'application/json', 'X-Request-Id': 'req-123' } },
      ),
    );

    await expect(apiRequest('/organizations/does-not-exist')).rejects.toMatchObject({
      status: 404,
      code: 'RESOURCE_NOT_FOUND',
      message: 'Organization not found',
      requestId: 'req-123',
    });
  });

  it('normalizes a network failure (e.g. CORS-blocked or unreachable backend) into an ApiError with isNetworkError=true', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    const error = await apiRequest('/organizations/org1').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).isNetworkError).toBe(true);
  });

  it('sends the configured dev-identity header when one is configured', async () => {
    vi.stubEnv('VITE_DEV_USER_ID', 'user-1');
    vi.stubEnv('VITE_DEV_ORGANIZATION_ID', 'org-1');
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    global.fetch = fetchMock;

    await apiRequest('/organizations/org-1');

    const [, init] = fetchMock.mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get('X-SIE-Dev-User-Id')).toBe('user-1');
  });

  it('never sends the dev-identity header when none is configured', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    global.fetch = fetchMock;

    await apiRequest('/organizations/org-1');

    const [, init] = fetchMock.mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get('X-SIE-Dev-User-Id')).toBeNull();
  });
});
