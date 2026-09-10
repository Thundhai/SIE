import type { ReactNode } from 'react';
import { AuthContext } from '../auth/AuthContext';
import type { AuthContextValue } from '../auth/types';

/** The same "not authenticated" shape `DevAuthProvider` itself falls
 * back to (never a fabricated user/org) — the default for any test that
 * doesn't care about identity, so `useEventRepository()` (and anything
 * else reading `useAuth()`) resolves to fixture-backed behavior without
 * every unrelated test needing to know that. */
export const NOT_AUTHENTICATED_AUTH_VALUE: AuthContextValue = {
  isAuthenticated: false,
  isDevIdentity: true,
  user: null,
  organization: null,
  memberships: [],
  permissions: [],
  hasPermission: () => false,
};

/** Renders `children` under a real `AuthContext.Provider` — every
 * screen under `useAuth()` (directly or via `useEventRepository()`)
 * needs one, since `useAuth()` throws outside a provider by design (see
 * `auth/AuthContext.tsx`). Pass `value` to override specific fields
 * (e.g. a resolved organization, to exercise the real-API repository
 * path) — anything unset keeps the not-authenticated defaults above. */
export function AuthProviderStub({
  value,
  children,
}: {
  value?: Partial<AuthContextValue>;
  children: ReactNode;
}) {
  return (
    <AuthContext.Provider value={{ ...NOT_AUTHENTICATED_AUTH_VALUE, ...value }}>{children}</AuthContext.Provider>
  );
}
