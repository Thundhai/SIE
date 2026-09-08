import { useEffect, useState } from 'react';
import { Section } from '../../components/layout/Section';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { getRiskAssessmentReport, type RiskAssessmentReport } from '../../services/api/riskAssessments';
import type { AsyncState } from '../../types/common';
import { readinessStatusLabel, readinessStatusTone } from './riskAssessmentLabels';

export interface RiskAssessmentOverviewTabProps {
  organizationId: string;
  assessmentId: string;
}

function StatTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold text-navy-900">{value}</p>
    </div>
  );
}

/**
 * Overview — "What is this assessment? What is its current status? What
 * risk picture does it contain? What requires attention?" (SIE Milestone
 * UI-02 Part 3). Entirely backed by the real, read-only
 * `GET /risk-assessments/{id}/report` endpoint (SIE Milestone 28) — no
 * frontend-computed risk score, no reinterpretation of the backend's own
 * rating. If the backend has nothing to report yet, that is shown
 * honestly rather than papered over.
 */
export function RiskAssessmentOverviewTab({ organizationId, assessmentId }: RiskAssessmentOverviewTabProps) {
  const [state, setState] = useState<AsyncState<RiskAssessmentReport>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    getRiskAssessmentReport(organizationId, assessmentId, controller.signal)
      .then((report) => setState({ status: 'success', data: report }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load the assessment report.' });
      });
    return () => controller.abort();
  }, [organizationId, assessmentId, reloadToken]);

  if (state.status === 'loading') return <LoadingState label="Loading assessment report…" />;
  if (state.status === 'error') {
    return <ErrorState description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />;
  }

  const report = state.data;

  return (
    <div className="flex flex-col gap-6">
      <Section title="Readiness">
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center gap-2">
            <StatusBadge tone={readinessStatusTone(report.readiness.status)} label={readinessStatusLabel(report.readiness.status)} />
          </div>
          {report.readiness.reasons.length > 0 ? (
            <ul className="list-inside list-disc text-sm text-text-secondary">
              {report.readiness.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-text-secondary">No outstanding readiness concerns were reported.</p>
          )}
        </div>
      </Section>

      <Section title="Findings summary">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Findings" value={report.assessment_summary.finding_count} />
          <StatTile label="Unrated" value={report.assessment_summary.unrated_finding_count} />
          <StatTile label="Linked actions" value={report.assessment_summary.linked_action_count} />
          <StatTile label="Open findings" value={report.assessment_summary.findings_by_status.OPEN ?? 0} />
        </div>
      </Section>

      <Section title="Risk distribution" description="Persisted finding-level risk ratings, inherent vs. residual.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <RiskBandTable title="Inherent risk" bands={report.risk_distribution.inherent} />
          <RiskBandTable title="Residual risk" bands={report.risk_distribution.residual} />
        </div>
      </Section>

      <Section title="Control effectiveness">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Total controls" value={report.control_effectiveness.total_controls} />
          <StatTile label="Findings with no controls" value={report.control_effectiveness.findings_with_no_controls} />
          <StatTile
            label="Not yet assessed"
            value={report.control_effectiveness.findings_with_controls_but_no_effectiveness_assessment}
          />
          <StatTile
            label="Ineffective/partial"
            value={report.control_effectiveness.findings_with_ineffective_or_partially_effective_controls}
          />
        </div>
      </Section>

      <Section title="Evidence coverage">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Total findings" value={report.evidence_coverage.total_findings} />
          <StatTile label="With no evidence" value={report.evidence_coverage.findings_with_no_evidence} />
          <StatTile label="With multiple evidence types" value={report.evidence_coverage.findings_with_multiple_evidence_types} />
          <StatTile label="With intelligence evidence" value={report.evidence_coverage.findings_with_intelligence_evidence} />
        </div>
      </Section>

      <Section title="Action response">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Total response actions" value={report.action_response_summary.total_response_actions} />
          <StatTile label="Outstanding" value={report.action_response_summary.outstanding_response_actions} />
          <StatTile label="Overdue" value={report.action_response_summary.overdue_response_actions} />
          <StatTile label="Completed" value={report.action_response_summary.completed_response_actions} />
        </div>
      </Section>
    </div>
  );
}

function RiskBandTable({ title, bands }: { title: string; bands: RiskAssessmentReport['risk_distribution']['inherent'] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="mb-2 text-sm font-semibold text-text-primary">{title}</p>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div className="flex justify-between">
          <dt className="text-text-secondary">Critical</dt>
          <dd className="font-medium text-critical">{bands.critical}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-text-secondary">High</dt>
          <dd className="font-medium text-warning">{bands.high}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-text-secondary">Moderate</dt>
          <dd className="font-medium text-informational">{bands.moderate}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-text-secondary">Low</dt>
          <dd className="font-medium text-success">{bands.low}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-text-secondary">Unrated</dt>
          <dd className="font-medium text-text-muted">{bands.unrated}</dd>
        </div>
      </dl>
    </div>
  );
}
