/**
 * Normalized API error — mirrors the backend's own standardized error
 * contract (`backend/app/core/errors.py`):
 *
 *   { "detail": "...", "error": { "code": "...", "message": "...", "request_id": "..." } }
 *
 * Every error the API client throws is an `ApiError`, whether it came
 * from a non-2xx HTTP response, a network failure, or malformed JSON —
 * so a caller only ever has to handle one error type.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly requestId: string | null;

  constructor(message: string, options: { status: number; code?: string | null; requestId?: string | null }) {
    super(message);
    this.name = 'ApiError';
    this.status = options.status;
    this.code = options.code ?? null;
    this.requestId = options.requestId ?? null;
  }

  /** True for a connectivity failure (no response at all) rather than a
   * real HTTP error status — used to word loading/error states honestly
   * ("could not reach the server" vs. "the server refused the request"). */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

/**
 * The one place "was this specifically a permission problem" is decided
 * — SIE Milestone G3-2. Checks the real HTTP status (403), never the
 * error message text: a prior ad hoc pattern in a couple of pages
 * matched on `message.includes('permission')`, which is fragile (it
 * would misfire on any unrelated error whose text happens to contain
 * that word, and silently stop working if the backend's own wording
 * ever changes) and duplicated the same guess in more than one place.
 * See `KnowledgePage.tsx`/`RiskAssessmentDetailPage.tsx` for the two
 * call sites this replaces.
 */
export function isPermissionDeniedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403;
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const requestId = response.headers.get('X-Request-Id');
  let message = `Request failed with status ${response.status}`;
  let code: string | null = null;

  try {
    const body = await response.json();
    if (body && typeof body === 'object') {
      if (body.error && typeof body.error === 'object') {
        message = body.error.message || message;
        code = body.error.code || null;
      } else if (typeof body.detail === 'string') {
        message = body.detail;
      }
    }
  } catch {
    // Response body wasn't JSON (or was empty) — fall back to the
    // generic status-based message above rather than throwing a second
    // error while handling the first.
  }

  return new ApiError(message, { status: response.status, code, requestId });
}
