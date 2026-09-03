import { ReactNode, useEffect, useState } from 'react';
import { getMembership, getOrganization } from '../services/api/organizations';
import { AuthContext } from './AuthContext';
import { getDevIdentityConfig } from './devIdentity';
import type { AuthContextValue, AuthMembership } from './types';

const NOT_AUTHENTICATED: AuthContextValue = {
  isAuthenticated: false,
  isDevIdentity: true,
  user: null,
  organization: null,
  memberships: [],
  permissions: [],
  hasPermission: () => false,
};

/**
 * Development identity provider — the ONLY `AuthContext` implementation
 * that exists today. It is explicitly not a production login: it
 * resolves whatever `VITE_DEV_USER_ID`/`VITE_DEV_ORGANIZATION_ID` name
 * (see devIdentity.ts) against the REAL backend (`GET /organizations/{id}`,
 * `GET /organizations/{id}/members/{user_id}` — both real, already-built
 * endpoints), so the organization name and role shown are genuine
 * backend data, not fabricated — but the *mechanism* used to reach them
 * (the `X-SIE-Dev-User-Id` header) is the backend's own documented
 * dev-only mechanism, not a real session.
 *
 * `permissions` is always empty and `hasPermission()` always returns
 * `false`: the backend has no endpoint to resolve a user's effective
 * permission set (only their role, which requires the same
 * `ROLE_PERMISSIONS` logic `app/services/permissions.py` owns to turn
 * into permissions — duplicating that mapping client-side would drift
 * from the backend's own source of truth, so it was deliberately not
 * attempted here; see this milestone's own completion report, "known
 * backend gaps"). Nothing in this milestone's UI depends on
 * `hasPermission()` returning true — the backend's own 403 response
 * remains the real enforcement in every case.
 */
export function DevAuthProvider({ children }: { children: ReactNode }) {
  const [value, setValue] = useState<AuthContextValue>(NOT_AUTHENTICATED);

  useEffect(() => {
    const config = getDevIdentityConfig();
    if (!config) {
      setValue(NOT_AUTHENTICATED);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    async function resolve() {
      try {
        const [organization, membership] = await Promise.all([
          getOrganization(config!.organizationId, controller.signal),
          getMembership(config!.organizationId, config!.userId, controller.signal),
        ]);
        if (cancelled) return;

        const memberships: AuthMembership[] = [
          { organizationId: organization.id, organizationName: organization.name, role: membership.role },
        ];

        setValue({
          isAuthenticated: true,
          isDevIdentity: true,
          user: { id: config!.userId, name: config!.userName, email: config!.userEmail },
          organization: { id: organization.id, name: organization.name },
          memberships,
          permissions: [],
          hasPermission: () => false,
        });
      } catch {
        // Could not resolve the configured dev identity against the
        // backend (not running, wrong id, network unreachable, ...) —
        // fail to "not authenticated" rather than fabricating a user/org
        // the backend never confirmed exists.
        if (!cancelled) {
          setValue(NOT_AUTHENTICATED);
        }
      }
    }

    void resolve();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
