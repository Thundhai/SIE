import { BrowserRouter } from 'react-router-dom';
import { AppRoutes } from './router';

/**
 * The new SIE application root — SIE Frontend Foundation & Core UX
 * Implementation v0.1. Mounted directly by src/main.tsx, replacing the
 * legacy `src/App.tsx` as the live application; the legacy file itself
 * is left completely untouched (see docs/FRONTEND_ARCHITECTURE.md for
 * the full legacy-vs-new boundary).
 *
 * `data-sie-app` scopes the new design tokens' document-level rules
 * (src/index.css) so nothing here can ever affect the legacy prototype
 * if it were ever mounted again for comparison.
 *
 * **SIE Milestone G3-1.** No longer hardcodes `<DevAuthProvider>` here —
 * `AuthGate` (dispatched per-route by `router.tsx`, inside the
 * router context it needs) now picks `DevAuthProvider` vs
 * `ProductionSessionGate` based on `authMode.ts`, and `/login`/
 * `/callback` must render *outside* either one (both would otherwise
 * try to gate routes those two pages have no business being gated by).
 * `BrowserRouter` has to wrap `AppRoutes` for that dispatch to have
 * router context (`useLocation`) available at all.
 */
export function App() {
  return (
    <div data-sie-app className="min-h-screen">
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </div>
  );
}

export default App;
