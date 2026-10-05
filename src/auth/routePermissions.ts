/**
 * Central route-permission metadata — SIE Milestone G3-2: Authorization
 * & Protected Routes.
 *
 * The ONE source of truth for "which backend permission does route X
 * require" — `router.tsx` (route-level enforcement, via
 * `PermissionRoute`) and `Sidebar.tsx` (navigation visibility) both read
 * from this module so the two can never drift (this milestone's own
 * "do not duplicate permission logic between Sidebar and router"
 * requirement). Sidebar hiding is a UX convenience only — it is never
 * the security boundary; `PermissionRoute` is, and enforces the exact
 * same permission independently of whatever Sidebar happens to render
 * (a direct URL/deep link reaches `PermissionRoute` regardless of
 * Sidebar).
 *
 * Every value here is a `backend/app/services/permissions.py::Permission`
 * enum value, copied verbatim from the actual backend route dependency
 * that enforces it — never invented, never a frontend guess. See the
 * G3-2 audit's route/permission matrix for the exact evidence (file and
 * line) behind each entry:
 *
 *   events            -> SAFETY_DATA_READ   (backend/app/api/v1/events.py)
 *   actions           -> INTERVENTION_READ  (backend/app/api/v1/actions.py)
 *   riskAssessments   -> RISK_ASSESSMENT_READ (backend/app/api/v1/risk_assessments.py)
 *   intelligence      -> INTELLIGENCE_READ  (backend/app/api/v1/intelligence.py)
 *   knowledge         -> KNOWLEDGE_READ     (backend/app/api/v1/knowledge.py, retrieval.py)
 *   reports           -> INTELLIGENCE_READ  (its primary, title-defining
 *                        capability -- the page also touches
 *                        SAFETY_DATA_READ/INTERVENTION_READ, but every
 *                        role that has any one of the three already has
 *                        all three today, per ROLE_PERMISSIONS, so a
 *                        route-level AND-of-three gate would protect
 *                        against a hypothetical role that doesn't exist
 *                        yet, not a real one -- not implemented here;
 *                        revisit if such a role is ever introduced)
 *   administration    -> ORGANIZATION_READ  (the route-level floor: every
 *                        role has it, so this only establishes "an
 *                        authenticated organization member may open the
 *                        page" -- each administration SECTION inside it
 *                        independently checks its own, stricter
 *                        permission; see AdministrationPage.tsx)
 *
 * Home (`/`) has no entry here deliberately: it has no single
 * permission requirement (its sections already fail independently —
 * see HomePage.tsx's per-section AsyncState pattern), and every defined
 * role already has every permission its sections individually use.
 */
import type { PermissionKey } from './types';

export const ROUTE_PERMISSIONS = {
  events: 'safety_data:read',
  actions: 'intervention:read',
  riskAssessments: 'risk_assessment:read',
  intelligence: 'intelligence:read',
  knowledge: 'knowledge:read',
  reports: 'intelligence:read',
  administration: 'organization:read',
} as const satisfies Record<string, PermissionKey>;

/**
 * Administration-section permissions — a *second* tier below the
 * route-level floor above, used by `AdministrationPage.tsx` to gate
 * each section's own fetch and visibility independently (this
 * milestone's own "do not grant all Administration access merely
 * because a user can view one administrative section" requirement).
 * Evidence:
 *
 *   sites       -> SITE_READ    (backend/app/api/v1/sites.py, as
 *                  hardened by G3-BE-01 -- enforced on this branch as
 *                  of the G3-2 rebase onto post-G3-BE-01 main; no
 *                  longer a cross-branch gap)
 *   members     -> USERS_READ   (backend/app/api/v1/memberships.py)
 *   standards   -> STANDARDS_READ (backend/app/api/v1/governing_standards.py)
 *   apiClients  -> USERS_MANAGE (backend/app/api/v1/api_clients.py — the
 *                  list endpoint itself requires USERS_MANAGE, not a
 *                  separate read permission; confirmed directly from
 *                  that route's own dependency, not assumed)
 *
 * `organization` (the Organization info section) has no entry: the
 * backend's `GET /organizations/{id}` route has no permission
 * requirement at all today (a separate, already-tracked gap — see the
 * G3-2 final report's "backend capabilities found to be missing"
 * section) — so, pending that fix, it is shown to anyone who can reach
 * the route-level floor above.
 */
export const ADMINISTRATION_SECTION_PERMISSIONS = {
  sites: 'site:read',
  members: 'users:read',
  standards: 'standards:read',
  apiClients: 'users:manage',
} as const satisfies Record<string, PermissionKey>;
