import { useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { getAuthMode } from './authMode';
import { useOidcSession } from './oidcSession';

interface LocationState {
  from?: { pathname: string };
}

/**
 * Production sign-in entry point — SIE Milestone G3-1.
 *
 * No credentials form of any kind (SIE never implements its own
 * username/password authentication — see this milestone's own
 * architectural rules): the single action below redirects to whichever
 * OIDC provider this deployment is configured against
 * (`oidcConfig.ts`); SIE itself never collects a password.
 *
 * Never rendered in dev mode at all in practice (`router.tsx` only
 * reaches this component on the production branch), but guarded here
 * too in case a dev build is ever navigated to `/login` directly — dev
 * identity resolves automatically with no login step, so there is
 * nothing for this page to do there.
 */
export function LoginPage() {
  const location = useLocation();
  const oidc = useOidcSession();
  const [signInError, setSignInError] = useState<string | null>(null);

  if (getAuthMode() === 'dev') {
    return <Navigate to="/" replace />;
  }

  // Requirement: "authenticated user visiting /login -> redirected to
  // application".
  if (oidc.status === 'authenticated') {
    const from = (location.state as LocationState | null)?.from?.pathname ?? '/';
    return <Navigate to={from} replace />;
  }

  async function handleSignIn() {
    setSignInError(null);
    try {
      await oidc.signIn();
    } catch (err) {
      setSignInError(
        err instanceof Error
          ? err.message
          : 'Sign-in is not available right now. Please contact your administrator.',
      );
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-8 shadow-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-navy-800 text-sm font-bold text-white">
            SIE
          </div>
          <div>
            <h1 className="text-lg font-semibold text-navy-900">Safety Intelligence Engine</h1>
            <p className="mt-1 text-sm text-text-secondary">Sign in to continue to your workspace.</p>
          </div>
        </div>

        {oidc.status === 'loading' ? (
          <div role="status" aria-live="polite" className="py-2 text-center text-sm text-text-secondary">
            Checking your session…
          </div>
        ) : (
          <Button
            type="button"
            variant="primary"
            className="w-full justify-center"
            autoFocus
            onClick={handleSignIn}
          >
            Sign in
          </Button>
        )}

        {signInError && (
          <p role="alert" className="mt-4 text-center text-sm text-critical">
            {signInError}
          </p>
        )}

        {oidc.status === 'error' && !signInError && (
          <p role="alert" className="mt-4 text-center text-sm text-critical">
            {oidc.error?.message ?? 'Could not check your session. Please try signing in.'}
          </p>
        )}
      </div>
    </div>
  );
}
