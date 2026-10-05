import { ReactNode } from 'react';
import { getAuthMode } from './authMode';
import { DevAuthProvider } from './DevAuthProvider';
import { ProductionSessionGate } from './ProductionSessionGate';

/**
 * The one place `router.tsx` decides which of the two `AuthContextValue`
 * implementations the authenticated shell runs under — SIE Milestone
 * G3-1. Everything downstream (every page, `Sidebar`, `Header`, the
 * `useAuth()` hook itself) is completely unaware this decision exists;
 * it only ever sees a resolved `AuthContextValue` (`types.ts`).
 *
 * `getAuthMode()` (see that module's own docstring) is the sole switch:
 * never both providers mounted at once, and never a runtime toggle a
 * user or a request could influence — it is fixed for the lifetime of a
 * given build (`import.meta.env.MODE`), exactly mirroring the backend's
 * own `DEV_MODE` being a fixed deployment setting, not a per-request
 * choice.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  if (getAuthMode() === 'dev') {
    return <DevAuthProvider>{children}</DevAuthProvider>;
  }
  return <ProductionSessionGate>{children}</ProductionSessionGate>;
}
