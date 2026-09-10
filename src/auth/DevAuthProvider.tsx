import { ReactNode, useEffect, useState } from 'react';
import { getEffectivePermissions } from '../services/api/auth';
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
 * `permissions`/`hasPermission()` are backed by the real
 * `GET /api/v1/auth/me` endpoint (SIE Enterprise Read API & Browser
 * Integration Foundation v0.1 — `backend/app/api/v1/auth.py`), which
 * serializes the backend's own already-computed, already-authoritative
 * `TenantContext.permissions` (`app/services/permissions.py::
 * ROLE_PERMISSIONS`, resolved server-side). This frontend never carries
 * its own copy of that mapping — see `docs/FRONTEND_ARCHITECTURE.md` §3
 * and `docs/ENTERPRISE_API.md` §6. `hasPermission()` remains
 * display-only, exactly like every other field on this context (this
 * module's own docstring): it lets the UI hide an action a user
 * genuinely cannot perform, but the backend's own 403 response is still
 * the real enforcement in every case, whether or not a screen also
 * checks this first.
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
        const [organization, membership, effectivePermissions] = await Promise.all([
          getOrganization(config!.organizationId, controller.signal),
          getMembership(config!.organizationId, config!.userId, controller.signal),
          // Real, backend-authoritative permissions (see this module's
          // own docstring) — not derived from `membership.role` here.
          getEffectivePermissions(config!.organizationId, controller.signal),
        ]);
        if (cancelled) return;

        const memberships: AuthMembership[] = [
          { organizationId: organization.id, organizationName: organization.name, role: membership.role },
        ];
        const permissions = effectivePermissions.permissions;
        const permissionSet = new Set(permissions);

        setValue({
          isAuthenticated: true,
          isDevIdentity: true,
          user: { id: config!.userId, name: config!.userName, email: config!.userEmail },
          organization: { id: organization.id, name: organization.name },
          memberships,
          permissions,
          hasPermission: (permission) => permissionSet.has(permission),
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
