import { useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { EvidenceList } from '../../components/data/EvidenceList';
import { Section } from '../../components/layout/Section';
import { StatusBadge } from '../../components/ui/StatusBadge';
import type { RiskAssessmentFinding, RiskControl } from '../../services/api/riskAssessments';
import { ControlEffectivenessDialog } from './ControlEffectivenessDialog';
import { FindingActionsPanel } from './FindingActionsPanel';
import { FindingCloseDialog } from './FindingCloseDialog';
import {
  controlEffectivenessLabel,
  controlEffectivenessTone,
  controlStatusLabel,
  controlTypeLabel,
  findingRiskClassificationLabel,
  findingRiskClassificationTone,
  findingStatusLabel,
  findingStatusTone,
} from './riskAssessmentLabels';
import { toEvidenceRecords } from './riskEvidenceDisplay';

export interface RiskAssessmentFindingsTabProps {
  organizationId: string;
  assessmentId: string;
  findings: RiskAssessmentFinding[];
  isEditable: boolean;
  onFindingChanged: (finding: RiskAssessmentFinding) => void;
}

function riskCell(score: number | null, classification: string | null): { label: string; tone: ReturnType<typeof findingRiskClassificationTone> } {
  if (score === null || classification === null) {
    return { label: 'Not recorded', tone: 'neutral' };
  }
  return { label: `${classification} (${score})`, tone: findingRiskClassificationTone(classification) };
}

/**
 * Findings — the assessment's core "what did we find, and how risky is
 * it" workspace (SIE Milestone UI-02 Part 4). Each finding expands
 * in-place to its controls (Part 5-6), evidence (Part 7), and linked
 * actions (Part 8-9), plus the governed closure interaction (Part 11) —
 * every value shown is a real, persisted backend value; an unavailable
 * field reads "Not recorded" rather than being invented.
 */
export function RiskAssessmentFindingsTab({ organizationId, assessmentId, findings, isEditable, onFindingChanged }: RiskAssessmentFindingsTabProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (findings.length === 0) {
    return <EmptyState title="No findings recorded" description="This assessment has no findings yet." />;
  }

  return (
    <ul className="flex flex-col gap-3">
      {findings.map((finding) => {
        const inherent = riskCell(finding.inherent_risk_score, finding.inherent_risk_classification);
        const residual = riskCell(finding.residual_risk_score, finding.residual_risk_classification);
        const isExpanded = expandedId === finding.id;

        return (
          <li key={finding.id} className="rounded-lg border border-border bg-surface">
            <button
              type="button"
              onClick={() => setExpandedId(isExpanded ? null : finding.id)}
              className="flex w-full flex-col gap-2 p-4 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
              aria-expanded={isExpanded}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{finding.risk_area.label}</p>
                  <p className="mt-0.5 text-sm font-medium text-text-primary">{finding.title}</p>
                </div>
                <StatusBadge tone={findingStatusTone(finding.status)} label={findingStatusLabel(finding.status)} />
              </div>
              <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <div>
                  <dt className="text-text-muted">Likelihood / Consequence</dt>
                  <dd className="mt-0.5 text-text-primary">
                    {finding.likelihood ?? 'Not recorded'} / {finding.consequence ?? 'Not recorded'}
                  </dd>
                </div>
                <div>
                  <dt className="text-text-muted">Inherent risk</dt>
                  <dd className="mt-0.5">
                    <StatusBadge tone={inherent.tone} label={inherent.label} />
                  </dd>
                </div>
                <div>
                  <dt className="text-text-muted">Residual risk</dt>
                  <dd className="mt-0.5">
                    <StatusBadge tone={residual.tone} label={residual.label} />
                  </dd>
                </div>
                <div>
                  <dt className="text-text-muted">Controls / Evidence</dt>
                  <dd className="mt-0.5 text-text-primary">
                    {finding.controls.length} / {finding.evidence.length}
                  </dd>
                </div>
              </dl>
            </button>

            {isExpanded && (
              <div className="border-t border-border p-4">
                <FindingExpandedDetail
                  organizationId={organizationId}
                  assessmentId={assessmentId}
                  finding={finding}
                  isEditable={isEditable}
                  onFindingChanged={onFindingChanged}
                />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function FindingExpandedDetail({
  organizationId,
  assessmentId,
  finding,
  isEditable,
  onFindingChanged,
}: {
  organizationId: string;
  assessmentId: string;
  finding: RiskAssessmentFinding;
  isEditable: boolean;
  onFindingChanged: (finding: RiskAssessmentFinding) => void;
}) {
  const { hasPermission } = useAuth();
  const [assessingControl, setAssessingControl] = useState<RiskControl | null>(null);
  const [closing, setClosing] = useState(false);
  const canClose = isEditable && finding.status !== 'CLOSED' && finding.likelihood !== null && hasPermission('risk_assessment:approve');

  function handleControlAssessed(updatedControl: RiskControl) {
    onFindingChanged({
      ...finding,
      controls: finding.controls.map((control) => (control.id === updatedControl.id ? updatedControl : control)),
    });
  }

  return (
    <div className="flex flex-col gap-5">
      {finding.description && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Description</p>
          <p className="mt-1 text-sm text-text-primary">{finding.description}</p>
        </div>
      )}
      {finding.system_analysis_summary && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">System analysis</p>
          <p className="mt-1 text-sm text-text-primary">{finding.system_analysis_summary}</p>
        </div>
      )}
      {finding.assessor_notes && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Assessor notes</p>
          <p className="mt-1 text-sm text-text-primary">{finding.assessor_notes}</p>
        </div>
      )}

      <Section title="Controls">
        {finding.controls.length === 0 ? (
          <EmptyState title="No controls recorded" description="No controls have been recorded for this finding." />
        ) : (
          <ul className="flex flex-col gap-2">
            {finding.controls.map((control) => (
              <li key={control.id} className="flex flex-col gap-2 rounded-md border border-border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm text-text-primary">{control.description}</p>
                    <p className="mt-0.5 text-xs text-text-muted">
                      {controlTypeLabel(control.control_type)} · {controlStatusLabel(control.status)}
                    </p>
                  </div>
                  <StatusBadge tone={controlEffectivenessTone(control.effectiveness)} label={controlEffectivenessLabel(control.effectiveness)} />
                </div>
                {control.effectiveness_rationale && (
                  <p className="text-xs text-text-secondary">{control.effectiveness_rationale}</p>
                )}
                {control.assessed_at && (
                  <p className="text-xs text-text-muted">
                    Assessed {new Date(control.assessed_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                  </p>
                )}
                {isEditable && hasPermission('risk_assessment:write') && (
                  <div>
                    <Button variant="secondary" size="sm" onClick={() => setAssessingControl(control)}>
                      Assess effectiveness
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Evidence">
        {finding.evidence.length === 0 ? (
          <EmptyState title="No evidence recorded" description="No supporting evidence has been recorded for this finding." />
        ) : (
          <EvidenceList evidence={toEvidenceRecords(finding.evidence)} label="Evidence" />
        )}
      </Section>

      <Section title="Actions">
        <FindingActionsPanel
          organizationId={organizationId}
          assessmentId={assessmentId}
          findingId={finding.id}
          isEditable={isEditable}
        />
      </Section>

      {finding.status === 'CLOSED' ? (
        <p className="text-sm text-text-secondary">This finding is closed.</p>
      ) : (
        canClose && (
          <div>
            <Button variant="danger" size="sm" onClick={() => setClosing(true)}>
              Close finding
            </Button>
          </div>
        )
      )}
      {!canClose && finding.status !== 'CLOSED' && finding.likelihood === null && (
        <p className="text-xs text-text-muted">This finding must be rated before it can be closed.</p>
      )}

      {assessingControl && (
        <ControlEffectivenessDialog
          isOpen={Boolean(assessingControl)}
          onClose={() => setAssessingControl(null)}
          organizationId={organizationId}
          assessmentId={assessmentId}
          findingId={finding.id}
          control={assessingControl}
          onAssessed={handleControlAssessed}
        />
      )}
      <FindingCloseDialog
        isOpen={closing}
        onClose={() => setClosing(false)}
        organizationId={organizationId}
        assessmentId={assessmentId}
        finding={finding}
        onClosed={(updated) => onFindingChanged(updated)}
      />
    </div>
  );
}
