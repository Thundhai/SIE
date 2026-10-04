import { ReactNode, useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { listAuthOrganizations } from '../services/api/auth';
import { ApiError } from '../services/api/errors';
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
 * The authenticated SIE workspace (`children`) is never rendered until
 * `ProdAuthProvider`'s own context value flips to `isAuthenticated: true`
 * (see `<AuthenticatedGate>` below) — satisfying this milestone's own
 * "must not render the authenticated workspace before the production
 * session is resolved" requirement independently of this gate's own
 * phase tracking.
 */
export function ProductionSessionGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const oidc = useOidcSession();
  const [gate, setGate] = useState<GateState>({ phase: 'loading' });

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
          <AuthenticatedGate>{children}</AuthenticatedGate>
        </ProdAuthProvider>
      );
  }
}

/** The literal "do not render the workspace before the session is
 * resolved" gate — rendered inside `ProdAuthProvider`, so it reads that
 * provider's own, already-existing `isAuthenticated` resolution rather
 * than this module tracking a second copy of it. */
function AuthenticatedGate({ children }: { children: ReactNode }) {
  const auth = useAuth();
  if (!auth.isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingState label="Loading your workspace…" />
      </div>
    );
  }
  return <>{children}</>;
}
