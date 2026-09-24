import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { getOrganization, listMembers, type Organization, type OrganizationMembership } from '../../services/api/organizations';
import { listSites, type Site } from '../../services/api/administration';
import { ApiError } from '../../services/api/errors';
import type { AsyncState } from '../../types/common';
import { AddMemberDrawer } from './AddMemberDrawer';
import { ApiClientsSection } from './ApiClientsSection';
import { CreateSiteDrawer } from './CreateSiteDrawer';
import { GoverningStandardsSection } from './GoverningStandardsSection';
import { membershipStatusLabel, membershipStatusTone, organizationRoleLabel } from './administrationLabels';

/**
 * Administration. Every section here calls a real, already-existing
 * backend endpoint — nothing is invented. Organization has no update
 * endpoint (`app/api/v1/organizations.py` exposes only create + get), so
 * it is deliberately read-only. Sites/Users have create-only backend
 * support (no edit/delete routes), so this page offers create but never
 * edit or delete for them either. Governing Standards and API Clients
 * are each delegated to their own self-contained section component.
 */
export function AdministrationPage() {
  const auth = useAuth();
  const organizationId = auth.organization?.id ?? null;

  const [organizationState, setOrganizationState] = useState<AsyncState<Organization>>({ status: 'loading' });

  const [sitesState, setSitesState] = useState<AsyncState<Site[]>>({ status: 'loading' });
  const [sitesRefreshToken, setSitesRefreshToken] = useState(0);
  const [createSiteOpen, setCreateSiteOpen] = useState(false);

  const [membersState, setMembersState] = useState<AsyncState<OrganizationMembership[]>>({ status: 'loading' });
  const [membersRefreshToken, setMembersRefreshToken] = useState(0);
  const [addMemberOpen, setAddMemberOpen] = useState(false);

  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    setOrganizationState({ status: 'loading' });
    getOrganization(organizationId, controller.signal)
      .then((organization) => setOrganizationState({ status: 'success', data: organization }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setOrganizationState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load organization details.' });
      });
    return () => controller.abort();
  }, [organizationId]);

  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    setSitesState({ status: 'loading' });
    listSites(organizationId, controller.signal)
      .then((sites) => setSitesState({ status: 'success', data: sites }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setSitesState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load sites.' });
      });
    return () => controller.abort();
  }, [organizationId, sitesRefreshToken]);

  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    setMembersState({ status: 'loading' });
    listMembers(organizationId, controller.signal)
      .then((members) => setMembersState({ status: 'success', data: members }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 403) {
          setMembersState({ status: 'error', message: "You don't have permission to view members of this organization." });
        } else {
          setMembersState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load members.' });
        }
      });
    return () => controller.abort();
  }, [organizationId, membersRefreshToken]);

  if (!organizationId) {
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

      <Section title="Organization" description="Current tenant configuration returned by the SIE organization API. Read-only — no update endpoint exists yet.">
        {organizationState.status === 'loading' && <LoadingState label="Loading organization…" />}
        {organizationState.status === 'error' && <ErrorState description={organizationState.message} />}
        {organizationState.status === 'success' && (
          <div className="grid gap-3 sm:grid-cols-4">
            <Info label="Name" value={organizationState.data.name} />
            <Info label="Industry" value={organizationState.data.industry ?? '—'} />
            <Info label="Country" value={organizationState.data.country ?? '—'} />
            <Info label="Status" value={organizationState.data.status} />
          </div>
        )}
      </Section>

      <Section
        title="Sites"
        description="Sites registered to this organization."
        action={
          <Button size="sm" onClick={() => setCreateSiteOpen(true)}>
            Create site
          </Button>
        }
      >
        {sitesState.status === 'loading' && <LoadingState label="Loading sites…" />}
        {sitesState.status === 'error' && <ErrorState description={sitesState.message} />}
        {sitesState.status === 'success' && sitesState.data.length === 0 && (
          <EmptyState title="No sites registered" description="No organization sites are currently available." />
        )}
        {sitesState.status === 'success' && sitesState.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[650px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-3 py-2">Site</th>
                  <th className="px-3 py-2">Location</th>
                  <th className="px-3 py-2">Country</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {sitesState.data.map((site) => (
                  <tr key={site.id} className="border-b border-border">
                    <td className="px-3 py-3 font-medium text-text-primary">{site.name}</td>
                    <td className="px-3 py-3 text-text-secondary">{site.location ?? '—'}</td>
                    <td className="px-3 py-3 text-text-secondary">{site.country ?? '—'}</td>
                    <td className="px-3 py-3 text-text-secondary">{site.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section
        title="Users & membership"
        description="Organization memberships and assigned roles. The backend intentionally exposes user IDs rather than profile details here — no name/email lookup exists."
        action={
          <Button size="sm" onClick={() => setAddMemberOpen(true)}>
            Add member
          </Button>
        }
      >
        {membersState.status === 'loading' && <LoadingState label="Loading members…" />}
        {membersState.status === 'error' && <ErrorState description={membersState.message} />}
        {membersState.status === 'success' && membersState.data.length === 0 && (
          <EmptyState title="No members found" description="No organization memberships were returned." />
        )}
        {membersState.status === 'success' && membersState.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[650px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-3 py-2">User ID</th>
                  <th className="px-3 py-2">Role</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {membersState.data.map((member) => (
                  <tr key={member.id} className="border-b border-border">
                    <td className="px-3 py-3 font-mono text-xs text-text-secondary">{member.user_id}</td>
                    <td className="px-3 py-3 text-text-primary">{organizationRoleLabel(member.role)}</td>
                    <td className="px-3 py-3">
                      <StatusBadge tone={membershipStatusTone(member.status)} label={membershipStatusLabel(member.status)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <GoverningStandardsSection organizationId={organizationId} />

      <ApiClientsSection organizationId={organizationId} />

      <CreateSiteDrawer
        isOpen={createSiteOpen}
        onClose={() => setCreateSiteOpen(false)}
        organizationId={organizationId}
        onCreated={() => setSitesRefreshToken((token) => token + 1)}
      />
      <AddMemberDrawer
        isOpen={addMemberOpen}
        onClose={() => setAddMemberOpen(false)}
        organizationId={organizationId}
        onAdded={() => setMembersRefreshToken((token) => token + 1)}
      />
    </PageContainer>
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
