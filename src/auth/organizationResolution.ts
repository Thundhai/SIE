/**
 * Session-level active-organization resolution — SIE Milestone G3-1.
 *
 * G3-1 establishes the session-level active organization; it does not
 * build the full organization switcher (that's G3-3 — see
 * `ProdAuthProvider.tsx`'s own docstring on `organizationId` being
 * supplied, never chosen, by the provider itself). This module is the
 * one place that initial choice is made, kept pure and separately
 * testable from the async session-bootstrap code that calls it.
 */
import type { AuthOrganizationMembership } from '../services/api/auth';

export type InitialOrganizationResolution =
  | { kind: 'none' }
  | { kind: 'selected'; organizationId: string };

/**
 * - Zero memberships -> `{ kind: 'none' }` (the caller renders an
 *   "organization setup required" state, never an ambiguous failure).
 * - One or more memberships -> the lowest `organization_id` by plain
 *   string comparison. Deterministic regardless of the order the
 *   backend's own query happens to return rows in (`GET
 *   /auth/organizations` makes no ordering guarantee) — "deterministic"
 *   specifically means "the same input list always yields the same
 *   choice", not "the most recently used" or any other stateful notion,
 *   which would be the actual organization switcher (G3-3).
 */
export function resolveInitialOrganization(
  memberships: AuthOrganizationMembership[],
): InitialOrganizationResolution {
  if (memberships.length === 0) {
    return { kind: 'none' };
  }

  const sorted = [...memberships].sort((a, b) => a.organization_id.localeCompare(b.organization_id));
  return { kind: 'selected', organizationId: sorted[0].organization_id };
}
