/**
 * Session-invalidation notification — SIE Milestone G3-2.
 *
 * Mirrors `authToken.ts`'s own "one pluggable, registered callback"
 * shape exactly, for the same reason: `services/api/client.ts` and the
 * production session owner (`ProductionSessionGate.tsx`) need one
 * un-duplicated channel to agree through, not two independent guesses.
 *
 * **Why this exists.** G3-1 already handles a 401 from its own
 * bootstrap calls (`listAuthOrganizations`, `/auth/me`) by signing out
 * locally and returning to `/login` — but only for those specific call
 * sites. A 401 from an *ordinary* feature page's own API call, later in
 * an otherwise-healthy session (the backend's token genuinely expired
 * or was revoked mid-session), previously just surfaced as that page's
 * own generic error — never returning the user to `/login`, the
 * required behavior for *any* 401 (`backend/app/api/deps_auth.py`'s own
 * semantics: 401 always and only means "this credential is no longer
 * valid", never anything else). `client.ts` calls
 * `notifySessionInvalidated()` on every 401 it sees, from any call;
 * `ProductionSessionGate` is the one registrant, reacting with its
 * already-existing `signOutLocally()` + "unauthenticated" transition.
 *
 * **Safe to fire redundantly.** G3-1's own bootstrap-call 401 handling
 * is untouched and still runs; this notification arriving at the same
 * moment for the same failure is a harmless, idempotent duplicate (see
 * `ProductionSessionGate.tsx`'s own registration) — never a second,
 * competing decision.
 *
 * **Inert in dev mode.** `DevAuthProvider` never registers a handler
 * here (dev identity has no OIDC session to invalidate — see that
 * module's own fallback-to-not-authenticated behavior for its own
 * calls), so a 401 during a dev-mode session simply reaches no handler
 * and changes nothing — production session-invalidation behavior never
 * depends on `DEV_MODE`.
 */

export type SessionInvalidationHandler = () => void;

let currentHandler: SessionInvalidationHandler | null = null;

/** Registers (or clears, with `null`) the function called whenever any
 * API request receives a 401. Call this once, from the one component
 * that owns the production session — never from a page/feature
 * component. */
export function registerSessionInvalidationHandler(handler: SessionInvalidationHandler | null): void {
  currentHandler = handler;
}

/** Called by `services/api/client.ts` on every 401 response, from any
 * request. */
export function notifySessionInvalidated(): void {
  currentHandler?.();
}
