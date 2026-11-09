import { apiRequest } from './client';
import { ApiError } from './errors';
import type { InvitableRole } from './invitations';

/**
 * Administrator-added users — `backend/app/api/v1/user_provisioning.py`.
 *
 * The administrator enters an email, a name and a role. SIE creates (or
 * finds) the person's sign-in; when it creates one, the sign-in provider
 * emails them a link to set their password.
 */

export type AddUserOutcome = 'account_created' | 'existing_sign_in' | 'existing_sie_account';

export interface AddedUser {
  user_id: string;
  organization_id: string;
  role: string;
  outcome: AddUserOutcome;
  /** The set-password email was sent. */
  email_sent: boolean;
  /** A set-password email was needed but could not be sent; it can be resent. */
  email_failed: boolean;
}

export function addUser(organizationId: string, input: { email: string; name?: string; role: InvitableRole }) {
  return apiRequest<AddedUser>(`/organizations/${organizationId}/users`, { method: 'POST', body: input });
}

export function resendPasswordEmail(organizationId: string, userId: string) {
  return apiRequest<{ email_sent: boolean }>(`/organizations/${organizationId}/users/${userId}/password-email`, {
    method: 'POST',
  });
}

/** The backend's `details.reason` for a `USER_ADD_REJECTED` error, if any. */
export function addUserErrorReason(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const reason = error.details?.reason;
  return typeof reason === 'string' ? reason : null;
}
