import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { Pagination } from '../../components/ui/Pagination';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Table, type TableColumn } from '../../components/ui/Table';
import { listRiskAssessments, type RiskAssessmentSummary } from '../../services/api/riskAssessments';
import type { AsyncState, Page } from '../../types/common';
import { assessmentScopeLabel, assessmentStatusLabel, assessmentStatusTone, assessmentTypeLabel } from './riskAssessmentLabels';

const PAGE_SIZE = 10;

/**
 * Risk Assessments — a minimal, read-only list of the organization's
 * enterprise risk assessments (SIE Milestones 25-29A), backed by the
 * real `GET /risk-assessments` endpoint (`RISK_ASSESSMENT_READ`).
 *
 * Deliberately minimal for UI-01: findings, controls, effectiveness
 * assessment, evidence, and the Milestone 28 report stay for a later UI
 * milestone (per the milestone's own explicit scope note) — this screen
 * exists so the completed Risk Assessment capability is not left
 * entirely invisible, not to reproduce its full workflow.
 */
export function RiskAssessmentsPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<AsyncState<Page<RiskAssessmentSummary>>>({ status: 'loading' });

  useEffect(() => {
    if (!auth.organization) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    listRiskAssessments({ organizationId: auth.organization.id, page, pageSize: PAGE_SIZE, signal: controller.signal })
      .then((result) =>
        setState({ status: 'success', data: { items: result.items, total: result.total, page: result.page, pageSize: result.page_size } }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load risk assessments.' });
      });
    return () => controller.abort();
  }, [auth.organization, page, reloadToken]);

  const isPermissionDenied = state.status === 'error' && state.message.toLowerCase().includes('missing') && state.message.toLowerCase().includes('permission');

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
        <h1 className="text-xl font-semibold text-text-primary">Risk Assessments</h1>
        <p className="mt-1 text-sm text-text-secondary">Formal enterprise risk assessments and their current status.</p>
      </div>

      {!auth.organization && (
        <EmptyState
          title="No organization context available"
          description="A development identity is not configured, or it could not be resolved against the backend. See docs/FRONTEND_ARCHITECTURE.md for setup."
        />
      )}

      {auth.organization && state.status === 'loading' && <LoadingState label="Loading risk assessments…" />}

      {auth.organization && state.status === 'error' && isPermissionDenied && (
        <EmptyState title="You don't have permission to view this" description="Ask an administrator for risk_assessment:read access in this organization." />
      )}

      {auth.organization && state.status === 'error' && !isPermissionDenied && (
        <ErrorState title="Could not load risk assessments" description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {auth.organization && state.status === 'success' && (
        <Section title="All assessments">
          {state.data.items.length === 0 ? (
            <EmptyState title="No risk assessments yet" description="No enterprise risk assessments have been created for this organization." />
          ) : (
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
