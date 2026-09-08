import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { listFindingActions, type RiskAssessmentFinding, type RiskAssessmentLinkedAction } from '../../services/api/riskAssessments';
import type { ActionStatus } from '../../types/actions';
import type { AsyncState } from '../../types/common';
import { actionStatusLabel, actionStatusTone } from '../actions/actionStatus';

export interface RiskAssessmentActionsTabProps {
  organizationId: string;
  assessmentId: string;
  findings: RiskAssessmentFinding[];
}

interface Row {
  finding: RiskAssessmentFinding;
  linkedAction: RiskAssessmentLinkedAction;
}

/**
 * Actions — every action currently linked to this assessment's findings
 * (SIE Milestone UI-02 Part 8), gathered across
 * `GET .../findings/{finding_id}/actions` for each finding (no
 * assessment-level "list all linked actions" endpoint exists on the
 * backend). Fetched once when this tab is opened, not on every render.
 */
export function RiskAssessmentActionsTab({ organizationId, assessmentId, findings }: RiskAssessmentActionsTabProps) {
  const navigate = useNavigate();
  const [state, setState] = useState<AsyncState<Row[]>>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (findings.length === 0) {
      setState({ status: 'success', data: [] });
      return;
    }
    const controller = new AbortController();
    setState({ status: 'loading' });
    Promise.all(
      findings.map((finding) =>
        listFindingActions(organizationId, assessmentId, finding.id, controller.signal).then((result) =>
          result.items.map((linkedAction) => ({ finding, linkedAction })),
        ),
      ),
    )
      .then((rowsByFinding) => setState({ status: 'success', data: rowsByFinding.flat() }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load linked actions.' });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId, assessmentId, findings, reloadToken]);

  if (state.status === 'loading') return <LoadingState label="Loading linked actions…" />;
  if (state.status === 'error') {
    return <ErrorState description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />;
  }
  if (state.data.length === 0) {
    return <EmptyState title="No actions linked to this assessment" description="Actions raised from a finding will appear here." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {state.data.map(({ finding, linkedAction }) => (
        <li key={linkedAction.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3.5">
          <div>
            <button
              type="button"
              onClick={() => navigate(`/actions/${linkedAction.action_id}`)}
              className="text-left text-sm font-medium text-text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
            >
              {linkedAction.action_title}
            </button>
            <p className="mt-0.5 text-xs text-text-muted">From finding: {finding.title}</p>
          </div>
          <StatusBadge tone={actionStatusTone(linkedAction.action_status as ActionStatus)} label={actionStatusLabel(linkedAction.action_status as ActionStatus)} />
        </li>
      ))}
    </ul>
  );
}
