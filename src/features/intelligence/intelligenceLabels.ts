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
