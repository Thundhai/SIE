import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { getEffectivePermissions } from '../services/api/auth';
import { ApiError } from '../services/api/errors';
import { AuthContext, useAuth } from './AuthContext';
import { persistActiveOrganizationId } from './organizationPersistence';
import type { AuthContextValue } from './types';

export type OrganizationSwitchStatus = 'idle' | 'switching' | 'error';

export interface OrganizationSwitchContextValue {
  switchState: OrganizationSwitchStatus;
  /** Set only while `switchState === 'switching'` — lets a switcher UI
   * show a spinner next to the specific target the user picked, not a
   * generic "something is loading" state. */
  switchingToOrganizationId: string | null;
  /** Set only while `switchState === 'error'`. Never a raw backend error
   * string (mirrors `AccessDeniedPage`'s own "no raw backend errors"
   * rule) -- one of a small, fixed set of plain-language messages. */
  switchErrorMessage: string | null;
  switchOrganization: (organizationId: string) => Promise<void>;
}

const OrganizationSwitchContext = createContext<OrganizationSwitchContextValue | null>(null);

export function useOrganizationSwitch(): OrganizationSwitchContextValue {
  const value = useContext(OrganizationSwitchContext);
  if (!value) {
    throw new Error(
      'useOrganizationSwitch() must be called within an <OrganizationSwitchProvider> (see auth/AuthGate.tsx).',
    );
  }
  return value;
}

type InternalSwitchState =
  | { status: 'idle' }
  | { status: 'switching'; organizationId: string }
  | { status: 'error'; organizationId: string; message: string };

/**
 * The one authoritative owner of "which organization is active" — SIE
 * Milestone G3-3: Organization Context & Switching.
 *
 *     Authentication (AuthGate: DevAuthProvider / ProductionSessionGate)
 *         ↓
 *     Organization context (THIS component)
 *         ↓
 *     Authorization (PermissionRoute, Sidebar)
 *         ↓
 *     Application (every page)
 *
 * Mounted once, inside `AuthGate`, wrapping every authenticated route —
 * see that module's own docstring. It renders a SECOND `AuthContext.
 * Provider`, shadowing whichever base provider (`DevAuthProvider` or
 * `ProductionSessionGate` → `ProdAuthProvider`) is above it: every
 * existing consumer (`Header`, `Sidebar`, `PermissionRoute`, every
 * feature page) keeps reading `useAuth()` exactly as before and is
 * completely unaware this layer exists, except that `organization`/
 * `permissions`/`hasPermission()` now reflect whichever organization a
 * user explicitly switched to, not only the one the base provider
 * resolved at session bootstrap.
 *
 * **Why a second `AuthContext.Provider`, not a change to
 * `ProdAuthProvider` itself.** `ProdAuthProvider`'s own `organizationId`
 * prop is deliberately left untouched by this component — it still
 * resolves exactly one organization, exactly once, exactly as it did
 * before this milestone (zero regression risk to G3-1). Feeding a
 * *changing* `organizationId` into it instead would mean every switch
 * re-triggers its own internal bootstrap effect, including its "any
 * failure -> NOT_AUTHENTICATED" catch-all (correct for an initial
 * bootstrap failure, wrong for a later switch attempt: a 403 switching
 * TO a forbidden organization must never look like a full sign-out from
 * the one the user was already using). Owning the switch as its own,
 * explicit, one-shot `GET /auth/me?organization_id=<target>` request
 * here — the same endpoint, the same backend-authoritative contract,
 * just not routed through `ProdAuthProvider`'s own state machine — keeps
 * that existing contract intact and gives this component exactly the
 * control the task requires: commit the override only on confirmed
 * success, never on a failure, and never duplicate the *current*
 * organization's permission resolution (there is still only one
 * resolver per organization per request, never two racing observers of
 * the same one).
 *
 * **Tenant safety.** `switchOrganization()` only ever accepts an id
 * already present in `base.memberships` -- the same backend-authoritative
 * list `/auth/organizations` already returned for the *current*
 * organization's own resolution. An arbitrary caller-supplied id (typed,
 * URL-sourced, or otherwise) that isn't in that list is rejected locally
 * before any request is made; even so, the backend's own
 * `authorize_tenant_context()` remains the real, final authority — this
 * local check is a UX guard against an obviously-wrong target, never
 * the security boundary itself (see this module's own test file's
 * "arbitrary organization id" cases, which assert both layers).
 */
export function OrganizationSwitchProvider({ children }: { children: ReactNode }) {
  const base = useAuth();
  const [override, setOverride] = useState<AuthContextValue | null>(null);
  const [switchState, setSwitchState] = useState<InternalSwitchState>({ status: 'idle' });
  const inFlight = useRef<AbortController | null>(null);
  // Which base-provider organization id this override was computed
  // relative to -- if the base provider ever resolves a *different*
  // organization than this (a fresh sign-in after a session ended, most
  // concretely), the override no longer corresponds to the session it
  // was switched within and must be discarded, not carried forward.
  const overriddenForBaseOrgId = useRef<string | null>(null);

  const baseOrgId = base.organization?.id ?? null;

  useEffect(() => {
    if (!base.isAuthenticated) {
      // Session ended (sign-out, 401-triggered invalidation, ...) --
      // nothing this component holds is valid any more.
      setOverride(null);
      overriddenForBaseOrgId.current = null;
      setSwitchState({ status: 'idle' });
      return;
    }
    if (overriddenForBaseOrgId.current !== null && overriddenForBaseOrgId.current !== baseOrgId) {
      setOverride(null);
      overriddenForBaseOrgId.current = null;
      setSwitchState({ status: 'idle' });
    }
  }, [base.isAuthenticated, baseOrgId]);

  useEffect(() => {
    return () => inFlight.current?.abort();
  }, []);

  const activeOrganizationId = (override ?? base).organization?.id ?? null;

  const switchOrganization = useCallback(
    async (organizationId: string) => {
      // One switch in flight at a time -- prevents rapid repeated
      // switching from ever leaving the context inconsistent (the task's
      // own explicit requirement). A caller-side disabled control is the
      // first line of defense; this is the actual guarantee.
      if (switchState.status === 'switching') {
        return;
      }

      if (activeOrganizationId === organizationId) {
        return; // Already active -- no network call, no state change.
      }

      const isAuthorized = base.memberships.some((m) => m.organizationId === organizationId);
      if (!isAuthorized) {
        setSwitchState({
          status: 'error',
          organizationId,
          message: 'That organization is not available to you.',
        });
        return;
      }

      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      setSwitchState({ status: 'switching', organizationId });

      try {
        const effective = await getEffectivePermissions(organizationId, controller.signal);
        if (controller.signal.aborted) return;

        const permissionSet = new Set(effective.permissions);
        setOverride({
          ...base,
          organization: { id: effective.organization_id, name: effective.organization_name },
          permissions: effective.permissions,
          hasPermission: (permission) => permissionSet.has(permission),
        });
        overriddenForBaseOrgId.current = baseOrgId;
        persistActiveOrganizationId(effective.organization_id);
        setSwitchState({ status: 'idle' });
      } catch (err) {
        if (controller.signal.aborted) return;

        if (err instanceof ApiError && err.status === 401) {
          // The credential itself is no longer valid -- services/api/
          // client.ts already called notifySessionInvalidated() for
          // this exact response, and ProductionSessionGate (the one
          // registered handler) is already signing out and navigating
          // to /login. This component's only remaining job is to make
          // sure it never shows a switched-to organization in the brief
          // window before that unmount happens.
          setOverride(null);
          overriddenForBaseOrgId.current = null;
          setSwitchState({ status: 'idle' });
          return;
        }

        // 403 (authenticated, but not authorized for this organization)
        // and every other failure (network, 5xx, ...) get the same
        // treatment here: never activate the target organization, never
        // sign out, retain whatever was already active (the override, if
        // any, is simply left untouched above this catch block).
        setSwitchState({
          status: 'error',
          organizationId,
          message:
            err instanceof ApiError && err.status === 403
              ? 'You do not have access to that organization.'
              : 'Could not switch organizations. Please try again.',
        });
      }
    },
    [base, baseOrgId, activeOrganizationId, switchState.status],
  );

  const value = override ?? base;

  return (
    <AuthContext.Provider value={value}>
      <OrganizationSwitchContext.Provider
        value={{
          switchState: switchState.status,
          switchingToOrganizationId: switchState.status === 'switching' ? switchState.organizationId : null,
          switchErrorMessage: switchState.status === 'error' ? switchState.message : null,
          switchOrganization,
        }}
      >
        {children}
      </OrganizationSwitchContext.Provider>
    </AuthContext.Provider>
  );
}
