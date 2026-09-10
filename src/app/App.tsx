import { BrowserRouter } from 'react-router-dom';
import { DevAuthProvider } from '../auth/DevAuthProvider';
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
 */
export function App() {
  return (
    <div data-sie-app className="min-h-screen">
      <DevAuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </DevAuthProvider>
    </div>
  );
}

export default App;
