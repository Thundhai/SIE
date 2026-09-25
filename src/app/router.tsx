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
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="events/:eventId" element={<EventDetailPage />} />
        <Route path="actions" element={<ActionsPage />} />
        <Route path="actions/:actionId" element={<ActionDetailPage />} />
        <Route path="risk-assessments" element={<RiskAssessmentsPage />} />
        <Route path="risk-assessments/:assessmentId" element={<RiskAssessmentDetailPage />} />
        <Route path="intelligence" element={<IntelligencePage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="administration" element={<AdministrationPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
