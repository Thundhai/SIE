import { ReactNode } from 'react';
import { getAuthMode } from './authMode';
import { DevAuthProvider } from './DevAuthProvider';
import { OrganizationSwitchProvider } from './OrganizationSwitchProvider';
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
 *
 * **Organization context (SIE Milestone G3-3).** `OrganizationSwitchProvider`
 * is mounted identically under either branch, wrapping `children` —
 * never the base provider itself, which stays completely unaware a
 * switcher exists (see that component's own docstring for why it is a
 * separate layer rather than a change to `ProdAuthProvider`/
 * `DevAuthProvider`). This keeps the layering explicit and in one place:
 *
 *     Authentication (this dispatch) -> Organization context
 *         (OrganizationSwitchProvider) -> Authorization (PermissionRoute)
 *         -> Application
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const withOrganizationContext = <OrganizationSwitchProvider>{children}</OrganizationSwitchProvider>;

  if (getAuthMode() === 'dev') {
    return <DevAuthProvider>{withOrganizationContext}</DevAuthProvider>;
  }
  return <ProductionSessionGate>{withOrganizationContext}</ProductionSessionGate>;
}
