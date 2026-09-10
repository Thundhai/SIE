import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { FilterBar } from '../../components/ui/FilterBar';
import { LoadingState } from '../../components/ui/LoadingState';
import { Pagination } from '../../components/ui/Pagination';
import { Select } from '../../components/ui/Select';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Table, type TableColumn } from '../../components/ui/Table';
import { listRiskAssessments, type RiskAssessmentSummary } from '../../services/api/riskAssessments';
import { listSites, type Site } from '../../services/api/sites';
import type { AsyncState, Page } from '../../types/common';
import { assessmentScopeLabel, assessmentStatusLabel, assessmentStatusTone, assessmentTypeLabel } from './riskAssessmentLabels';

const PAGE_SIZE = 10;

const STATUS_OPTIONS = ['DRAFT', 'IN_REVIEW', 'APPROVED', 'SUPERSEDED', 'ARCHIVED'].map((value) => ({
  value,
  label: assessmentStatusLabel(value),
}));

const SCOPE_OPTIONS = ['ORGANIZATION', 'LOCATION', 'SITE'].map((value) => ({ value, label: assessmentScopeLabel(value) }));

/**
 * Risk Assessments — the organization's enterprise risk assessments
 * (SIE Milestones 25-29A), backed by the real `GET /risk-assessments`
 * endpoint (`RISK_ASSESSMENT_READ`). Filtering is limited to what the
 * backend actually supports (`status`, `scope`, `site_id` — SIE
 * Milestone UI-02 Part 1); there is no assessment-type, risk-level, or
 * free-text search filter on this endpoint, so none is offered here.
 * Never falls back to fixture data — a real organization with no
 * assessments shows an honest empty state instead.
 */
export function RiskAssessmentsPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [scope, setScope] = useState('');
  const [siteId, setSiteId] = useState('');
  const [siteOptions, setSiteOptions] = useState<Site[]>([]);
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<AsyncState<Page<RiskAssessmentSummary>>>({ status: 'loading' });

  useEffect(() => {
    if (!auth.organization) return;
    let cancelled = false;
    listSites(auth.organization.id)
      .then((sites) => {
        if (!cancelled) setSiteOptions(sites);
      })
      .catch(() => {
        if (!cancelled) setSiteOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [auth.organization]);

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    listRiskAssessments({
      organizationId: auth.organization.id,
      page,
      pageSize: PAGE_SIZE,
      status: status || undefined,
      scope: scope || undefined,
      siteId: siteId || undefined,
      signal: controller.signal,
    })
      .then((result) =>
        setState({ status: 'success', data: { items: result.items, total: result.total, page: result.page, pageSize: result.page_size } }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load risk assessments.' });
      });
    return () => controller.abort();
  }, [auth.organization, page, status, scope, siteId, reloadToken]);

  const isPermissionDenied = state.status === 'error' && state.message.toLowerCase().includes('missing') && state.message.toLowerCase().includes('permission');
  const hasActiveFilters = Boolean(status || scope || siteId);

  const columns: TableColumn<RiskAssessmentSummary>[] = [
    {
      key: 'title',
      header: 'Assessment',
      render: (row) => (
        <div>
          <p className="font-medium text-text-primary">{row.title}</p>
          <p className="text-xs text-text-muted">
            {assessmentTypeLabel(row.assessment_type)} · {assessmentScopeLabel(row.scope)}
            {row.version > 1 ? ` · v${row.version}` : ''}
          </p>
        </div>
      ),
    },
    { key: 'status', header: 'Status', render: (row) => <StatusBadge tone={assessmentStatusTone(row.status)} label={assessmentStatusLabel(row.status)} /> },
    {
      key: 'assessment_date',
      header: 'Assessment date',
      render: (row) => new Date(row.assessment_date).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }),
    },
    { key: 'reference', header: 'Reference', render: (row) => row.reference ?? '—' },
  ];

  return (
    <PageContainer>
      <div>
        <h1 className="text-xl font-semibold text-navy-900">Risk Assessments</h1>
        <p className="mt-1 text-sm text-text-secondary">Formal enterprise risk assessments and their current status.</p>
      </div>

      {!auth.organization && (
        <EmptyState
          title="No organization context available"
          description="A development identity is not configured, or it could not be resolved against the backend. See docs/FRONTEND_ARCHITECTURE.md for setup."
        />
      )}

      {auth.organization && (
        <Section title="All assessments">
          <FilterBar
            onClear={() => {
              setStatus('');
              setScope('');
              setSiteId('');
              setPage(1);
            }}
            hasActiveFilters={hasActiveFilters}
          >
            <div className="w-44">
              <Select
                label="Status"
                options={[{ value: '', label: 'All statuses' }, ...STATUS_OPTIONS]}
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="w-44">
              <Select
                label="Scope"
                options={[{ value: '', label: 'All scopes' }, ...SCOPE_OPTIONS]}
                value={scope}
                onChange={(event) => {
                  setScope(event.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="w-48">
              <Select
                label="Site"
                options={[{ value: '', label: 'All sites' }, ...siteOptions.map((site) => ({ value: site.id, label: site.name }))]}
                value={siteId}
                onChange={(event) => {
                  setSiteId(event.target.value);
                  setPage(1);
                }}
              />
            </div>
          </FilterBar>

          {state.status === 'loading' && <LoadingState label="Loading risk assessments…" />}

          {state.status === 'error' && isPermissionDenied && (
            <EmptyState title="You don't have permission to view this" description="Ask an administrator for risk_assessment:read access in this organization." />
          )}

          {state.status === 'error' && !isPermissionDenied && (
            <ErrorState title="Could not load risk assessments" description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
          )}

          {state.status === 'success' && state.data.items.length === 0 && (
            <EmptyState
              title={hasActiveFilters ? 'No risk assessments match your filters' : 'No risk assessments yet'}
              description={
                hasActiveFilters
                  ? 'Try adjusting or clearing your filters.'
                  : 'No enterprise risk assessments have been created for this organization.'
              }
            />
          )}

          {state.status === 'success' && state.data.items.length > 0 && (
            <>
              <Table
                columns={columns}
                rows={state.data.items}
                getRowKey={(row) => row.id}
                onRowClick={(row) => navigate(`/risk-assessments/${row.id}`)}
                caption="Risk assessments"
              />
              <Pagination page={state.data.page} pageSize={state.data.pageSize} total={state.data.total} onPageChange={setPage} />
            </>
          )}
        </Section>
      )}
    </PageContainer>
  );
}
