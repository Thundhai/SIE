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
 */

export interface DevIdentityConfig {
  userId: string;
  userName: string;
  userEmail: string;
  organizationId: string;
  organizationName: string;
}

export function getDevIdentityConfig(): DevIdentityConfig | null {
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
