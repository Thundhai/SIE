import { ReactNode, useEffect, useState } from 'react';
import { getEffectivePermissions, listAuthOrganizations } from '../services/api/auth';
import { ApiError } from '../services/api/errors';
import { setAccessTokenGetter, type AccessTokenGetter } from './authToken';
import { AuthContext } from './AuthContext';
import type { AuthContextValue, AuthMembership } from './types';

/**
 * The authoritative outcome of this provider's own `/auth/me` +
 * `/auth/organizations` resolution — SIE Milestone G3-1 blocker
 * hardening. Deliberately NOT part of `AuthContextValue` (that stays
 * exactly as every existing consumer already expects: `isAuthenticated`
 * and nothing finer-grained) — this is an internal signal a *wrapper*
 * around `ProdAuthProvider` can use to distinguish "still resolving"
 * from "resolved" from "the backend said 401" from "the backend failed
 * for some other reason", none of which `isAuthenticated: false` alone
 * can tell apart. See `ProductionSessionGate.tsx` for the one consumer.
 */
export type ProdAuthBootstrapStatus =
  | { status: 'resolving' }
  | { status: 'resolved' }
  | { status: 'unauthorized' }
  | { status: 'error'; message: string };

const NOT_AUTHENTICATED: AuthContextValue = {
  isAuthenticated: false,
  isDevIdentity: false,
  user: null,
  organization: null,
  memberships: [],
  permissions: [],
  hasPermission: () => false,
};

/**
 * Production identity provider — SIE Milestone 20: Production
 * Authentication & Identity Foundation v0.1.
 *
 * Implements the exact same `AuthContextValue` interface `DevAuthProvider`
 * does (see `types.ts`) — no page, route, permission check, or API
 * repository needs to change to use this provider instead. It is
 * provider-neutral by construction: it never imports or references any
 * specific identity provider's SDK. Instead, the app wires it with:
 *
 *   - `getAccessToken` — a plain function returning the current bearer
 *     token (or `null`), supplied by whatever real login/session
 *     mechanism a deployment actually integrates (an OIDC client
 *     library, a cookie-backed session endpoint, ...). This is the one
 *     seam a real integration plugs into; nothing else in this component
 *     is provider-specific.
 *   - `organizationId` — the organization to resolve permissions for, or
 *     `null` before one has been chosen. Per the milestone's own "must
 *     explicitly handle organization selection" requirement, this
 *     provider never picks one on its own: `availableOrganizations` (via
 *     `GET /auth/organizations`) is exposed once a token is available so
 *     the app can render an explicit picker when a user belongs to more
 *     than one, and `organizationId` is supplied back once chosen.
 *
 * Registers `getAccessToken` with `auth/authToken.ts` so every API call
 * (via `services/api/client.ts`) automatically carries the token as
 * `Authorization: Bearer <token>` — no repository or feature component
 * ever touches the token directly.
 *
 * **Unauthenticated responses resolve to a clean auth state.** Exactly
 * like `DevAuthProvider`, any failure resolving identity (no token, a
 * 401 from `/auth/me`, a network error, ...) falls back to
 * `NOT_AUTHENTICATED` rather than surfacing a raw `ApiError` — the app
 * shell renders "not signed in", not a generic error screen.
 */
export function ProdAuthProvider({
  getAccessToken,
  organizationId,
  onBootstrapStatusChange,
  children,
}: {
  getAccessToken: AccessTokenGetter;
  organizationId: string | null;
  /** Optional — see `ProdAuthBootstrapStatus`'s own docstring. Existing
   * callers that don't pass this (every test and usage predating this
   * hardening) are completely unaffected: the public `AuthContextValue`
   * this provider produces is unchanged either way. */
  onBootstrapStatusChange?: (status: ProdAuthBootstrapStatus) => void;
  children: ReactNode;
}) {
  const [value, setValue] = useState<AuthContextValue>(NOT_AUTHENTICATED);

  useEffect(() => {
    setAccessTokenGetter(getAccessToken);
    return () => setAccessTokenGetter(null);
  }, [getAccessToken]);

  useEffect(() => {
    const token = getAccessToken();
    if (!token || !organizationId) {
      setValue(NOT_AUTHENTICATED);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    onBootstrapStatusChange?.({ status: 'resolving' });

    async function resolve() {
      try {
        const [effectivePermissions, organizations] = await Promise.all([
          getEffectivePermissions(organizationId!, controller.signal),
          listAuthOrganizations(controller.signal),
        ]);
        if (cancelled) return;

        const memberships: AuthMembership[] = organizations.memberships.map((m) => ({
          organizationId: m.organization_id,
          organizationName: m.organization_name,
          role: m.role,
        }));
        const permissionSet = new Set(effectivePermissions.permissions);

        setValue({
          isAuthenticated: true,
          isDevIdentity: false,
          user: {
            id: effectivePermissions.user_id,
            name: effectivePermissions.name,
            email: effectivePermissions.email,
          },
          organization: {
            id: effectivePermissions.organization_id,
            name: effectivePermissions.organization_name,
          },
          memberships,
          permissions: effectivePermissions.permissions,
          hasPermission: (permission) => permissionSet.has(permission),
        });
        onBootstrapStatusChange?.({ status: 'resolved' });
      } catch (err) {
        // No real session, an expired/invalid token, a 401 from the
        // backend, or a network failure -- all resolve to the same
        // clean "not authenticated" AuthContextValue (see this module's
        // own docstring), never a raw application error -- but the
        // *authoritative* outcome (401 vs. any other failure) is still
        // reported via onBootstrapStatusChange so a wrapper around this
        // provider can act on it without a second /auth/me request of
        // its own (SIE Milestone G3-1 blocker hardening).
        if (!cancelled) {
          setValue(NOT_AUTHENTICATED);
          if (err instanceof ApiError && err.status === 401) {
            onBootstrapStatusChange?.({ status: 'unauthorized' });
          } else {
            onBootstrapStatusChange?.({
              status: 'error',
              message: err instanceof ApiError ? err.message : 'Could not resolve your session.',
            });
          }
        }
      }
    }

    void resolve();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [getAccessToken, organizationId, onBootstrapStatusChange]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
