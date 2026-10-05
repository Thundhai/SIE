import { ReactNode, useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { getEffectivePermissions, listAuthOrganizations } from '../services/api/auth';
import { ApiError } from '../services/api/errors';
import { setAccessTokenGetter } from './authToken';
import { useAuth } from './AuthContext';
import { resolveInitialOrganization } from './organizationResolution';
import { useOidcSession } from './oidcSession';
import { ProdAuthProvider } from './ProdAuthProvider';

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
 * The authenticated SIE workspace (`children`) is never rendered until
 * `ProdAuthProvider`'s own context value flips to `isAuthenticated: true`
 * (see `<AuthenticatedGate>` below) — satisfying this milestone's own
 * "must not render the authenticated workspace before the production
 * session is resolved" requirement independently of this gate's own
 * phase tracking. `AuthenticatedGate` also runs its own `/auth/me` probe
 * so a definitive failure there (401, or any other backend error) is
 * never indistinguishable from "still loading" — see that component's
 * own docstring.
 */
export function ProductionSessionGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const oidc = useOidcSession();
  const [gate, setGate] = useState<GateState>({ phase: 'loading' });

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
        const resolution = resolveInitialOrganization(result.memberships);
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
        <ProdAuthProvider getAccessToken={oidc.getAccessTokenLive} organizationId={gate.organizationId}>
          <AuthenticatedGate organizationId={gate.organizationId} signOutLocally={oidc.signOutLocally}>
            {children}
          </AuthenticatedGate>
        </ProdAuthProvider>
      );
  }
}

type BootstrapOutcome = { kind: 'expired' } | { kind: 'error'; message: string };

/**
 * Blocker fix: "do not render the workspace before the session is
 * resolved" — but `ProdAuthProvider`'s own `AuthContextValue` contract
 * is deliberately binary (`isAuthenticated: true` or not — see that
 * component's own docstring) and gives no way to tell "still resolving"
 * apart from "definitively failed" (a 401, or any other backend error,
 * from its internal `/auth/me` call both just become `NOT_AUTHENTICATED`
 * silently). Left alone, that makes a genuine failure here indistinguishable
 * from "still loading" forever.
 *
 * Rather than turning `ProdAuthProvider` itself into a larger state
 * machine (preserving its existing, provider-neutral contract exactly,
 * per this milestone's own rule), this boundary runs its own, independent
 * `GET /auth/me` probe — purely to observe success/401/other-failure,
 * never to extract permissions for the app to use (those still come
 * exclusively from `ProdAuthProvider`'s own `AuthContext` once it
 * resolves) — so a real failure here gets a deterministic outcome
 * instead of an indefinite spinner. This mirrors the identical,
 * already-established pattern `ProductionSessionGate`'s own upfront
 * `listAuthOrganizations()` call uses for exactly the same reason.
 */
function AuthenticatedGate({
  organizationId,
  signOutLocally,
  children,
}: {
  organizationId: string;
  signOutLocally: () => Promise<void>;
  children: ReactNode;
}) {
  const auth = useAuth();
  const [outcome, setOutcome] = useState<BootstrapOutcome | null>(null);

  useEffect(() => {
    if (auth.isAuthenticated) {
      // ProdAuthProvider's own identical call already succeeded --
      // nothing left for this probe to usefully detect.
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    getEffectivePermissions(organizationId, controller.signal).catch(async (err: unknown) => {
      if (cancelled) return;
      if (err instanceof ApiError && err.status === 401) {
        // Requirement: "/auth/me 401 -> session becomes unauthenticated
        // -> user is returned to /login" -- the token was valid moments
        // ago (ProductionSessionGate's own organizations probe already
        // confirmed that) but no longer is; clear the OIDC session so
        // the next visit doesn't repeat the same failed bootstrap.
        await signOutLocally();
        if (!cancelled) setOutcome({ kind: 'expired' });
        return;
      }
      setOutcome({
        kind: 'error',
        message: err instanceof ApiError ? err.message : 'Could not load your workspace.',
      });
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [auth.isAuthenticated, organizationId, signOutLocally]);

  if (outcome?.kind === 'expired') {
    return <Navigate to="/login" replace />;
  }

  if (outcome?.kind === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-sm">
          <ErrorState title="Could not load your workspace" description={outcome.message} />
        </div>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingState label="Loading your workspace…" />
      </div>
    );
  }

  return <>{children}</>;
}
