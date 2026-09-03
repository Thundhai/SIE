/**
 * Authentication/identity abstraction — SIE Frontend Foundation v0.1.
 *
 * The backend (`backend/app/api/deps_auth.py`) has no production login or
 * session endpoint yet: the only identity mechanism today is a dev-mode
 * request header (`X-SIE-Dev-User-Id`), explicitly documented there as
 * non-production ("THERE IS NO REAL AUTHENTICATION IMPLEMENTED YET").
 *
 * This module exists so no page/feature component ever depends on that
 * mechanism directly. Every component reads identity through
 * `useAuth()` (see AuthContext.tsx) against this interface; today
 * `DevAuthProvider` is the only implementation, and a future
 * `ProdAuthProvider` (real OIDC/OAuth2 session) can be swapped in later
 * without touching a single screen.
 */

export interface AuthUser {
  id: string;
  name: string;
  email: string;
}

export interface AuthOrganization {
  id: string;
  name: string;
}

export interface AuthMembership {
  organizationId: string;
  organizationName: string;
  /** Mirrors `app/services/permissions.py::OrganizationRole` values
   * verbatim (e.g. "ORG_ADMIN", "HSE_MANAGER") — never invented here. */
  role: string;
}

/** Mirrors `app/services/permissions.py::Permission` values verbatim
 * (e.g. "intelligence:read"). Kept as a plain string, not a duplicated
 * enum, so the frontend never drifts from the backend's own vocabulary
 * by needing a second definition to stay in sync. */
export type PermissionKey = string;

export interface AuthContextValue {
  /** Whether an identity is currently established at all. */
  isAuthenticated: boolean;
  /** True for the dev-mode stand-in identity, false for a real session.
   * UI that needs to visibly disclose "this is a development identity,
   * not a real login" (see AppShell's own user menu) reads this rather
   * than inferring it from other fields. */
  isDevIdentity: boolean;
  user: AuthUser | null;
  /** The organization the app is currently scoped to. Display-only — see
   * this module's own docstring: the backend remains the sole
   * authorization boundary, this value is never trusted as a security
   * control on its own. */
  organization: AuthOrganization | null;
  memberships: AuthMembership[];
  permissions: PermissionKey[];
  hasPermission: (permission: PermissionKey) => boolean;
}
