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

/**
 * URL-based routing — replaces the legacy `currentScreen: AppScreen`
 * `useState` switch entirely for the new SIE application (the legacy
 * `src/App.tsx` still uses that pattern, untouched, for its own
 * unrelated screens).
 *
 * Home, Events (+ Event Detail), Actions (+ Action Detail, SIE Milestone
 * 18), Intelligence, and Risk Assessments (+ detail, SIE Milestone UI-01)
 * are real routes. Knowledge/Reports/Administration are still NOT routed
 * — the Sidebar renders them as disabled, clearly-labeled "Coming later"
 * items rather than linking to placeholder pages (§9/§22: "do not create
 * fake pages for them simply to make navigation appear complete"). Any
 * unknown path redirects to Home rather than 404ing, since there is
 * nothing else to route to yet.
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
