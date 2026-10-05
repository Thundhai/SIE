import { ShieldX } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageContainer } from '../components/layout/PageContainer';
import { Button } from '../components/ui/Button';

/**
 * The reusable 403/access-denied state — SIE Milestone G3-2.
 *
 * Deliberately NOT styled like `ErrorState` (a server/request failure):
 * this is an authorization boundary, not a system outage — see this
 * milestone's own "do not make the UI look like a system failure"
 * requirement. Renders inside the ordinary authenticated shell (Sidebar
 * and Header stay visible — `PermissionRoute` only replaces the
 * *page content*, not the whole app), so the user can still navigate
 * away normally, including back to a page they *do* have access to.
 *
 * Never names the specific missing permission (e.g. "risk_assessment:
 * approve") — that is internal vocabulary, not something a denied user
 * needs to see (this milestone's own "do not expose internal permission
 * names unnecessarily" requirement). An administrator who needs to know
 * exactly what to grant already has that answer from the backend's own
 * `Permission` vocabulary and this repository's route/permission
 * matrix — not from this screen.
 */
export function AccessDeniedPage() {
  const navigate = useNavigate();

  return (
    <PageContainer>
      <div
        role="alert"
        className="flex flex-col items-center justify-center gap-3 rounded-lg border border-border bg-surface px-6 py-16 text-center"
      >
        <ShieldX className="h-8 w-8 text-text-muted" aria-hidden="true" />
        <h1 className="text-lg font-semibold text-navy-900">Access denied</h1>
        <p className="max-w-sm text-sm text-text-secondary">
          Your signed-in account does not have the access required to view this page. If you believe this is
          incorrect, contact your organization administrator.
        </p>
        <Button variant="secondary" size="sm" className="mt-1" onClick={() => navigate('/')}>
          Return to Home
        </Button>
      </div>
    </PageContainer>
  );
}
