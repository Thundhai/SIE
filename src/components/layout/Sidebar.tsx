import { CheckSquare, ClipboardList, FileBarChart2, Home, LineChart, Settings2, ShieldCheck } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '../../lib/cn';

interface NavItem {
  label: string;
  href: string;
  icon: typeof Home;
  /** `false` items render as disabled, non-navigating rows with a
   * "Coming later" note — never a fake page (§9/§22). Only Home and
   * Events are active this milestone. */
  enabled: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Home', href: '/', icon: Home, enabled: true },
  { label: 'Events', href: '/events', icon: ClipboardList, enabled: true },
  { label: 'Actions', href: '/actions', icon: CheckSquare, enabled: false },
  { label: 'Intelligence', href: '/intelligence', icon: LineChart, enabled: false },
  { label: 'Knowledge', href: '/knowledge', icon: ShieldCheck, enabled: false },
  { label: 'Reports', href: '/reports', icon: FileBarChart2, enabled: false },
  { label: 'Administration', href: '/administration', icon: Settings2, enabled: false },
];

/**
 * Primary navigation — clean, light, and easy to scan (§9): no glow, no
 * saturated badges, no per-item live counts. Only Home and Events are
 * real links; the rest render as disabled rows with a "Coming later"
 * label so the eventual information architecture is visible without
 * pretending those screens exist yet.
 */
export function Sidebar() {
  return (
    <nav aria-label="Primary" className="flex h-full w-(--width-sidebar) shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-navy-800 text-[11px] font-bold text-white">
          SIE
        </div>
        <div>
          <p className="text-sm font-semibold text-text-primary leading-tight">Safety Intelligence Engine</p>
        </div>
      </div>

      <ul className="flex flex-1 flex-col gap-0.5 p-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          if (!item.enabled) {
            return (
              <li key={item.label}>
                <div
                  aria-disabled="true"
                  className="flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm text-text-muted"
                >
                  <span className="flex items-center gap-2.5">
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {item.label}
                  </span>
                  <span className="text-[11px] text-text-muted">Coming later</span>
                </div>
              </li>
            );
          }
          return (
            <li key={item.label}>
              <NavLink
                to={item.href}
                end={item.href === '/'}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600',
                    isActive
                      ? 'bg-teal-50 text-teal-700'
                      : 'text-text-secondary hover:bg-surface-muted hover:text-text-primary',
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {item.label}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
