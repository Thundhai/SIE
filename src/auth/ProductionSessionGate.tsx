import { ReactNode, useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { listAuthOrganizations } from '../services/api/auth';
import { ApiError } from '../services/api/errors';
import { setAccessTokenGetter } from './authToken';
import { registerSessionInvalidationHandler } from './sessionInvalidation';
import { readPersistedOrganizationId, resolveActiveOrganization } from './organizationPersistence';
import { useOidcSession } from './oidcSession';
import { ProdAuthProvider, type ProdAuthBootstrapStatus } from './ProdAuthProvider';

type GateState =
  | { phase: 'loading' }
  | { phase: 'unauthenticated' }
  | { phase: 'error'; message: string }
  | { phase: 'organization_setup_required' }
  | { phase: 'ready'; organizationId: string };

/**
 * Production session boundary — SIE Milestone G3-1. Wraps every
 * authenticated-shell route (see `router.tsx`); never wraps `/login` or
 * `/callback`, which must stay reachable regardless of session state.
 *
 * Session bootstrap sequence (this milestone's own required order):
 *
 *   1. `useOidcSession()` resolves whether a stored OIDC session exists
 *      at all (an access token — see `oidcSession.ts`).
 *   2. Once one does, this component itself calls `GET
 *      /auth/organizations` — the one call that both confirms the
 *      backend still honors the token (so a server-side-only expiry/
 *      revocation is caught here, not left to surface as a confusing
 *      failure deeper in the app) and resolves which organization to
 *      enter with (`organizationResolution.ts`) — `ProdAuthProvider`
 *      requires a concrete `organizationId` up front, so this has to
 *      happen before it can be constructed at all.
 *   3. Only then is `<ProdAuthProvider>` mounted, which performs its own
 *      existing, unchanged `/auth/me` + `/auth/organizations` resolution
 *      (see that component's own docstring) — this does not duplicate
 *      permission calculation, only the one upfront organization-list
 *      fetch, which is unavoidable without changing `ProdAuthProvider`'s
 *      contract (this milestone's own "preserve the existing
 *      ProdAuthProvider architecture" rule).
 *
 * **Token-registration bridge (blocker fix, see this module's own
 * second `useEffect` below).** Step 2's `listAuthOrganizations()` call
 * is a protected endpoint — it needs the production Bearer token
 * registered with `auth/authToken.ts` *before* it runs. `ProdAuthProvider`
 * is the "normal" registrant (unchanged — its own `useEffect` still
 * does this on mount), but it isn't mounted until *after* step 2
 * resolves. Without a second, earlier registration here, that first
 * call would go out with no `Authorization` header at all (and no dev
 * header either — `devIdentity.ts` correctly refuses to activate in
 * production), which the backend would correctly reject as 401 —
 * observed as "signing in immediately bounces back to /login". This
 * registers the exact same `getAccessTokenLive` function
 * `<ProdAuthProvider>` is later given below, so both registrations are
 * idempotent duplicates of each other whenever both are active, never
 * two different token sources.
 *
 * **The authoritative `/auth/me` outcome (blocker hardening).**
 * `ProdAuthProvider`'s own `/auth/me` + `/auth/organizations` call is
 * the *only* one — this component does not run a second, independent
 * probe of its own (an earlier version of this fix did, which could
 * legitimately disagree with the provider's real result and leave the
 * workspace stuck loading forever on a race). Instead,
 * `ProdAuthProvider` reports its own real outcome via
 * `onBootstrapStatusChange` (see that component's own docstring for why
 * this is a separate signal from the public `AuthContextValue`, which
 * stays exactly as every existing consumer already expects). The
 * authenticated SIE workspace (`children`) is rendered only once that
 * outcome is `'resolved'` — never merely because `isAuthenticated`
 * happens to be true, and never left indistinguishable from "still
 * loading" on a `401` or any other failure.
 */
export function ProductionSessionGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const oidc = useOidcSession();
  const [gate, setGate] = useState<GateState>({ phase: 'loading' });
  const [bootstrapStatus, setBootstrapStatus] = useState<ProdAuthBootstrapStatus>({ status: 'resolving' });

  // Blocker fix: register the production token source as soon as the
  // OIDC layer itself is authenticated — declared, and therefore run by
  // React, *before* the effect below that calls `listAuthOrganizations()`
  // (React runs a given component's own effects in declaration order
  // within the same commit). Cleanup fires only when `oidc.status`
  // itself stops being `'authenticated'` (session genuinely ended),
  // not on every gate-phase transition in between — `ProdAuthProvider`
  // mounting/unmounting around that same, stable window re-registers
  // the identical function, never races this one into leaving a still-
  // valid session with no getter registered.
  useEffect(() => {
    if (oidc.status !== 'authenticated') {
      return;
    }
    setAccessTokenGetter(oidc.getAccessTokenLive);
    return () => setAccessTokenGetter(null);
  }, [oidc.status, oidc.getAccessTokenLive]);

  // SIE Milestone G3-2: the one registrant of auth/sessionInvalidation.ts
  // -- a 401 from ANY later API call (not only the bootstrap calls this
  // component's own effects below already handle) reaches this same
  // signOutLocally(), which in turn flips oidc.status to
  // 'unauthenticated' and is picked up by the effect below exactly like
  // any other session end. Registered for the same window as the token
  // getter above (only while genuinely authenticated), for the same
  // reason.
  useEffect(() => {
    if (oidc.status !== 'authenticated') {
      return;
    }
    registerSessionInvalidationHandler(() => {
      void oidc.signOutLocally();
    });
    return () => registerSessionInvalidationHandler(null);
  }, [oidc.status, oidc.signOutLocally]);

  useEffect(() => {
    if (oidc.status === 'loading') {
      setGate({ phase: 'loading' });
      return;
    }
    if (oidc.status === 'unauthenticated') {
      setGate({ phase: 'unauthenticated' });
      return;
    }
    if (oidc.status === 'error') {
      setGate({ phase: 'error', message: oidc.error?.message ?? 'Could not resolve your session.' });
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    listAuthOrganizations(controller.signal)
      .then((result) => {
        if (cancelled) return;
        // SIE Milestone G3-3: prefer a persisted, still-valid active
        // organization (set by a previous session's explicit switch —
        // see organizationPersistence.ts) over G3-1's deterministic
        // pick, so a page refresh re-enters the organization the user
        // was actually last using rather than always the lowest-id one.
        // Discarding an invalid persisted id and resolving the
        // deterministic fallback both happen inside this one call —
        // see that module's own docstring.
        const resolution = resolveActiveOrganization(result.memberships, readPersistedOrganizationId());
        setGate(
          resolution.kind === 'none'
            ? { phase: 'organization_setup_required' }
            : { phase: 'ready', organizationId: resolution.organizationId },
        );
      })
      .catch(async (err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          // Requirement: "401 from /auth/me -> session becomes
          // unauthenticated -> user is returned to /login". The
          // organizations list is gated by the same authentication
          // dependency /auth/me is, so a 401 here means exactly the
          // same thing: the backend no longer honors this token.
          await oidc.signOutLocally();
          if (!cancelled) setGate({ phase: 'unauthenticated' });
          return;
        }
        setGate({
          phase: 'error',
          message: err instanceof ApiError ? err.message : 'Could not resolve your organizations.',
        });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [oidc.status, oidc.user, oidc.signOutLocally]);

  // Blocker hardening: react to ProdAuthProvider's own authoritative
  // 401, exactly like the organizations-probe's 401 handling above —
  // sign out locally and return to /login. This is the ONE place a
  // provider-reported 401 is acted on; there is no second observer.
  useEffect(() => {
    if (bootstrapStatus.status !== 'unauthorized') {
      return;
    }
    let cancelled = false;
    void (async () => {
      await oidc.signOutLocally();
      if (!cancelled) setGate({ phase: 'unauthenticated' });
    })();
    return () => {
      cancelled = true;
    };
  }, [bootstrapStatus.status, oidc.signOutLocally]);

  switch (gate.phase) {
    case 'loading':
      return (
        <div className="flex min-h-screen items-center justify-center">
          <LoadingState label="Resolving your session…" />
        </div>
      );

    case 'unauthenticated':
      return <Navigate to="/login" replace state={{ from: location }} />;

    case 'error':
      return (
        <div className="flex min-h-screen items-center justify-center px-4">
          <div className="w-full max-w-sm">
            <ErrorState title="Could not sign you in" description={gate.message} />
          </div>
        </div>
      );

    case 'organization_setup_required':
      return (
        <div className="flex min-h-screen items-center justify-center px-4">
          <div className="w-full max-w-sm">
            <ErrorState
              title="Organization setup required"
              description="Your account is signed in, but it does not yet belong to an organization. Contact your administrator to be added to one."
            />
          </div>
        </div>
      );

    case 'ready':
      return (
        <ProdAuthProvider
          getAccessToken={oidc.getAccessTokenLive}
          organizationId={gate.organizationId}
          onBootstrapStatusChange={setBootstrapStatus}
        >
          <BootstrapOutcomeGate status={bootstrapStatus}>{children}</BootstrapOutcomeGate>
        </ProdAuthProvider>
      );
  }
}

/**
 * Purely presentational: renders exactly one of {loading, the real
 * error, the authenticated workspace} based on `ProdAuthProvider`'s own
 * reported outcome — no probing, no state of its own. `'unauthorized'`
 * is handled by the `useEffect` above (sign out, transition `gate.phase`
 * away from `'ready'`, which unmounts this entire subtree); while that's
 * in flight this renders the same loading state as `'resolving'`, since
 * it's always momentary.
 */
function BootstrapOutcomeGate({ status, children }: { status: ProdAuthBootstrapStatus; children: ReactNode }) {
  if (status.status === 'resolved') {
    return <>{children}</>;
  }

  if (status.status === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-sm">
          <ErrorState title="Could not load your workspace" description={status.message} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <LoadingState label="Loading your workspace…" />
    </div>
  );
}
