import { useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import type { RiskAssessmentFinding, RiskControl } from '../../services/api/riskAssessments';
import { ControlEffectivenessDialog } from './ControlEffectivenessDialog';
import { controlEffectivenessLabel, controlEffectivenessTone, controlStatusLabel, controlTypeLabel } from './riskAssessmentLabels';

export interface RiskAssessmentControlsTabProps {
  organizationId: string;
  assessmentId: string;
  findings: RiskAssessmentFinding[];
  isEditable: boolean;
  onFindingChanged: (finding: RiskAssessmentFinding) => void;
}

/**
 * Controls — a cross-finding view of every control recorded in this
 * assessment (SIE Milestone UI-02 Part 5-6), assembled from the already-
 * loaded findings (`RiskAssessmentFindingRead.controls`) — no separate
 * "list all controls" endpoint exists, so this is a client-side
 * aggregation of real data, never a second, competing fetch. Every
 * effectiveness change still goes through the same dedicated
 * `assess-effectiveness` route as the Findings tab.
 */
export function RiskAssessmentControlsTab({ organizationId, assessmentId, findings, isEditable, onFindingChanged }: RiskAssessmentControlsTabProps) {
  const { hasPermission } = useAuth();
  const [assessing, setAssessing] = useState<{ finding: RiskAssessmentFinding; control: RiskControl } | null>(null);

  const rows = findings.flatMap((finding) => finding.controls.map((control) => ({ finding, control })));

  if (rows.length === 0) {
    return <EmptyState title="No controls recorded" description="No controls have been recorded across this assessment's findings." />;
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.map(({ finding, control }) => (
        <div key={control.id} className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{finding.title}</p>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-sm text-text-primary">{control.description}</p>
              <p className="mt-0.5 text-xs text-text-muted">
                {controlTypeLabel(control.control_type)} · {controlStatusLabel(control.status)}
              </p>
            </div>
            <StatusBadge tone={controlEffectivenessTone(control.effectiveness)} label={controlEffectivenessLabel(control.effectiveness)} />
          </div>
          {control.effectiveness_rationale && <p className="text-xs text-text-secondary">{control.effectiveness_rationale}</p>}
          {isEditable && hasPermission('risk_assessment:write') && (
            <div>
              <Button variant="secondary" size="sm" onClick={() => setAssessing({ finding, control })}>
                Assess effectiveness
              </Button>
            </div>
          )}
        </div>
      ))}

      {assessing && (
        <ControlEffectivenessDialog
          isOpen={Boolean(assessing)}
          onClose={() => setAssessing(null)}
          organizationId={organizationId}
          assessmentId={assessmentId}
          findingId={assessing.finding.id}
          control={assessing.control}
          onAssessed={(updatedControl) =>
            onFindingChanged({
              ...assessing.finding,
              controls: assessing.finding.controls.map((c) => (c.id === updatedControl.id ? updatedControl : c)),
            })
          }
        />
      )}
    </div>
  );
}
