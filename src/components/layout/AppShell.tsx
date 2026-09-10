import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

/** The new SIE application shell — sidebar + header + routed page
 * content (`<Outlet />`). Rendered once as the router's layout route
 * (see app/router.tsx) so it never remounts between Home/Events/Event
 * Detail navigations. */
export function AppShell() {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
