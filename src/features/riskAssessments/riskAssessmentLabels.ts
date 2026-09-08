import type { StatusTone } from '../../types/common';
import { formatCanonicalLabel } from '../events/eventStatus';

/** Plain-language presentation for the governed
 * `RiskAssessmentStatus`/`AssessmentType`/`RiskAssessmentScope` vocabulary
 * (`backend/app/models/risk_assessment_enums.py`) — mirrors
 * `intelligenceLabels.ts`'s own "pure formatting transform, never coerce
 * an unmapped value" precedent. */

const STATUS_LABEL: Record<string, string> = {
  DRAFT: 'Draft',
  IN_REVIEW: 'In review',
  APPROVED: 'Approved',
  SUPERSEDED: 'Superseded',
  ARCHIVED: 'Archived',
};

const STATUS_TONE: Record<string, StatusTone> = {
  DRAFT: 'neutral',
  IN_REVIEW: 'informational',
  APPROVED: 'success',
  SUPERSEDED: 'neutral',
  ARCHIVED: 'neutral',
};

export function assessmentStatusLabel(status: string): string {
  return STATUS_LABEL[status] ?? formatCanonicalLabel(status);
}

export function assessmentStatusTone(status: string): StatusTone {
  return STATUS_TONE[status] ?? 'neutral';
}

const ASSESSMENT_TYPE_LABEL: Record<string, string> = {
  BASELINE: 'Baseline',
  PERIODIC: 'Periodic',
  INCIDENT_TRIGGERED: 'Incident-triggered',
  CHANGE_TRIGGERED: 'Change-triggered',
  TARGETED: 'Targeted',
};

export function assessmentTypeLabel(type: string): string {
  return ASSESSMENT_TYPE_LABEL[type] ?? formatCanonicalLabel(type);
}

const SCOPE_LABEL: Record<string, string> = {
  ORGANIZATION: 'Organization-wide',
  LOCATION: 'Location',
  SITE: 'Site',
};

export function assessmentScopeLabel(scope: string): string {
  return SCOPE_LABEL[scope] ?? formatCanonicalLabel(scope);
}

const RISK_CLASSIFICATION_TONE: Record<string, StatusTone> = {
  LOW: 'success',
  MODERATE: 'informational',
  HIGH: 'warning',
  CRITICAL: 'critical',
};

export function findingRiskClassificationTone(classification: string | null): StatusTone {
  if (!classification) return 'neutral';
  return RISK_CLASSIFICATION_TONE[classification] ?? 'neutral';
}

export function findingRiskClassificationLabel(classification: string | null): string {
  return classification ? formatCanonicalLabel(classification) : 'Not yet rated';
}

const FINDING_STATUS_LABEL: Record<string, string> = {
  OPEN: 'Open',
  ADDRESSED: 'Addressed',
  CLOSED: 'Closed',
};

const FINDING_STATUS_TONE: Record<string, StatusTone> = {
  OPEN: 'warning',
  ADDRESSED: 'informational',
  CLOSED: 'success',
};

export function findingStatusLabel(status: string): string {
  return FINDING_STATUS_LABEL[status] ?? formatCanonicalLabel(status);
}

export function findingStatusTone(status: string): StatusTone {
  return FINDING_STATUS_TONE[status] ?? 'neutral';
}

// --- Controls (SIE Milestone 29/29A) -----------------------------------------------------

const CONTROL_TYPE_LABEL: Record<string, string> = {
  ELIMINATION: 'Elimination',
  SUBSTITUTION: 'Substitution',
  ENGINEERING: 'Engineering',
  ADMINISTRATIVE: 'Administrative',
  PPE: 'PPE',
  OTHER: 'Other',
};

export function controlTypeLabel(type: string): string {
  return CONTROL_TYPE_LABEL[type] ?? formatCanonicalLabel(type);
}

const CONTROL_STATUS_LABEL: Record<string, string> = {
  PROPOSED: 'Proposed',
  IN_PLACE: 'In place',
  NOT_IMPLEMENTED: 'Not implemented',
  PARTIALLY_IMPLEMENTED: 'Partially implemented',
  NOT_VERIFIED: 'Not verified',
};

const CONTROL_STATUS_TONE: Record<string, StatusTone> = {
  PROPOSED: 'neutral',
  IN_PLACE: 'success',
  NOT_IMPLEMENTED: 'critical',
  PARTIALLY_IMPLEMENTED: 'warning',
  NOT_VERIFIED: 'informational',
};

export function controlStatusLabel(status: string): string {
  return CONTROL_STATUS_LABEL[status] ?? formatCanonicalLabel(status);
}

export function controlStatusTone(status: string): StatusTone {
  return CONTROL_STATUS_TONE[status] ?? 'neutral';
}

/** The backend's actual `ControlEffectiveness` values
 * (`backend/app/models/risk_assessment_enums.py`) — NOT_ASSESSED,
 * INEFFECTIVE, PARTIALLY_EFFECTIVE, EFFECTIVE. "No control information
 * was provided" (NOT_ASSESSED) is deliberately never conflated with "the
 * control is ineffective" (item 12's own distinction) — different tone,
 * different label. */
const CONTROL_EFFECTIVENESS_LABEL: Record<string, string> = {
  NOT_ASSESSED: 'Not yet assessed',
  INEFFECTIVE: 'Ineffective',
  PARTIALLY_EFFECTIVE: 'Partially effective',
  EFFECTIVE: 'Effective',
};

const CONTROL_EFFECTIVENESS_TONE: Record<string, StatusTone> = {
  NOT_ASSESSED: 'neutral',
  INEFFECTIVE: 'critical',
  PARTIALLY_EFFECTIVE: 'warning',
  EFFECTIVE: 'success',
};

export function controlEffectivenessLabel(effectiveness: string): string {
  return CONTROL_EFFECTIVENESS_LABEL[effectiveness] ?? formatCanonicalLabel(effectiveness);
}

export function controlEffectivenessTone(effectiveness: string): StatusTone {
  return CONTROL_EFFECTIVENESS_TONE[effectiveness] ?? 'neutral';
}

/** Assessable target values only — `NOT_ASSESSED` may never be submitted
 * as a conclusion (the backend's own validator rejects it — see
 * `RiskAssessmentControlEffectivenessAssess`'s own docstring). */
export const ASSESSABLE_CONTROL_EFFECTIVENESS_OPTIONS: { value: string; label: string }[] = [
  'EFFECTIVE',
  'PARTIALLY_EFFECTIVE',
  'INEFFECTIVE',
].map((value) => ({ value, label: controlEffectivenessLabel(value) }));

// --- Evidence (RiskEvidenceType) ----------------------------------------------------------

const EVIDENCE_TYPE_LABEL: Record<string, string> = {
  EVENT: 'Event',
  ANOMALY: 'Anomaly',
  PATTERN: 'Pattern',
  ASSOCIATION: 'Association',
  KNOWLEDGE_DOCUMENT: 'Knowledge document',
  ACTION: 'Action',
  OTHER: 'Other',
};

export function evidenceTypeLabel(type: string): string {
  return EVIDENCE_TYPE_LABEL[type] ?? formatCanonicalLabel(type);
}

/** `reference_label` for computed-intelligence evidence is a machine key
 * like `"anomaly:incident_count"` or `"association:incident_count:near_miss_count"`
 * (see `RiskEvidenceType`'s own docstring) — humanized here the same way
 * `formatCanonicalLabel` humanizes every other governed value elsewhere
 * in this codebase, never fabricated. */
export function formatEvidenceReferenceLabel(label: string): string {
  return label.split(':').map(formatCanonicalLabel).join(' · ');
}

// --- Assessment readiness (SIE Milestone 28) -----------------------------------------------

export function readinessStatusLabel(status: string): string {
  return status === 'READY' ? 'Ready' : status === 'NOT_READY' ? 'Not ready' : formatCanonicalLabel(status);
}

export function readinessStatusTone(status: string): StatusTone {
  if (status === 'READY') return 'success';
  if (status === 'NOT_READY') return 'warning';
  return 'neutral';
}
