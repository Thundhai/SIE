import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Breadcrumb } from '../../components/layout/Breadcrumb';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { ApiError } from '../../services/api/errors';
import { getRiskAssessment, type RiskAssessmentDetail } from '../../services/api/riskAssessments';
import type { AsyncState } from '../../types/common';
import {
  assessmentScopeLabel,
  assessmentStatusLabel,
  assessmentStatusTone,
  assessmentTypeLabel,
  findingRiskClassificationLabel,
  findingRiskClassificationTone,
  findingStatusLabel,
  findingStatusTone,
} from './riskAssessmentLabels';

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

/**
 * Risk Assessment Detail — the assessment's own record plus its
 * findings' current risk ratings, read-only. Mirrors `ActionDetailPage`/
 * `EventDetailPage`'s established loading/error/not-found shape. A
 * finding's controls, effectiveness assessment, and evidence are not
 * shown here yet — see `RiskAssessmentsPage`'s own module docstring for
 * why this stays deliberately minimal in UI-01.
 */
export function RiskAssessmentDetailPage() {
  const { assessmentId } = useParams<{ assessmentId: string }>();
  const auth = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<AsyncState<RiskAssessmentDetail | null>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);

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

      {auth.organization && state.status === 'success' && state.data && <RiskAssessmentDetailContent assessment={state.data} />}
    </PageContainer>
  );
}

function RiskAssessmentDetailContent({ assessment }: { assessment: RiskAssessmentDetail }) {
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">{assessment.title}</h1>
          <p className="mt-1 text-sm text-text-secondary">
            {assessmentTypeLabel(assessment.assessment_type)} · {assessmentScopeLabel(assessment.scope)}
            {assessment.version > 1 ? ` · Version ${assessment.version}` : ''}
          </p>
        </div>
        <StatusBadge tone={assessmentStatusTone(assessment.status)} label={assessmentStatusLabel(assessment.status)} />
      </div>

      <Section title="Details">
        <dl className="grid grid-cols-2 gap-4 rounded-lg border border-border bg-surface p-4 sm:grid-cols-4">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Assessment date</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{formatDate(assessment.assessment_date)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">As of</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{formatDate(assessment.as_of)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Reference</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{assessment.reference ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Methodology version</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{assessment.methodology_version}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Submitted</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{formatDate(assessment.submitted_at)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-text-muted">Approved</dt>
            <dd className="mt-0.5 text-sm text-text-primary">{formatDate(assessment.approved_at)}</dd>
          </div>
        </dl>
      </Section>

      <Section title="Findings" description={`${assessment.findings.length} finding${assessment.findings.length === 1 ? '' : 's'} in this assessment.`}>
        {assessment.findings.length === 0 ? (
          <EmptyState title="No findings recorded" description="This assessment has no findings yet." />
        ) : (
          <ul className="flex flex-col gap-2">
            {assessment.findings.map((finding) => (
              <li key={finding.id} className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface p-3.5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-text-primary">{finding.title}</p>
                  <p className="mt-0.5 text-xs text-text-muted">{finding.risk_area.label}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={findingStatusTone(finding.status)} label={findingStatusLabel(finding.status)} />
                  <StatusBadge
                    tone={findingRiskClassificationTone(finding.residual_risk_classification ?? finding.inherent_risk_classification)}
                    label={`Residual: ${findingRiskClassificationLabel(finding.residual_risk_classification)}`}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}
