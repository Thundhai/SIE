import { Loader2 } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { useOidcSession } from '../../auth/oidcSession';
import { useOrganizationSwitch } from '../../auth/OrganizationSwitchProvider';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';

/**
 * Top bar — organization/user identity only, never hardcoded (contrast
 * the legacy prototype's `Header.tsx`, which hardcodes "Demo Energy &
 * Engineering Ltd." and a fictional user). Reads exclusively through
 * `useAuth()`, so it renders correctly whether the configured dev
 * identity resolved, is still resolving, or isn't configured at all —
 * and will keep working unchanged once a real auth provider replaces
 * `DevAuthProvider`.
 *
 * **Sign out (G3-1).** Only rendered for a real production session
 * (`!isDevIdentity`) — a dev identity has no login step, so it has no
 * meaningful logout either (see `devIdentity.ts`). `useOidcSession()` is
 * safe to call unconditionally: in dev mode (no OIDC configured) it
 * simply resolves to an inert `unauthenticated` state and the button
 * below never renders.
 *
 * **Organization switcher (SIE Milestone G3-3).** A single-organization
 * identity (today's only dev-mode shape, and the common production case)
 * keeps the plain-text organization name exactly as before — "no
 * misleading switch action" for a user who has nothing to switch to. A
 * genuinely multi-organization identity gets a native `<Select>` instead
 * (see `ui/Select.tsx`'s own docstring on why a native select, not a
 * hand-rolled listbox — keyboard/screen-reader/mobile support for free).
 * The list is exactly `auth.memberships` — the same backend-authoritative
 * `/auth/organizations` data every other organization-aware component
 * already reads, never a second source. Selecting an option calls
 * `useOrganizationSwitch().switchOrganization()`, which is the only
 * thing that ever changes which organization is active (see that
 * module's own docstring for the full switch sequence and why no raw
 * organization UUID is ever shown as the primary label here).
 */
export function Header() {
  const auth = useAuth();
  const oidc = useOidcSession();
  const { switchState, switchErrorMessage, switchOrganization } = useOrganizationSwitch();
  const showSignOut = auth.isAuthenticated && !auth.isDevIdentity;
  const isSwitching = switchState === 'switching';
  const canSwitch = auth.isAuthenticated && auth.memberships.length > 1;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-6">
      <div className="flex items-center gap-2.5">
        {canSwitch ? (
          <>
            <Select
              label="Organization"
              hideLabel
              className="w-56 py-1.5 text-sm"
              value={auth.organization?.id ?? ''}
              disabled={isSwitching}
              onChange={(event) => void switchOrganization(event.target.value)}
              options={auth.memberships.map((m) => ({ value: m.organizationId, label: m.organizationName }))}
            />
            {isSwitching && (
              <span role="status" aria-live="polite" className="flex items-center gap-1.5 text-xs text-text-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                Switching…
              </span>
            )}
            {switchState === 'error' && switchErrorMessage && (
              <span role="alert" className="text-xs text-critical">
                {switchErrorMessage}
              </span>
            )}
          </>
        ) : auth.organization ? (
          <p className="text-sm font-medium text-text-primary">{auth.organization.name}</p>
        ) : (
          <p className="text-sm text-text-muted">No organization context</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        {auth.isAuthenticated && auth.isDevIdentity && (
          <span className="rounded-full border border-warning/30 bg-warning-surface px-2.5 py-0.5 text-[11px] font-medium text-warning">
            Development identity
          </span>
        )}
        {auth.user ? (
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-teal-100 text-xs font-semibold text-teal-700">
              {auth.user.name.slice(0, 1).toUpperCase()}
            </div>
            <span className="text-sm text-text-secondary">{auth.user.name}</span>
          </div>
        ) : (
          <span className="text-sm text-text-muted">Not signed in</span>
        )}
        {showSignOut && (
          <Button variant="ghost" size="sm" onClick={() => void oidc.signOutLocally()}>
            Sign out
          </Button>
        )}
      </div>
    </header>
  );
}
