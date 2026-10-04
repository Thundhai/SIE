/**
 * The single source of truth for SIE's development identity — read by
 * BOTH `DevAuthProvider` (so the UI can display who it thinks it is) and
 * the API client (so requests carry the matching `X-SIE-Dev-User-Id`
 * header the backend's dev-mode mechanism expects). Keeping one function
 * instead of two independent readers means the two can never disagree.
 *
 * Configured entirely via Vite env vars, never hardcoded — there is no
 * "Demo Energy & Engineering Ltd." or fabricated user anywhere in the new
 * SIE frontend (contrast the legacy prototype's `Header.tsx`). When
 * unset, the app has no dev identity at all and shows that honestly
 * (see AuthContext's `isAuthenticated: false` state) rather than
 * fabricating one.
 *
 * **Production safety gate (G3-1).** Before this gate existed, this
 * function's only check was "are `VITE_DEV_USER_ID`/
 * `VITE_DEV_ORGANIZATION_ID` set" — which meant a production build whose
 * deployment environment happened to still carry those two build-time
 * variables (exactly the live misconfiguration the G3-0 audit found)
 * would silently resolve a development identity, and `services/api/
 * client.ts`'s own fallback would silently attach the dev-only
 * `X-SIE-Dev-User-Id` header to every request. This now returns `null`
 * unconditionally in production (see `authMode.ts`), regardless of
 * whether those two variables are set, so there is no environment-
 * variable combination that can reactivate development identity in a
 * production build.
 */

import { getAuthMode } from './authMode';

export interface DevIdentityConfig {
  userId: string;
  userName: string;
  userEmail: string;
  organizationId: string;
  organizationName: string;
}

export function getDevIdentityConfig(): DevIdentityConfig | null {
  if (getAuthMode() === 'production') {
    return null;
  }

  const userId = import.meta.env.VITE_DEV_USER_ID as string | undefined;
  const organizationId = import.meta.env.VITE_DEV_ORGANIZATION_ID as string | undefined;

  // Both a user id and an organization id are required — every
  // authorized backend read in this milestone needs organization_id as
  // an explicit query parameter (see app/api/v1/intelligence.py), so a
  // dev identity without one is not usable and should not be presented
  // as if it were.
  if (!userId || !organizationId) {
    return null;
  }

  return {
    userId,
    userName: (import.meta.env.VITE_DEV_USER_NAME as string | undefined) || 'Development User',
    userEmail: (import.meta.env.VITE_DEV_USER_EMAIL as string | undefined) || 'dev-user@example.invalid',
    organizationId,
    organizationName: (import.meta.env.VITE_DEV_ORGANIZATION_NAME as string | undefined) || 'Development Organization',
  };
}
