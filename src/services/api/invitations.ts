import { apiRequest } from './client';
import { ApiError } from './errors';

/**
 * Invitation-based registration — `backend/app/api/v1/invitations.py`.
 *
 * The one-time code only ever travels in a request body (and, in the
 * invitation link, in the URL fragment, which browsers never send to a
 * server). It is never put in a query string.
 */

export type InvitationStatus = 'PENDING' | 'REGISTRATION_STARTED' | 'VERIFIED' | 'ACCEPTED' | 'EXPIRED' | 'REVOKED';
export type InvitationMethod = 'password' | 'sso';

/** Mirrors `app/services/permissions.py::OrganizationRole`. */
export const INVITABLE_ROLES = ['ORG_ADMIN', 'HSE_MANAGER', 'HSE_ANALYST', 'HSE_USER', 'VIEWER'] as const;
export type InvitableRole = (typeof INVITABLE_ROLES)[number];

export interface Invitation {
  id: string;
  organization_id: string;
  email: string;
  role: string;
  status: InvitationStatus;
  created_at: string;
  expires_at: string;
  created_by_user_id: string | null;
  registration_started_at: string | null;
  verified_at: string | null;
  accepted_at: string | null;
  revoked_at: string | null;
  accepted_user_id: string | null;
  issue_count: number;
}

export interface IssuedInvitation {
  invitation: Invitation;
  /** Shown once. Build the link with `invitationLink()`. */
  code: string;
}

export interface PublicInvitation {
  status: InvitationStatus;
  organization_id: string;
  organization_name: string;
  role: string;
  invited_email: string;
  expires_at: string;
  methods: InvitationMethod[];
}

export interface AcceptedInvitation {
  organization_id: string;
  user_id: string;
  role: string;
  outcome: 'account_created' | 'existing_account';
}

/** `<origin>/invite#token=<code>` — the code is in the fragment. */
export function invitationLink(code: string, origin: string = window.location.origin): string {
  return `${origin}/invite#token=${encodeURIComponent(code)}`;
}

/** The backend's `details.reason` for an `INVITATION_REJECTED` error, if any. */
export function invitationErrorReason(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const reason = error.details?.reason;
  return typeof reason === 'string' ? reason : null;
}

// --- Administrator ---------------------------------------------------------------

export function listInvitations(organizationId: string, signal?: AbortSignal) {
  return apiRequest<Invitation[]>(`/organizations/${organizationId}/invitations`, { signal });
}

export function createInvitation(
  organizationId: string,
  input: { email: string; role: InvitableRole; expires_in_hours?: number },
) {
  return apiRequest<IssuedInvitation>(`/organizations/${organizationId}/invitations`, { method: 'POST', body: input });
}

export function resendInvitation(organizationId: string, invitationId: string) {
  return apiRequest<IssuedInvitation>(`/organizations/${organizationId}/invitations/${invitationId}/resend`, {
    method: 'POST',
  });
}

export function revokeInvitation(organizationId: string, invitationId: string) {
  return apiRequest<Invitation>(`/organizations/${organizationId}/invitations/${invitationId}/revoke`, {
    method: 'POST',
  });
}

// --- Invitee ---------------------------------------------------------------------

export function inspectInvitation(token: string, signal?: AbortSignal) {
  return apiRequest<PublicInvitation>('/invitations/inspect', { method: 'POST', body: { token }, signal });
}

export function startInvitation(token: string, method: InvitationMethod) {
  return apiRequest<PublicInvitation>('/invitations/start', { method: 'POST', body: { token, method } });
}

/** `accessToken` is passed explicitly: the invitation pages sit outside
 * the signed-in app shell, where the shared token getter isn't wired. */
export function acceptInvitation(token: string, accessToken: string, fullName?: string) {
  return apiRequest<AcceptedInvitation>('/auth/invitations/accept', {
    method: 'POST',
    body: fullName ? { token, full_name: fullName } : { token },
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
