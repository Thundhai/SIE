import { EmptyState } from '../../components/ui/EmptyState';
import { EvidenceList } from '../../components/data/EvidenceList';
import type { RiskAssessmentFinding } from '../../services/api/riskAssessments';
import { toEvidenceRecords } from './riskEvidenceDisplay';

export interface RiskAssessmentEvidenceTabProps {
  findings: RiskAssessmentFinding[];
}

/**
 * Evidence — a cross-finding view of every supporting evidence record in
 * this assessment (SIE Milestone UI-02 Part 7), grouped by finding.
 * Assembled from the already-loaded findings (`RiskAssessmentFindingRead.evidence`)
 * — no separate fetch. Uses the shared `EvidenceList`/`EvidenceItem`
 * components; never a raw database id as a primary label.
 */
export function RiskAssessmentEvidenceTab({ findings }: RiskAssessmentEvidenceTabProps) {
  const findingsWithEvidence = findings.filter((finding) => finding.evidence.length > 0);

  if (findingsWithEvidence.length === 0) {
    return <EmptyState title="No evidence recorded" description="No supporting evidence has been recorded across this assessment's findings." />;
  }

  return (
    <div className="flex flex-col gap-4">
      {findingsWithEvidence.map((finding) => (
        <div key={finding.id} className="rounded-lg border border-border bg-surface p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">{finding.title}</p>
          <EvidenceList evidence={toEvidenceRecords(finding.evidence)} label="Evidence" />
        </div>
      ))}
    </div>
  );
}
