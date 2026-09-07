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
