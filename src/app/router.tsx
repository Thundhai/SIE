import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { EventDetailPage } from '../features/events/EventDetailPage';
import { EventsPage } from '../features/events/EventsPage';
import { HomePage } from '../features/home/HomePage';

/**
 * URL-based routing — replaces the legacy `currentScreen: AppScreen`
 * `useState` switch entirely for the new SIE application (the legacy
 * `src/App.tsx` still uses that pattern, untouched, for its own
 * unrelated screens).
 *
 * Only Home and Events (+ Event Detail) are real routes this milestone.
 * Actions/Intelligence/Knowledge/Reports/Administration are NOT routed
 * yet — the Sidebar renders them as disabled, clearly-labeled
 * "Coming later" items rather than linking to placeholder pages (§9/§22:
 * "do not create fake pages for them simply to make navigation appear
 * complete"). Any unknown path redirects to Home rather than 404ing,
 * since there is nothing else to route to yet.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="events/:eventId" element={<EventDetailPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
