import { ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { AccessDeniedPage } from './AccessDeniedPage';
import type { PermissionKey } from './types';

/**
 * Route-level authorization boundary — SIE Milestone G3-2.
 *
 *     Authenticated? (G3-1's AuthGate, already satisfied by the time
 *         this renders -- every route it wraps sits inside AuthGate)
 *         ↓
 *     Organization context? (G3-1's ProductionSessionGate /
 *         DevAuthProvider, already resolved -- auth.organization is
 *         set by the time this renders)
 *         ↓
 *     Required permission?  <- THIS component
 *         ↓
 *     Render route, or render AccessDeniedPage
 *
 * Deliberately the only thing this component does: read
 * `auth.hasPermission()` (backend-authoritative — see `types.ts`'s own
 * docstring) and pick one of two renders. It never re-derives a
 * permission from a role, never maintains its own copy of
 * `ROLE_PERMISSIONS`, and never does anything a direct URL/deep link
 * could bypass — it runs on every render of the route it wraps,
 * independent of whether `Sidebar` happens to show a link to it.
 *
 * This is route-level authorization specifically, distinct from
 * operation-level authorization (an individual create/edit/approve
 * control's own `hasPermission()` check inside a page already-granted
 * route access — see e.g. `ActionDetailPage.tsx`, unaffected by this
 * component and not duplicated here).
 */
export function PermissionRoute({
  permission,
  children,
}: {
  permission: PermissionKey;
  children: ReactNode;
}) {
  const auth = useAuth();

  if (!auth.hasPermission(permission)) {
    return <AccessDeniedPage />;
  }

  return <>{children}</>;
}
