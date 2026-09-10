import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Breadcrumb } from '../../components/layout/Breadcrumb';
import { PageContainer } from '../../components/layout/PageContainer';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Tabs } from '../../components/ui/Tabs';
import { ApiError } from '../../services/api/errors';
import { getRiskAssessment, type RiskAssessmentDetail, type RiskAssessmentFinding } from '../../services/api/riskAssessments';
import type { AsyncState } from '../../types/common';
import { RiskAssessmentActionsTab } from './RiskAssessmentActionsTab';
import { RiskAssessmentControlsTab } from './RiskAssessmentControlsTab';
import { RiskAssessmentEvidenceTab } from './RiskAssessmentEvidenceTab';
import { RiskAssessmentFindingsTab } from './RiskAssessmentFindingsTab';
import { RiskAssessmentOverviewTab } from './RiskAssessmentOverviewTab';
import {
  assessmentScopeLabel,
  assessmentStatusLabel,
  assessmentStatusTone,
  assessmentTypeLabel,
} from './riskAssessmentLabels';

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

const ASSESSMENT_EDITABLE_STATUSES = new Set(['DRAFT', 'IN_REVIEW']);

type TabValue = 'overview' | 'findings' | 'controls' | 'actions' | 'evidence';

/**
 * Risk Assessment Detail — the main assessment workspace (SIE Milestone
 * UI-02, Part 2): Overview / Findings / Controls / Actions / Evidence.
 * Every tab is presentation over the real, already-built backend APIs —
 * nothing here recalculates a risk rating, invents an endpoint, or
 * bypasses the M29A dedicated control-effectiveness mutation path.
 */
export function RiskAssessmentDetailPage() {
  const { assessmentId } = useParams<{ assessmentId: string }>();
  const auth = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<AsyncState<RiskAssessmentDetail | null>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);
  const [tab, setTab] = useState<TabValue>('overview');

  useEffect(() => {
    if (!assessmentId || !auth.organization) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    getRiskAssessment(auth.organization.id, assessmentId, controller.signal)
      .then((detail) => setState({ status: 'success', data: detail }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) {
          setState({ status: 'success', data: null });
          return;
        }
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load this risk assessment.' });
      });
    return () => controller.abort();
  }, [auth.organization, assessmentId, reloadToken]);

  const isPermissionDenied = state.status === 'error' && state.message.toLowerCase().includes('missing') && state.message.toLowerCase().includes('permission');

  function handleFindingChanged(updated: RiskAssessmentFinding) {
    setState((current) => {
      if (current.status !== 'success' || !current.data) return current;
      return {
        status: 'success',
        data: { ...current.data, findings: current.data.findings.map((f) => (f.id === updated.id ? updated : f)) },
      };
    });
  }

  return (
    <PageContainer>
      <Breadcrumb
        items={[
          { label: 'Risk Assessments', href: '/risk-assessments' },
          { label: state.status === 'success' && state.data ? state.data.title : 'Assessment detail' },
        ]}
      />

      {!auth.organization && (
        <EmptyState
          title="No organization context available"
          description="A development identity is not configured, or it could not be resolved against the backend."
        />
      )}

      {auth.organization && state.status === 'loading' && <LoadingState label="Loading risk assessment…" />}

      {auth.organization && state.status === 'error' && isPermissionDenied && (
        <EmptyState title="You don't have permission to view this" description="Ask an administrator for risk_assessment:read access in this organization." />
      )}

      {auth.organization && state.status === 'error' && !isPermissionDenied && (
        <ErrorState description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {auth.organization && state.status === 'success' && state.data === null && (
        <EmptyState
          title="Risk assessment not found"
          description="This assessment may have been removed, or the link may be incorrect."
          action={
            <Button variant="secondary" size="sm" onClick={() => navigate('/risk-assessments')}>
              Back to Risk Assessments
            </Button>
          }
        />
      )}

      {auth.organization && state.status === 'success' && state.data && (
        <RiskAssessmentDetailContent
          organizationId={auth.organization.id}
          assessment={state.data}
          tab={tab}
          onTabChange={setTab}
          onFindingChanged={handleFindingChanged}
        />
      )}
    </PageContainer>
  );
}

function RiskAssessmentDetailContent({
  organizationId,
  assessment,
  tab,
  onTabChange,
  onFindingChanged,
}: {
  organizationId: string;
  assessment: RiskAssessmentDetail;
  tab: TabValue;
  onTabChange: (tab: TabValue) => void;
  onFindingChanged: (finding: RiskAssessmentFinding) => void;
}) {
  const isEditable = ASSESSMENT_EDITABLE_STATUSES.has(assessment.status);

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-navy-900">Risk Assessment</h1>
          <p className="mt-1 text-lg font-medium text-text-primary">
            {assessment.title}
            {assessment.reference ? ` · ${assessment.reference}` : ''}
          </p>
          <p className="mt-1 text-sm text-text-secondary">
            {assessmentTypeLabel(assessment.assessment_type)} · {assessmentScopeLabel(assessment.scope)}
            {assessment.version > 1 ? ` · Version ${assessment.version}` : ''} · {formatDate(assessment.assessment_date)}
          </p>
        </div>
        <StatusBadge tone={assessmentStatusTone(assessment.status)} label={assessmentStatusLabel(assessment.status)} />
      </div>

      <Tabs
        items={[
          { value: 'overview', label: 'Overview' },
          { value: 'findings', label: `Findings (${assessment.findings.length})` },
          { value: 'controls', label: 'Controls' },
          { value: 'actions', label: 'Actions' },
          { value: 'evidence', label: 'Evidence' },
        ]}
        value={tab}
        onChange={(value) => onTabChange(value as TabValue)}
      />

      <div>
        {tab === 'overview' && <RiskAssessmentOverviewTab organizationId={organizationId} assessmentId={assessment.id} />}
        {tab === 'findings' && (
          <RiskAssessmentFindingsTab
            organizationId={organizationId}
            assessmentId={assessment.id}
            findings={assessment.findings}
            isEditable={isEditable}
            onFindingChanged={onFindingChanged}
          />
        )}
        {tab === 'controls' && (
          <RiskAssessmentControlsTab
            organizationId={organizationId}
            assessmentId={assessment.id}
            findings={assessment.findings}
            isEditable={isEditable}
            onFindingChanged={onFindingChanged}
          />
        )}
        {tab === 'actions' && (
          <RiskAssessmentActionsTab organizationId={organizationId} assessmentId={assessment.id} findings={assessment.findings} />
        )}
        {tab === 'evidence' && <RiskAssessmentEvidenceTab findings={assessment.findings} />}
      </div>
    </>
  );
}
