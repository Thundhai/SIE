import type { EvidenceRecord } from '../../types/evidence';
import type { RiskEvidence } from '../../services/api/riskAssessments';
import { evidenceTypeLabel, formatEvidenceReferenceLabel } from './riskAssessmentLabels';

/**
 * Maps a `RiskEvidenceRead` row onto the shared `EvidenceRecord` shape
 * `EvidenceItem`/`EvidenceList` already render (SIE Milestone UI-02 Part
 * 7). `RiskEvidenceRead` never carries a resolved title for
 * `EVENT`/`ACTION`/`KNOWLEDGE_DOCUMENT` evidence — only a `reference_id`
 * — so no human title is invented here: `EVENT`/`ACTION` evidence links
 * to its real source record (a route that exists), `KNOWLEDGE_DOCUMENT`
 * evidence is shown without a link (none exists in this frontend) and,
 * per the "raw UUID" rule, its id is never displayed. Computed
 * intelligence evidence (`ANOMALY`/`PATTERN`/`ASSOCIATION`/`OTHER`)
 * always carries a real `reference_label` instead, humanized rather than
 * shown as its raw machine key.
 */
export function toEvidenceRecord(evidence: RiskEvidence, index: number): EvidenceRecord {
  const reference = `E${index + 1}`;
  const typeLabel = evidenceTypeLabel(evidence.evidence_type);

  if (evidence.reference_label) {
    return { reference, title: formatEvidenceReferenceLabel(evidence.reference_label), context: typeLabel };
  }
  if (evidence.evidence_type === 'EVENT' && evidence.reference_id) {
    return { reference, title: `${typeLabel} evidence`, context: 'View source event', href: `/events/${evidence.reference_id}` };
  }
  if (evidence.evidence_type === 'ACTION' && evidence.reference_id) {
    return { reference, title: `${typeLabel} evidence`, context: 'View source action', href: `/actions/${evidence.reference_id}` };
  }
  return { reference, title: `${typeLabel} evidence` };
}

export function toEvidenceRecords(evidence: RiskEvidence[]): EvidenceRecord[] {
  return evidence.map((item, index) => toEvidenceRecord(item, index));
}
