/**
 * Active-organization persistence — SIE Milestone G3-3: Organization
 * Context & Switching.
 *
 * `sessionStorage`, never `localStorage` (mirrors `oidcSession.ts`'s own
 * rationale exactly: survives a same-tab refresh, never shared across
 * tabs/origins or left behind on a shared machine after the tab closes).
 *
 * **This is a UI preference, never authorization.** A persisted
 * organization id is only ever a *hint* for which organization to
 * re-enter on reload — it is always re-validated against the current,
 * authenticated `GET /auth/organizations` response before use
 * (`resolveActiveOrganization` below); a stale, revoked, or fabricated
 * value here can at most cause a harmless fallback to the deterministic
 * G3-1 pick, never access to anything the backend wouldn't otherwise
 * grant. See `OrganizationSwitchProvider.tsx` and
 * `ProductionSessionGate.tsx` for the two call sites (write-after-switch,
 * read-at-bootstrap respectively).
 */
import type { AuthOrganizationMembership } from '../services/api/auth';
import { resolveInitialOrganization, type InitialOrganizationResolution } from './organizationResolution';

const STORAGE_KEY = 'sie.activeOrganizationId';

export function readPersistedOrganizationId(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    // Storage unavailable (private browsing, disabled storage, ...) --
    // treat exactly like "nothing persisted", never a hard failure.
    return null;
  }
}

export function persistActiveOrganizationId(organizationId: string): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, organizationId);
  } catch {
    // Best-effort only -- a failure to persist a UI preference must
    // never block the switch itself from succeeding.
  }
}

export function clearPersistedOrganizationId(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clean up if storage itself is unavailable.
  }
}

/**
 * G3-1's `resolveInitialOrganization` stays untouched (deterministic,
 * stateless, its own well-tested contract) — this wraps it with exactly
 * the one rule this milestone adds: a persisted id wins over the
 * deterministic pick, but *only* when it is actually present in the
 * memberships list this same request just returned. An invalid
 * (revoked, stale, or never-real) persisted id is discarded outright
 * (never merely ignored-and-left-behind) and the deterministic fallback
 * applies exactly as it did before this module existed.
 */
export function resolveActiveOrganization(
  memberships: AuthOrganizationMembership[],
  persistedOrganizationId: string | null,
): InitialOrganizationResolution {
  if (persistedOrganizationId) {
    const stillValid = memberships.some((m) => m.organization_id === persistedOrganizationId);
    if (stillValid) {
      return { kind: 'selected', organizationId: persistedOrganizationId };
    }
    clearPersistedOrganizationId();
  }
  return resolveInitialOrganization(memberships);
}
