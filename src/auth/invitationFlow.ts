/**
 * Browser-side state for the invitation flow (`/invite` -> identity
 * provider -> `/callback` -> `/invite/complete`).
 *
 * The invitation code arrives in the URL fragment (`/invite#token=...`),
 * which browsers never send to a server or put in a Referer header. The
 * landing page moves it into `sessionStorage` (this tab only, cleared when
 * the tab closes, the same storage `oidc-client-ts` uses for its tokens),
 * removes it from the address bar, and the completion page clears it once
 * the invitation is accepted or definitively refused.
 */

const PENDING_KEY = 'sie.invitation.pending';

export const INVITATION_COMPLETE_PATH = '/invite/complete';

export function readTokenFromHash(hash: string): string | null {
  const params = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash);
  const token = params.get('token');
  return token && token.length >= 10 && token.length <= 200 ? token : null;
}

export function storePendingInvitation(token: string): void {
  try {
    window.sessionStorage.setItem(PENDING_KEY, token);
  } catch {
    // Storage unavailable (private mode): the flow still works within this page.
  }
}

export function readPendingInvitation(): string | null {
  try {
    return window.sessionStorage.getItem(PENDING_KEY);
  } catch {
    return null;
  }
}

export function clearPendingInvitation(): void {
  try {
    window.sessionStorage.removeItem(PENDING_KEY);
  } catch {
    // nothing to clear
  }
}

/** Only same-origin, absolute paths: never `//host`, a scheme, or a backslash trick. */
export function safeReturnPath(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\') || value.includes('://')) return null;
  return value;
}
