import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { getAuthMode } from './authMode';
import { getOidcUserManager } from './oidcSession';

type CallbackResult = { status: 'pending' } | { status: 'success' } | { status: 'error'; message: string };

/**
 * OIDC redirect target — SIE Milestone G3-1. Registered as this
 * deployment's `redirect_uri` (and reused as `silent_redirect_uri`, see
 * `oidcSession.ts`) with the configured provider.
 *
 * **Two distinct callers load this exact route:**
 *
 *   1. The top-level browser window, after an interactive
 *      `signinRedirect()` — must call `signinRedirectCallback()`, then
 *      navigate away from the `?code=...&state=...` URL entirely (never
 *      leave the authorization code sitting in the visible address bar
 *      — see the milestone's own "no access token in URL after callback
 *      processing" security requirement).
 *   2. A hidden iframe `oidc-client-ts`'s `automaticSilentRenew` opens
 *      periodically — must call `signinSilentCallback()` instead, and
 *      renders nothing a user would ever see (the iframe is invisible by
 *      construction; this still returns a minimal, inert element in
 *      case a provider ever renders it visibly for a moment).
 *
 * Distinguished via `window.self !== window.top` — oidc-client-ts's own
 * documented pattern for telling the two apart, since both load the
 * identical URL.
 */
export function CallbackPage() {
  const [result, setResult] = useState<CallbackResult>({ status: 'pending' });

  useEffect(() => {
    const manager = getOidcUserManager();
    if (!manager) {
      setResult({ status: 'error', message: 'Sign-in is not configured for this deployment.' });
      return;
    }

    const isSilentRenewFrame = typeof window !== 'undefined' && window.self !== window.top;

    const promise = isSilentRenewFrame ? manager.signinSilentCallback() : manager.signinRedirectCallback();

    promise
      .then(() => {
        setResult({ status: 'success' });
      })
      .catch((err: unknown) => {
        setResult({
          status: 'error',
          message: err instanceof Error ? err.message : 'Sign-in could not be completed.',
        });
      });
  }, []);

  if (getAuthMode() === 'dev') {
    return <Navigate to="/" replace />;
  }

  if (typeof window !== 'undefined' && window.self !== window.top) {
    // Silent-renew iframe — nothing to render for a human to see.
    return null;
  }

  if (result.status === 'success') {
    // Replaces the `?code=...&state=...` query entirely rather than
    // merely navigating on top of it.
    return <Navigate to="/" replace />;
  }

  if (result.status === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4">
        <div className="w-full max-w-sm">
          <ErrorState title="Sign-in failed" description={result.message} />
          <div className="mt-4 text-center">
            <a href="/login" className="text-sm font-medium text-navy-800 underline-offset-2 hover:underline">
              Back to sign in
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4">
      <LoadingState label="Completing sign-in…" />
    </div>
  );
}
