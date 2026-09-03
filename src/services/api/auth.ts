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
