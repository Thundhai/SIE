import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { getOrganization, type OrganizationMembership } from '../../services/api/organizations';
import { listSites, listMembers, listActiveGoverningStandards, listApiClients, type Site, type ActiveGoverningStandard, type ApiClient } from '../../services/api/administration';

export function AdministrationPage() {
  const auth = useAuth();
  const [organization, setOrganization] = useState<Awaited<ReturnType<typeof getOrganization>> | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [members, setMembers] = useState<OrganizationMembership[]>([]);
  const [standards, setStandards] = useState<ActiveGoverningStandard[]>([]);
  const [clients, setClients] = useState<ApiClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setLoading(true); setError(null);
    Promise.all([
      getOrganization(auth.organization.id, controller.signal),
      listSites(auth.organization.id, controller.signal),
      listMembers(auth.organization.id, controller.signal),
      listActiveGoverningStandards(auth.organization.id, controller.signal),
      listApiClients(auth.organization.id, controller.signal),
    ]).then(([org, siteRows, memberRows, standardRows, clientRows]) => {
      setOrganization(org); setSites(siteRows); setMembers(memberRows); setStandards(standardRows.items); setClients(clientRows);
    }).catch((e: unknown) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not load administration data.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [auth.organization]);

  if (!auth.organization) return <PageContainer><h1 className="text-xl font-semibold text-navy-900">Administration</h1><EmptyState title="No organization context available" description="A development identity is not configured, or it could not be resolved against the backend." /></PageContainer>;

  return <PageContainer>
    <div><h1 className="text-xl font-semibold text-navy-900">Administration</h1><p className="mt-1 text-sm text-text-secondary">Organization configuration, sites, membership, governance, and system integrations.</p></div>
    {loading && <LoadingState label="Loading administration data…" />}
    {error && !loading && <ErrorState title="Could not load administration data" description={error} onRetry={() => window.location.reload()} />}
    {!loading && !error && organization && <>
      <Section title="Organization" description="Current tenant configuration returned by the SIE organization API.">
        <div className="grid gap-3 sm:grid-cols-4"><Info label="Name" value={organization.name} /><Info label="Industry" value={organization.industry ?? '—'} /><Info label="Country" value={organization.country ?? '—'} /><Info label="Status" value={organization.status} /></div>
      </Section>
      <Section title="Sites" description="Sites currently registered to this organization.">
        {sites.length === 0 ? <EmptyState title="No sites registered" description="No organization sites are currently available." /> : <Table headers={['Site','Location','Country','Status']} rows={sites.map(s => [s.name, s.location ?? '—', s.country ?? '—', s.status])} />}
      </Section>
      <Section title="Users & membership" description="Organization memberships and assigned roles. The current API intentionally exposes user IDs rather than profile details here.">
        {members.length === 0 ? <EmptyState title="No members found" description="No organization memberships were returned." /> : <Table headers={['User ID','Role','Status']} rows={members.map(m => [m.user_id, m.role, m.status])} monoFirst />}
      </Section>
      <Section title="Governing standards" description="Explicitly selected organizational standards. Selection does not by itself establish applicability.">
        {standards.length === 0 ? <EmptyState title="No governing standards selected" description="The organization currently has no explicitly selected active governing standards." /> : <div className="grid gap-2">{standards.map(item => <div key={item.selection.id} className="rounded-lg border border-border bg-surface p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{item.standard.name}</p><p className="mt-1 text-xs text-text-secondary">{item.standard.issuing_organization} · {item.standard.standard_type}{item.standard.version ? ' · ' + item.standard.version : ''}</p></div><StatusBadge tone="success" label={item.selection.status} /></div></div>)}</div>}
      </Section>
      <Section title="API clients" description="Machine-client credentials registered for system-to-system integration. Secrets are never displayed by the list endpoint.">
        {clients.length === 0 ? <EmptyState title="No API clients" description="No machine-client credentials are currently registered for this organization." /> : <Table headers={['Name','Client ID','Status','Scopes','Expires']} rows={clients.map(c => [c.name, c.client_id, c.status, c.scopes.join(', '), c.expires_at ? new Date(c.expires_at).toLocaleDateString() : 'No expiry'])} />}
      </Section>
    </>}
  </PageContainer>;
}

function Info({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-border bg-surface p-4"><p className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</p><p className="mt-1 font-medium text-text-primary">{value}</p></div>; }
function Table({ headers, rows, monoFirst = false }: { headers: string[]; rows: string[][]; monoFirst?: boolean }) { return <div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead><tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">{headers.map(h => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead><tbody>{rows.map((row,i) => <tr key={i} className="border-b border-border">{row.map((v,j) => <td key={j} className={'px-3 py-3' + (monoFirst && j === 0 ? ' font-mono text-xs' : '')}>{v}</td>)}</tr>)}</tbody></table></div>; }