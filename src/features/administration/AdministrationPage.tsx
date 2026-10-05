import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { ADMINISTRATION_SECTION_PERMISSIONS } from '../../auth/routePermissions';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { getOrganization, type OrganizationMembership } from '../../services/api/organizations';
import {
  listSites,
  listMembers,
  listActiveGoverningStandards,
  listApiClients,
  type Site,
  type ActiveGoverningStandard,
  type ApiClient,
} from '../../services/api/administration';
import type { AsyncState } from '../../types/common';

/**
 * Administration — SIE Milestone G3-2 hardening.
 *
 * **Before this milestone**, every section below was fetched together
 * in one `Promise.all()` and rendered together behind one loading/error
 * state. That meant a user who could see, say, governing standards but
 * lacked `users:manage` (API clients — see `routePermissions.ts`'s own
 * evidence for why that section specifically needs that permission, not
 * a separate "read" one) saw the *entire page* fail with one generic
 * error, because the single combined request failed as a whole — the
 * opposite of this milestone's own "do not grant all Administration
 * access merely because a user can view one administrative section"
 * requirement, and also simply wrong UX for a real admin who has
 * *some* but not *all* of these permissions.
 *
 * Each section below is now its own independent fetch, gated on its own
 * specific permission (`ADMINISTRATION_SECTION_PERMISSIONS`) — mirroring
 * `HomePage.tsx`'s own already-established "one section's failure never
 * blanks out the rest of the page" pattern. A section whose permission
 * is missing renders nothing at all (consistent with how `Sidebar.tsx`
 * hides a nav item it has no permission for) rather than a visible
 * "you can't see this" placeholder — this page is read-only
 * administrative data, not a feature a denied user needs to be told
 * exists. The route itself still requires `organization:read` (see
 * `router.tsx`), which every role has — this page is reachable by any
 * organization member; what each member actually sees inside it is
 * what varies.
 *
 * G3-4 (not this milestone) is where create/edit/invite/rotate/revoke
 * controls get added to these sections — nothing here adds a mutation.
 */
export function AdministrationPage() {
  const auth = useAuth();

  if (!auth.organization) {
    return (
      <PageContainer>
        <h1 className="text-xl font-semibold text-navy-900">Administration</h1>
        <EmptyState
          title="No organization context available"
          description="A development identity is not configured, or it could not be resolved against the backend."
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div>
        <h1 className="text-xl font-semibold text-navy-900">Administration</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Organization configuration, sites, membership, governance, and system integrations.
        </p>
      </div>

      <OrganizationSection organizationId={auth.organization.id} />
      <SitesSection organizationId={auth.organization.id} />
      <MembersSection organizationId={auth.organization.id} />
      <GoverningStandardsSection organizationId={auth.organization.id} />
      <ApiClientsSection organizationId={auth.organization.id} />
    </PageContainer>
  );
}

// --- Organization ----------------------------------------------------------
// No entry in ADMINISTRATION_SECTION_PERMISSIONS, deliberately: the
// backend's GET /organizations/{id} has no permission requirement at
// all today (see routePermissions.ts's own docstring on this tracked,
// separate gap) -- so, pending that fix, this section is shown to
// anyone who already cleared the route-level organization:read floor.

function OrganizationSection({ organizationId }: { organizationId: string }) {
  const [state, setState] = useState<AsyncState<Awaited<ReturnType<typeof getOrganization>>>>({ status: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    getOrganization(organizationId, controller.signal)
      .then((organization) => setState({ status: 'success', data: organization }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load organization.' });
      });
    return () => controller.abort();
  }, [organizationId]);

  return (
    <Section title="Organization" description="Current tenant configuration returned by the SIE organization API.">
      {state.status === 'loading' && <LoadingState label="Loading organization…" />}
      {state.status === 'error' && <ErrorState description={state.message} />}
      {state.status === 'success' && (
        <div className="grid gap-3 sm:grid-cols-4">
          <Info label="Name" value={state.data.name} />
          <Info label="Industry" value={state.data.industry ?? '—'} />
          <Info label="Country" value={state.data.country ?? '—'} />
          <Info label="Status" value={state.data.status} />
        </div>
      )}
    </Section>
  );
}

// --- Sites -------------------------------------------------------------

function SitesSection({ organizationId }: { organizationId: string }) {
  const auth = useAuth();
  const permitted = auth.hasPermission(ADMINISTRATION_SECTION_PERMISSIONS.sites);
  const [state, setState] = useState<AsyncState<Site[]>>({ status: 'loading' });

  useEffect(() => {
    if (!permitted) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    listSites(organizationId, controller.signal)
      .then((sites) => setState({ status: 'success', data: sites }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load sites.' });
      });
    return () => controller.abort();
  }, [organizationId, permitted]);

  if (!permitted) return null;

  return (
    <Section title="Sites" description="Sites currently registered to this organization.">
      {state.status === 'loading' && <LoadingState label="Loading sites…" />}
      {state.status === 'error' && <ErrorState description={state.message} />}
      {state.status === 'success' &&
        (state.data.length === 0 ? (
          <EmptyState title="No sites registered" description="No organization sites are currently available." />
        ) : (
          <Table
            headers={['Site', 'Location', 'Country', 'Status']}
            rows={state.data.map((s) => [s.name, s.location ?? '—', s.country ?? '—', s.status])}
          />
        ))}
    </Section>
  );
}

// --- Users & membership --------------------------------------------------

function MembersSection({ organizationId }: { organizationId: string }) {
  const auth = useAuth();
  const permitted = auth.hasPermission(ADMINISTRATION_SECTION_PERMISSIONS.members);
  const [state, setState] = useState<AsyncState<OrganizationMembership[]>>({ status: 'loading' });

  useEffect(() => {
    if (!permitted) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    listMembers(organizationId, controller.signal)
      .then((members) => setState({ status: 'success', data: members }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load members.' });
      });
    return () => controller.abort();
  }, [organizationId, permitted]);

  if (!permitted) return null;

  return (
    <Section
      title="Users & membership"
      description="Organization memberships and assigned roles. The current API intentionally exposes user IDs rather than profile details here."
    >
      {state.status === 'loading' && <LoadingState label="Loading members…" />}
      {state.status === 'error' && <ErrorState description={state.message} />}
      {state.status === 'success' &&
        (state.data.length === 0 ? (
          <EmptyState title="No members found" description="No organization memberships were returned." />
        ) : (
          <Table
            headers={['User ID', 'Role', 'Status']}
            rows={state.data.map((m) => [m.user_id, m.role, m.status])}
            monoFirst
          />
        ))}
    </Section>
  );
}

// --- Governing standards ---------------------------------------------------

function GoverningStandardsSection({ organizationId }: { organizationId: string }) {
  const auth = useAuth();
  const permitted = auth.hasPermission(ADMINISTRATION_SECTION_PERMISSIONS.standards);
  const [state, setState] = useState<AsyncState<ActiveGoverningStandard[]>>({ status: 'loading' });

  useEffect(() => {
    if (!permitted) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    listActiveGoverningStandards(organizationId, controller.signal)
      .then((result) => setState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load governing standards.' });
      });
    return () => controller.abort();
  }, [organizationId, permitted]);

  if (!permitted) return null;

  return (
    <Section
      title="Governing standards"
      description="Explicitly selected organizational standards. Selection does not by itself establish applicability."
    >
      {state.status === 'loading' && <LoadingState label="Loading governing standards…" />}
      {state.status === 'error' && <ErrorState description={state.message} />}
      {state.status === 'success' &&
        (state.data.length === 0 ? (
          <EmptyState
            title="No governing standards selected"
            description="The organization currently has no explicitly selected active governing standards."
          />
        ) : (
          <div className="grid gap-2">
            {state.data.map((item) => (
              <div key={item.selection.id} className="rounded-lg border border-border bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">{item.standard.name}</p>
                    <p className="mt-1 text-xs text-text-secondary">
                      {item.standard.issuing_organization} · {item.standard.standard_type}
                      {item.standard.version ? ' · ' + item.standard.version : ''}
                    </p>
                  </div>
                  <StatusBadge tone="success" label={item.selection.status} />
                </div>
              </div>
            ))}
          </div>
        ))}
    </Section>
  );
}

// --- API clients -----------------------------------------------------------

function ApiClientsSection({ organizationId }: { organizationId: string }) {
  const auth = useAuth();
  const permitted = auth.hasPermission(ADMINISTRATION_SECTION_PERMISSIONS.apiClients);
  const [state, setState] = useState<AsyncState<ApiClient[]>>({ status: 'loading' });

  useEffect(() => {
    if (!permitted) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    listApiClients(organizationId, controller.signal)
      .then((clients) => setState({ status: 'success', data: clients }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load API clients.' });
      });
    return () => controller.abort();
  }, [organizationId, permitted]);

  if (!permitted) return null;

  return (
    <Section
      title="API clients"
      description="Machine-client credentials registered for system-to-system integration. Secrets are never displayed by the list endpoint."
    >
      {state.status === 'loading' && <LoadingState label="Loading API clients…" />}
      {state.status === 'error' && <ErrorState description={state.message} />}
      {state.status === 'success' &&
        (state.data.length === 0 ? (
          <EmptyState
            title="No API clients"
            description="No machine-client credentials are currently registered for this organization."
          />
        ) : (
          <Table
            headers={['Name', 'Client ID', 'Status', 'Scopes', 'Expires']}
            rows={state.data.map((c) => [
              c.name,
              c.client_id,
              c.status,
              c.scopes.join(', '),
              c.expires_at ? new Date(c.expires_at).toLocaleDateString() : 'No expiry',
            ])}
          />
        ))}
    </Section>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-1 font-medium text-text-primary">{value}</p>
    </div>
  );
}

function Table({ headers, rows, monoFirst = false }: { headers: string[]; rows: string[][]; monoFirst?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[650px] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
            {headers.map((h) => (
              <th key={h} className="px-3 py-2">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border">
              {row.map((v, j) => (
                <td key={j} className={'px-3 py-3' + (monoFirst && j === 0 ? ' font-mono text-xs' : '')}>
                  {v}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
