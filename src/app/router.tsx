import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { ActionDetailPage } from '../features/actions/ActionDetailPage';
import { ActionsPage } from '../features/actions/ActionsPage';
import { EventDetailPage } from '../features/events/EventDetailPage';
import { EventsPage } from '../features/events/EventsPage';
import { HomePage } from '../features/home/HomePage';
import { IntelligencePage } from '../features/intelligence/IntelligencePage';
import { RiskAssessmentDetailPage } from '../features/riskAssessments/RiskAssessmentDetailPage';
import { RiskAssessmentsPage } from '../features/riskAssessments/RiskAssessmentsPage';
import { KnowledgePage } from '../features/knowledge/KnowledgePage';
import { ReportsPage } from '../features/reports/ReportsPage';
import { AdministrationPage } from '../features/administration/AdministrationPage';
import { CallbackPage } from '../auth/CallbackPage';
import { LoginPage } from '../auth/LoginPage';
import { AuthGate } from '../auth/AuthGate';
import { PermissionRoute } from '../auth/PermissionRoute';
import { ROUTE_PERMISSIONS } from '../auth/routePermissions';

/**
 * URL-based routing — replaces the legacy `currentScreen: AppScreen`
 * `useState` switch entirely for the new SIE application (the legacy
 * `src/App.tsx` still uses that pattern, untouched, for its own
 * unrelated screens).
 *
 * Home, Events (+ Event Detail), Actions (+ Action Detail, SIE Milestone
 * 18), Intelligence, Risk Assessments (+ detail, SIE Milestone UI-01),
 * Knowledge, Reports, and Administration are all real routes, each backed
 * by real backend data (never a fake/placeholder page — §9/§22). Any
 * unknown path redirects to Home rather than 404ing.
 *
 * **`/login` and `/callback` (SIE Milestone G3-1).** The only two public
 * routes — reachable with no session at all, in either auth mode. Every
 * other route is nested under `<AuthGate>`, which in dev mode is exactly
 * today's unchanged `<DevAuthProvider>`, and in production is
 * `<ProductionSessionGate>` (redirect-to-`/login` + organization
 * resolution + `<ProdAuthProvider>` — see that component's own
 * docstring).
 *
 * **Permission gates (SIE Milestone G3-2).** Below the authentication
 * boundary:
 *
 *     Public Routes -> AuthGate (authentication) -> PermissionRoute
 *         (authorization) -> Feature Route
 *
 * Each route that requires a specific backend permission beyond plain
 * authentication is wrapped in `<PermissionRoute permission={...}>`,
 * reading the SAME `ROUTE_PERMISSIONS` constants `Sidebar.tsx` uses for
 * navigation visibility — the one source of truth this milestone's own
 * "do not duplicate permission logic between Sidebar and router"
 * requirement asks for. This is what actually protects a direct URL/
 * deep link: `Sidebar` hiding a link is a UX convenience only, never
 * the security boundary (`PermissionRoute` runs regardless of how the
 * route was reached). Home has no entry in `ROUTE_PERMISSIONS` and is
 * therefore wrapped in nothing beyond `AuthGate` — see that module's
 * own docstring for why.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route path="callback" element={<CallbackPage />} />
      <Route
        element={
          <AuthGate>
            <AppShell />
          </AuthGate>
        }
      >
        <Route index element={<HomePage />} />
        <Route
          path="events"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.events}>
              <EventsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="events/:eventId"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.events}>
              <EventDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="actions"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.actions}>
              <ActionsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="actions/:actionId"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.actions}>
              <ActionDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="risk-assessments"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.riskAssessments}>
              <RiskAssessmentsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="risk-assessments/:assessmentId"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.riskAssessments}>
              <RiskAssessmentDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="intelligence"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.intelligence}>
              <IntelligencePage />
            </PermissionRoute>
          }
        />
        <Route
          path="knowledge"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.knowledge}>
              <KnowledgePage />
            </PermissionRoute>
          }
        />
        <Route
          path="reports"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.reports}>
              <ReportsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="administration"
          element={
            <PermissionRoute permission={ROUTE_PERMISSIONS.administration}>
              <AdministrationPage />
            </PermissionRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
