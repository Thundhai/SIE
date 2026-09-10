/**
 * API base configuration — SIE Frontend Foundation v0.1.
 *
 * Read from Vite env (`VITE_API_BASE_URL`), never hardcoded. The
 * fallback below is a LOCAL DEVELOPMENT default only (matches the
 * backend README's own `uvicorn app.main:app` default port) — it is not
 * a production URL and must not be treated as one. Set
 * `VITE_API_BASE_URL` explicitly for any non-local environment.
 */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000/api/v1';
