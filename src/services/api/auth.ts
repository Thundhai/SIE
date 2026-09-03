/**
 * Effective-permissions service — thin typed wrapper around
 * `GET /api/v1/auth/me` (`backend/app/api/v1/auth.py`), the
 * backend-authoritative replacement for a client-side permission matrix.
 * See `src/auth/DevAuthProvider.tsx` for how this is consumed.
 */
import { apiRequest } from './client';

export interface EffectivePermissions {
  user_id: string;
  name: string;
  email: string;
  organization_id: string;
  organization_name: string;
  role: string;
  permissions: string[];
  is_platform_admin: boolean;
  /** "dev" or "production" — which authentication mechanism the backend
   * used to resolve this identity (SIE Milestone 20). Display/diagnostic
   * only, e.g. so the UI can visibly disclose a development identity. */
  auth_mode: string;
  /** The identity provider label (e.g. "azuread"), or `null` for a
   * dev-mode identity — never a token or any other secret. */
  identity_provider: string | null;
}

export function getEffectivePermissions(
  organizationId: string,
  signal?: AbortSignal,
): Promise<EffectivePermissions> {
  return apiRequest<EffectivePermissions>('/auth/me', {
    query: { organization_id: organizationId },
    signal,
  });
}

export interface AuthOrganizationMembership {
  organization_id: string;
  organization_name: string;
  role: string;
}

export interface AuthOrganizations {
  memberships: AuthOrganizationMembership[];
  is_platform_admin: boolean;
}

/**
 * `GET /api/v1/auth/organizations` — the organizations the authenticated
 * identity may explicitly select (SIE Milestone 20, item 3: "if a user
 * belongs to multiple organizations, the architecture must explicitly
 * handle organization selection rather than silently choosing one"). A
 * production auth provider calls this once a token is available but
 * before any organization has been chosen, to render that selection
 * explicitly rather than defaulting to one.
 */
export function listAuthOrganizations(signal?: AbortSignal): Promise<AuthOrganizations> {
  return apiRequest<AuthOrganizations>('/auth/organizations', { signal });
}
