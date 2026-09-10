import { useAuth } from '../../auth/AuthContext';

/**
 * Top bar — organization/user identity only, never hardcoded (contrast
 * the legacy prototype's `Header.tsx`, which hardcodes "Demo Energy &
 * Engineering Ltd." and a fictional user). Reads exclusively through
 * `useAuth()`, so it renders correctly whether the configured dev
 * identity resolved, is still resolving, or isn't configured at all —
 * and will keep working unchanged once a real auth provider replaces
 * `DevAuthProvider`.
 */
export function Header() {
  const auth = useAuth();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-6">
      <div>
        {auth.organization ? (
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
      </div>
    </header>
  );
}
