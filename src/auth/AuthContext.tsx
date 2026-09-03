import { createContext, useContext } from 'react';
import type { AuthContextValue } from './types';

/** No default value — every consumer must render under a real provider
 * (DevAuthProvider today; a future ProdAuthProvider later). Reading the
 * context outside one is a programming error, not a state to render
 * around, so `useAuth()` throws rather than silently returning a
 * fabricated "logged out" value. */
export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth() must be called within an <AuthProvider> (see auth/DevAuthProvider.tsx).');
  }
  return value;
}
