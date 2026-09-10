import type { StatusTone } from '../../types/common';
import { formatCanonicalLabel } from '../events/eventStatus';

/**
 * Plain-HSE-language presentation for the deterministic intelligence
 * vocabulary the backend already returns (`app/intelligence/enums.py`).
 * UI-01's own "Intelligence presentation rules": prefer "Above baseline"/
 * "Recurring pattern"/"Moderate positive association"/"Insufficient
 * data" over "AI detected"/"AI prediction" language — SIE is intelligent
 * without repeatedly announcing that AI is involved. Every mapping here
 * is a pure formatting transform of a real backend value; an unmapped
 * value falls back to `formatCanonicalLabel()` (never hidden, never
 * coerced into a mapped one — mirrors `eventStatus.ts`'s own precedent).
 */

// --- Risk classification (RiskClassification) -------------------------------------------------

const RISK_CLASSIFICATION_TONE: Record<string, StatusTone> = {
  LOW: 'success',
  MODERATE: 'informational',
  HIGH: 'warning',
  CRITICAL: 'critical',
};

export function riskClassificationTone(classification: string | null): StatusTone {
  if (!classification) return 'neutral';
  return RISK_CLASSIFICATION_TONE[classification] ?? 'neutral';
}

export function riskClassificationLabel(classification: string | null): string {
  return classification ? formatCanonicalLabel(classification) : 'Not available';
}

// --- Data sufficiency (DataSufficiency) --------------------------------------------------------

const DATA_SUFFICIENCY_LABEL: Record<string, string> = {
  SUFFICIENT_DATA: 'Sufficient data',
  LIMITED_DATA: 'Limited data',
  INSUFFICIENT_DATA: 'Insufficient data',
};

const DATA_SUFFICIENCY_TONE: Record<string, StatusTone> = {
  SUFFICIENT_DATA: 'success',
  LIMITED_DATA: 'informational',
  INSUFFICIENT_DATA: 'warning',
};

export function dataSufficiencyLabel(status: string): string {
  return DATA_SUFFICIENCY_LABEL[status] ?? formatCanonicalLabel(status);
}

export function dataSufficiencyTone(status: string): StatusTone {
  return DATA_SUFFICIENCY_TONE[status] ?? 'neutral';
}

// --- Trend classification (EnterpriseTrendClassification) -------------------------------------

const TREND_LABEL: Record<string, string> = {
  IMPROVING: 'Improving',
  STABLE: 'Stable',
  DETERIORATING: 'Deteriorating',
  INSUFFICIENT_DATA: 'Insufficient data',
};

const TREND_TONE: Record<string, StatusTone> = {
  IMPROVING: 'success',
  STABLE: 'neutral',
  DETERIORATING: 'warning',
  INSUFFICIENT_DATA: 'informational',
};

export function trendLabel(classification: string): string {
  return TREND_LABEL[classification] ?? formatCanonicalLabel(classification);
}

export function trendTone(classification: string): StatusTone {
  return TREND_TONE[classification] ?? 'neutral';
}

// --- Anomaly status/direction (AnomalyStatus/AnomalyDirection) --------------------------------
// "An anomaly means deviation from baseline, not automatically risk" —
// ANOMALOUS never renders as 'critical'; it is a calm, informational
// signal, not an alarm.

const ANOMALY_STATUS_LABEL: Record<string, string> = {
  NORMAL: 'Normal',
  ANOMALOUS: 'Deviates from baseline',
  INSUFFICIENT_DATA: 'Insufficient data',
};

const ANOMALY_STATUS_TONE: Record<string, StatusTone> = {
  NORMAL: 'success',
  ANOMALOUS: 'warning',
  INSUFFICIENT_DATA: 'neutral',
};

export function anomalyStatusLabel(status: string): string {
  return ANOMALY_STATUS_LABEL[status] ?? formatCanonicalLabel(status);
}

export function anomalyStatusTone(status: string): StatusTone {
  return ANOMALY_STATUS_TONE[status] ?? 'neutral';
}

const ANOMALY_DIRECTION_LABEL: Record<string, string> = {
  ABOVE_BASELINE: 'Above baseline',
  BELOW_BASELINE: 'Below baseline',
  NONE: 'At baseline',
};

export function anomalyDirectionLabel(direction: string): string {
  return ANOMALY_DIRECTION_LABEL[direction] ?? formatCanonicalLabel(direction);
}

// --- Recurrence classification (RecurrenceClassification) -------------------------------------

const RECURRENCE_LABEL: Record<string, string> = {
  NONE: 'No recurrence observed',
  WATCH: 'Emerging pattern — watch',
  RECURRING: 'Recurring pattern',
  HIGH_RECURRENCE: 'High recurrence',
};

const RECURRENCE_TONE: Record<string, StatusTone> = {
  NONE: 'neutral',
  WATCH: 'informational',
  RECURRING: 'warning',
  HIGH_RECURRENCE: 'warning',
};

export function recurrenceLabel(classification: string): string {
  return RECURRENCE_LABEL[classification] ?? formatCanonicalLabel(classification);
}

export function recurrenceTone(classification: string): StatusTone {
  return RECURRENCE_TONE[classification] ?? 'neutral';
}

// --- Association classification (AssociationClassification) -----------------------------------
// Deliberately never phrased as causation — "association", never "causes".

const ASSOCIATION_LABEL: Record<string, string> = {
  STRONG_POSITIVE: 'Strong positive association',
  MODERATE_POSITIVE: 'Moderate positive association',
  WEAK: 'Weak or no association',
  MODERATE_NEGATIVE: 'Moderate negative association',
  STRONG_NEGATIVE: 'Strong negative association',
  INSUFFICIENT_DATA: 'Insufficient data',
};

export function associationLabel(classification: string): string {
  return ASSOCIATION_LABEL[classification] ?? formatCanonicalLabel(classification);
}

// --- Concentration classification (ConcentrationClassification) -------------------------------

const CONCENTRATION_LABEL: Record<string, string> = {
  LOW: 'Low concentration',
  MODERATE: 'Moderate concentration',
  HIGH: 'High concentration',
};

export function concentrationLabel(classification: string): string {
  return CONCENTRATION_LABEL[classification] ?? formatCanonicalLabel(classification);
}

// --- Attention priority (SIE Milestone 33 AttentionPriority) -----------------------------------
// Mirrors `PriorityBadge`'s own low/medium/high/critical tone mapping —
// kept separate since the backend's own vocabulary is
// LOW/MODERATE/HIGH/CRITICAL, not low/medium/high/critical.

const ATTENTION_PRIORITY_LABEL: Record<string, string> = {
  LOW: 'Low',
  MODERATE: 'Moderate',
  HIGH: 'High',
  CRITICAL: 'Critical',
};

const ATTENTION_PRIORITY_TONE: Record<string, StatusTone> = {
  LOW: 'neutral',
  MODERATE: 'informational',
  HIGH: 'warning',
  CRITICAL: 'critical',
};

export function attentionPriorityLabel(priority: string): string {
  return ATTENTION_PRIORITY_LABEL[priority] ?? formatCanonicalLabel(priority);
}

export function attentionPriorityTone(priority: string): StatusTone {
  return ATTENTION_PRIORITY_TONE[priority] ?? 'neutral';
}

// --- Attention category (SIE Milestone 33 AttentionCategory) -----------------------------------
// Plain-language category names — never "AI flagged", always naming the
// specific deterministic mechanism behind the item.

const ATTENTION_CATEGORY_LABEL: Record<string, string> = {
  DETERIORATING_TREND: 'Deteriorating trend',
  SIGNIFICANT_ANOMALY: 'Deviation from baseline',
  RECURRING_PATTERN: 'Recurring pattern',
  ELEVATED_RISK: 'Elevated risk score',
  PREDICTIVE_RISK: 'Model-derived risk signal',
  UNRESOLVED_FINDING: 'Unresolved finding',
  OVERDUE_ACTIONS: 'Overdue actions',
  EVIDENCE_GAP: 'Evidence gap',
};

export function attentionCategoryLabel(category: string): string {
  return ATTENTION_CATEGORY_LABEL[category] ?? formatCanonicalLabel(category);
}

// --- Human decision (SIE Milestone 34 IntelligenceDecisionType) --------------------------------
// The real, closed backend vocabulary — ACT / DO_NOT_ACT / DEFER /
// ALREADY_ADDRESSED / NOT_RELEVANT (`app/models/intelligence_decision_enums.py`).
// Never the illustrative ACT/MONITOR/DISMISS naming used in some
// milestone descriptions elsewhere.

const DECISION_LABEL: Record<string, string> = {
  ACT: 'Act',
  DO_NOT_ACT: 'Reviewed — no action',
  DEFER: 'Deferred — revisit later',
  ALREADY_ADDRESSED: 'Already addressed',
  NOT_RELEVANT: 'Not relevant',
};

const DECISION_TONE: Record<string, StatusTone> = {
  ACT: 'warning',
  DO_NOT_ACT: 'success',
  DEFER: 'informational',
  ALREADY_ADDRESSED: 'neutral',
  NOT_RELEVANT: 'neutral',
};

const DECISION_DESCRIPTION: Record<string, string> = {
  ACT: 'Raise or link an intervention in response to this signal.',
  DO_NOT_ACT: 'Reviewed the signal and chosen not to act on it (e.g. an existing control is already effective).',
  DEFER: 'Acknowledged for now — revisit this signal later.',
  ALREADY_ADDRESSED: 'The underlying condition is already being handled elsewhere.',
  NOT_RELEVANT: 'This signal does not warrant attention (e.g. a false positive, or context SIE could not see).',
};

export function decisionLabel(decision: string): string {
  return DECISION_LABEL[decision] ?? formatCanonicalLabel(decision);
}

export function decisionTone(decision: string): StatusTone {
  return DECISION_TONE[decision] ?? 'neutral';
}

export function decisionDescription(decision: string): string {
  return DECISION_DESCRIPTION[decision] ?? '';
}

export const DECISION_OPTIONS: { value: string; label: string }[] = [
  { value: 'ACT', label: DECISION_LABEL.ACT },
  { value: 'DO_NOT_ACT', label: DECISION_LABEL.DO_NOT_ACT },
  { value: 'DEFER', label: DECISION_LABEL.DEFER },
  { value: 'ALREADY_ADDRESSED', label: DECISION_LABEL.ALREADY_ADDRESSED },
  { value: 'NOT_RELEVANT', label: DECISION_LABEL.NOT_RELEVANT },
];

// --- Organizational memory (SIE Milestone 40/41 OrganizationalMemoryType/ApplicabilityBasis) ----

const MEMORY_TYPE_LABEL: Record<string, string> = {
  LESSON_LEARNED: 'Lesson learned',
  EFFECTIVE_PRACTICE: 'Effective practice',
  FAILED_APPROACH: 'Approach that did not work',
  EARLY_WARNING_PATTERN: 'Early warning pattern',
  CONTROL_INSIGHT: 'Control insight',
};

export function memoryTypeLabel(memoryType: string): string {
  return MEMORY_TYPE_LABEL[memoryType] ?? formatCanonicalLabel(memoryType);
}

const MEMORY_APPLICABILITY_LABEL: Record<string, string> = {
  ORGANIZATION_WIDE: 'Applies across the organization',
  SITE_MATCH: 'Applies to this site',
  PROJECT_SITE_MATCH: "Applies to a site associated with this project",
  ORGANIZATION_SCOPE_ROLLUP: 'Applies to a site within the organization',
};

export function memoryApplicabilityLabel(basis: string): string {
  return MEMORY_APPLICABILITY_LABEL[basis] ?? formatCanonicalLabel(basis);
}

export function memoryGovernanceTone(status: string): StatusTone {
  return status === 'ACTIVE' ? 'success' : 'neutral';
}
