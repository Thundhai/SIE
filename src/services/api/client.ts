/**
 * Typed API client — the one place `fetch` is called from in the new SIE
 * frontend. No page/feature component calls `fetch` directly (SIE
 * Frontend Foundation v0.1, §11).
 *
 * Responsibilities:
 *  - base URL (services/api/config.ts)
 *  - dev-identity auth header (auth/devIdentity.ts) — swappable later for
 *    a real session mechanism without changing any caller
 *  - a client-generated request id, sent as `X-Client-Request-Id` and
 *    echoed by the backend's own `RequestIdMiddleware`
 *    (backend/app/core/request_id.py)
 *  - JSON encode/decode
 *  - normalizing every failure (HTTP error status OR network failure)
 *    into one `ApiError` type (services/api/errors.ts)
 */
import { getDevIdentityConfig } from '../../auth/devIdentity';
import { API_BASE_URL } from './config';
import { ApiError, apiErrorFromResponse } from './errors';

export type QueryValue = string | number | boolean | undefined | null;

export interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  query?: Record<string, QueryValue>;
  body?: unknown;
  signal?: AbortSignal;
  /** Extra request headers (e.g. `Idempotency-Key` — see
   * `services/api/actions.ts`'s own `createAction()`). Applied before
   * the base headers `buildHeaders()` always sets, so a caller-supplied
   * value can never shadow `Content-Type`/`Accept`/the request-id/dev-
   * identity headers. */
  headers?: Record<string, string>;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(path.replace(/^\//, ''), API_BASE_URL.endsWith('/') ? API_BASE_URL : `${API_BASE_URL}/`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

function buildHeaders(hasBody: boolean, extraHeaders?: Record<string, string>): Headers {
  const headers = new Headers();
  // Caller-supplied headers are applied first, so none of them can ever
  // shadow the base headers set below (Content-Type/Accept/the request-
  // id/dev-identity headers always win on a name collision).
  if (extraHeaders) {
    for (const [key, value] of Object.entries(extraHeaders)) {
      headers.set(key, value);
    }
  }
  if (hasBody) {
    headers.set('Content-Type', 'application/json');
  }
  headers.set('Accept', 'application/json');
  headers.set('X-Client-Request-Id', crypto.randomUUID());

  // Development-only identity header — mirrors backend/app/api/deps_auth.py's
  // own `DEV_USER_HEADER` convention exactly. Never sent if no dev
  // identity is configured; there is no other auth mechanism to fall
  // back to yet (see auth/types.ts's own docstring).
  const devIdentity = getDevIdentityConfig();
  if (devIdentity) {
    headers.set('X-SIE-Dev-User-Id', devIdentity.userId);
  }

  return headers;
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, signal, headers: extraHeaders } = options;
  const url = buildUrl(path, query);
  const headers = buildHeaders(body !== undefined, extraHeaders);

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (cause) {
    // No response at all (offline, DNS failure, CORS, backend not
    // running) — normalized to the same ApiError shape as an HTTP
    // error, distinguished via `isNetworkError`.
    const message = cause instanceof Error ? cause.message : 'Network request failed';
    throw new ApiError(`Could not reach the SIE API: ${message}`, { status: 0 });
  }

  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}
