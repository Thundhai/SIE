import {
  CheckSquare,
  ClipboardList,
  FileBarChart2,
  Home,
  LineChart,
  Settings2,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { ROUTE_PERMISSIONS } from '../../auth/routePermissions';
import type { PermissionKey } from '../../auth/types';
import { cn } from '../../lib/cn';

interface NavItem {
  label: string;
  href: string;
  icon: typeof Home;
  /** The SAME permission `router.tsx`'s `PermissionRoute` enforces for
   * this route (both read from `auth/routePermissions.ts` — SIE
   * Milestone G3-2's own "do not duplicate permission logic between
   * Sidebar and router" requirement). `undefined` for a route with no
   * permission requirement beyond authentication (Home). Hiding an item
   * here is a navigation convenience only — it is never the security
   * boundary; a direct URL to a route this hides still hits
   * `PermissionRoute` and is denied there independently. */
  requiredPermission?: PermissionKey;
  /** Which brand color the active state uses (SIE Milestone UI-DESIGN-01).
   * Teal is the SIE *intelligence* accent specifically — reserved for the
   * Intelligence nav item (and its own tabs) — never a generic "this is
   * selected" color. Every other real item uses the navy structural-active
   * treatment instead. Defaults to `'navy'`. */
  accent?: 'navy' | 'teal';
}

interface NavGroup {
  /** `undefined` for Home, which stands alone above the grouped
   * sections — every other group gets a small uppercase heading, mirroring
   * the approved SIE information architecture (Home / Work / Intelligence
   * / Knowledge / Reporting / Administration). */
  heading?: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  { items: [{ label: 'Home', href: '/', icon: Home }] },
  {
    heading: 'Work',
    items: [
      { label: 'Events', href: '/events', icon: ClipboardList, requiredPermission: ROUTE_PERMISSIONS.events },
      { label: 'Actions', href: '/actions', icon: CheckSquare, requiredPermission: ROUTE_PERMISSIONS.actions },
      {
        label: 'Risk Assessments',
        href: '/risk-assessments',
        icon: ShieldAlert,
        requiredPermission: ROUTE_PERMISSIONS.riskAssessments,
      },
    ],
  },
  {
    heading: 'Intelligence',
    items: [
      {
        label: 'Intelligence',
        href: '/intelligence',
        icon: LineChart,
        requiredPermission: ROUTE_PERMISSIONS.intelligence,
        accent: 'teal',
      },
    ],
  },
  {
    heading: 'Knowledge',
    items: [{ label: 'Knowledge', href: '/knowledge', icon: ShieldCheck, requiredPermission: ROUTE_PERMISSIONS.knowledge }],
  },
  {
    heading: 'Reporting',
    items: [{ label: 'Reports', href: '/reports', icon: FileBarChart2, requiredPermission: ROUTE_PERMISSIONS.reports }],
  },
  {
    heading: 'Administration',
    items: [
      {
        label: 'Administration',
        href: '/administration',
        icon: Settings2,
        requiredPermission: ROUTE_PERMISSIONS.administration,
      },
    ],
  },
];

/**
 * Primary navigation — clean, light, and easy to scan (§9): no glow, no
 * saturated badges, no per-item live counts. Grouped into the approved
 * SIE information architecture (Home / Work / Intelligence / Knowledge /
 * Reporting / Administration) with small, restrained uppercase group
 * headings — never a second visual system layered on top of the plain
 * link list.
 *
 * **Permission-aware (SIE Milestone G3-2).** An item renders only when
 * `auth.hasPermission(item.requiredPermission)` — the same check
 * `PermissionRoute` makes for the route it links to (`routePermissions.ts`
 * is the one shared source for both). This is a navigation convenience
 * only, never the security boundary: hiding a link here does not and
 * cannot stop a direct URL/deep link to that route, which
 * `PermissionRoute` denies independently regardless of what this
 * component renders. A group heading is omitted too when every item in
 * that group is hidden, so no empty section ever appears.
 *
 * SIE Milestone UI-DESIGN-01: a stronger `border-border-strong` right
 * edge gives the rail a clearer separation from the canvas than v0.1's
 * hairline `border-border`, and the wordmark now takes the navy brand
 * color rather than generic body text — both "sidebar" requirements
 * (subtle separation from canvas; navy brand treatment) — while the
 * sidebar's own fill stays white/light, per that section's explicit "do
 * NOT turn dark" instruction. Active-item color is now split by accent
 * (see `NavItem.accent`): navy for ordinary structural navigation, teal
 * reserved for Intelligence alone, so teal keeps one consistent meaning
 * across the app.
 */
export function Sidebar() {
  const auth = useAuth();

  return (
    <nav aria-label="Primary" className="flex h-full w-(--width-sidebar) shrink-0 flex-col border-r border-border-strong bg-surface">
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-navy-800 text-[11px] font-bold text-white">
          SIE
        </div>
        <div>
          <p className="text-sm font-semibold text-navy-900 leading-tight">Safety Intelligence Engine</p>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-2">
        {NAV_GROUPS.map((group) => {
          const visibleItems = group.items.filter(
            (item) => !item.requiredPermission || auth.hasPermission(item.requiredPermission),
          );
          if (visibleItems.length === 0) return null;

          return (
            <div key={group.heading ?? 'home'}>
              {group.heading && (
                <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted">{group.heading}</p>
              )}
              <ul className="flex flex-col gap-0.5">
                {visibleItems.map((item) => {
                  const Icon = item.icon;
                  const activeClass = item.accent === 'teal' ? 'bg-teal-50 text-teal-700' : 'bg-navy-50 text-navy-900';
                  return (
                    <li key={item.label}>
                      <NavLink
                        to={item.href}
                        end={item.href === '/'}
                        className={({ isActive }) =>
                          cn(
                            'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600',
                            isActive ? activeClass : 'text-text-secondary hover:bg-surface-muted hover:text-text-primary',
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
            </div>
          );
        })}
      </div>
    </nav>
  );
}
