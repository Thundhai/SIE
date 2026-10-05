/**
 * Production OIDC session — SIE Milestone G3-1: Login & Production
 * Session.
 *
 *     LoginPage.signIn() -> UserManager.signinRedirect()
 *         -> (redirect to the provider's own /authorize endpoint)
 *         -> provider redirects back to /callback?code=...&state=...
 *     CallbackPage -> UserManager.signinRedirectCallback()
 *         -> exchanges the code for tokens (Authorization Code + PKCE,
 *            RFC 7636 -- oidc-client-ts generates and verifies the PKCE
 *            verifier/challenge itself; nothing here handles a client
 *            secret, because a browser SPA is a public client and has
 *            none) -> User (access_token, profile, expires_at, ...)
 *     ProductionSessionGate -> useOidcSession() -> getAccessToken()
 *         -> registered with auth/authToken.ts, exactly like any other
 *            production token source -- ProdAuthProvider.tsx is
 *            completely unaware an OIDC library is involved at all.
 *
 * **Token storage.** `oidc-client-ts`'s `UserManager` persists the
 * current `User` (which embeds the access token) via its own
 * `userStore`. This is configured below to `sessionStorage`, never
 * `localStorage` -- sessionStorage survives a same-tab refresh (so a
 * session isn't lost on every reload) but is cleared on tab close and
 * never shared across origins/tabs the way `localStorage` is. No
 * component in this codebase ever reads that storage directly: every
 * access goes through `getAccessToken()` below, which asks the
 * `UserManager` for its current in-memory `User`, mirroring
 * `authToken.ts`'s existing "one source of truth, read live" shape
 * rather than caching a copy anywhere else.
 *
 * **Provider-neutral.** No specific identity provider's SDK is imported
 * anywhere in this module -- `oidc-client-ts` itself only speaks the
 * OIDC/OAuth2 standard (discovery, Authorization Code + PKCE, standard
 * token/userinfo shapes), the same posture `backend/app/services/
 * oidc_verifier.py` already takes with PyJWT on the backend.
 */
import {
  type SigninRedirectArgs,
  User,
  UserManager,
  UserManagerSettings,
  WebStorageStateStore,
} from 'oidc-client-ts';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getOidcConfig } from './oidcConfig';

let cachedUserManager: UserManager | null | undefined;

/** Lazily constructs the one `UserManager` this app uses, or `null` if
 * no OIDC provider is configured (see `oidcConfig.ts`). Cached at module
 * scope -- `oidc-client-ts` manages its own internal event wiring and
 * silent-renew timers, which must not be torn down and recreated every
 * time a component using `useOidcSession()` re-renders. */
export function getOidcUserManager(): UserManager | null {
  if (cachedUserManager !== undefined) {
    return cachedUserManager;
  }

  const config = getOidcConfig();
  if (!config) {
    cachedUserManager = null;
    return null;
  }

  const settings: UserManagerSettings = {
    authority: config.authority,
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    // Same redirect target as the interactive flow -- CallbackPage
    // itself distinguishes "running inside the silent-renew iframe"
    // from "the top-level interactive callback" (see its own
    // docstring) rather than this needing a second registered URI.
    silent_redirect_uri: config.redirectUri,
    scope: config.scope,
    response_type: 'code',
    automaticSilentRenew: true,
    // sessionStorage, never localStorage -- see this module's own
    // docstring.
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
  };

  cachedUserManager = new UserManager(settings);
  return cachedUserManager;
}

/** Test-only: forces the next `getOidcUserManager()` call to re-read
 * configuration and construct a fresh instance. Production code never
 * calls this -- the whole point of the module-level cache is that it's
 * never invalidated during a real app's lifetime. */
export function resetOidcUserManagerForTests(): void {
  cachedUserManager = undefined;
}

export type OidcSessionStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error';

export interface OidcSessionState {
  status: OidcSessionStatus;
  user: User | null;
  /** Set only when `status === 'error'` -- a problem distinct from
   * "not signed in" (no OIDC session exists yet, which is a normal,
   * expected state, not an error). See CallbackPage/ProductionSessionGate
   * for how each status is actually presented. */
  error: Error | null;
}

/**
 * React hook: the current OIDC session state, kept live via
 * `UserManager`'s own events (`userLoaded`/`userUnloaded`/
 * `silentRenewError`), plus `signIn()`/`signOut()` actions.
 *
 * Deliberately returns `'unauthenticated'` (never `'error'`) when there
 * simply is no stored session yet -- the ordinary "nobody has signed in
 * on this browser/tab yet" case, not a failure. `'error'` is reserved
 * for something going wrong while trying to resolve or renew a session
 * that was expected to exist (see `signOutLocally`'s own 401-driven call
 * site in `ProductionSessionGate.tsx`).
 */
export function useOidcSession(): OidcSessionState & {
  signIn: (args?: SigninRedirectArgs) => Promise<void>;
  signOutLocally: () => Promise<void>;
  getAccessTokenLive: () => string | null;
} {
  const [state, setState] = useState<OidcSessionState>({ status: 'loading', user: null, error: null });
  const userRef = useRef<User | null>(null);

  useEffect(() => {
    const manager = getOidcUserManager();
    if (!manager) {
      setState({ status: 'unauthenticated', user: null, error: null });
      return;
    }

    let cancelled = false;

    function applyUser(user: User | null) {
      userRef.current = user;
      if (cancelled) return;
      setState({
        status: user && !user.expired ? 'authenticated' : 'unauthenticated',
        user,
        error: null,
      });
    }

    manager
      .getUser()
      .then(applyUser)
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({ status: 'error', user: null, error: err instanceof Error ? err : new Error(String(err)) });
      });

    const onUserLoaded = (user: User) => applyUser(user);
    const onUserUnloaded = () => applyUser(null);
    const onSilentRenewError = () => {
      // A failed silent renew does not by itself prove the session is
      // invalid (it may be a transient network failure) -- this
      // deliberately does NOT force 'unauthenticated' or 'error' here.
      // The next API call's own 401 (handled by ProductionSessionGate)
      // is what authoritatively decides the session is no longer valid;
      // this hook stays a thin reflection of the UserManager's own
      // state, never a second place that guesses.
    };

    manager.events.addUserLoaded(onUserLoaded);
    manager.events.addUserUnloaded(onUserUnloaded);
    manager.events.addSilentRenewError(onSilentRenewError);

    return () => {
      cancelled = true;
      manager.events.removeUserLoaded(onUserLoaded);
      manager.events.removeUserUnloaded(onUserUnloaded);
      manager.events.removeSilentRenewError(onSilentRenewError);
    };
  }, []);

  const signIn = useCallback(async (args?: SigninRedirectArgs) => {
    const manager = getOidcUserManager();
    if (!manager) {
      throw new Error('OIDC is not configured for this deployment.');
    }
    await manager.signinRedirect(args);
  }, []);

  const signOutLocally = useCallback(async () => {
    const manager = getOidcUserManager();
    if (!manager) return;
    // Local session reset only -- see this module's own docstring's
    // "do not assume IdP logout" rationale. `removeUser()` clears the
    // stored User (and its tokens) and fires `userUnloaded`, which this
    // hook's own listener above turns into `status: 'unauthenticated'`.
    await manager.removeUser();
  }, []);

  const getAccessTokenLive = useCallback(() => {
    const user = userRef.current;
    return user && !user.expired ? user.access_token : null;
  }, []);

  return { ...state, signIn, signOutLocally, getAccessTokenLive };
}
