import type { StatusTone } from '../../types/common';

/**
 * Reports-only presentation helpers — everything shared with Intelligence
 * (risk/trend/anomaly/pattern/association/concentration/data-sufficiency)
 * comes from `../intelligence/intelligenceLabels.ts` instead of being
 * redefined here. This file covers only the two things unique to the
 * Reports page's own data: risk-signal severity (mirrors
 * `../home/HomePage.tsx`'s own identical mapping — kept as its own copy
 * per this codebase's established per-feature-file precedent, e.g.
 * `administrationLabels.ts`/`knowledgeLabels.ts`) and a plain-language
 * signal description.
 */

const SIGNAL_SEVERITY_LABEL: Record<string, string> = { LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High' };
const SIGNAL_SEVERITY_TONE: Record<string, StatusTone> = { LOW: 'neutral', MEDIUM: 'warning', HIGH: 'critical' };

export function signalSeverityLabel(severity: string): string {
  return SIGNAL_SEVERITY_LABEL[severity] ?? severity;
}

export function signalSeverityTone(severity: string): StatusTone {
  return SIGNAL_SEVERITY_TONE[severity] ?? 'neutral';
}

/** A restrained, human-readable rendering of `RiskSignal.signal_type` —
 * never an invented narrative beyond what the backend's own value names
 * (`app/intelligence/enums.py::RiskSignalType`). Falls back to the raw
 * value for any type not covered, so nothing is ever hidden. */
export function signalDescription(signalType: string): string {
  const known: Record<string, string> = {
    OVERDUE_ACTION_SURGE: 'A surge in overdue corrective actions was detected.',
    HIGH_POTENTIAL_EVENT_CLUSTER: 'A cluster of high-potential-severity events was detected.',
    TRAINING_COMPLIANCE_DROP: 'A drop in training completion compliance was detected.',
    EQUIPMENT_FAILURE_CLUSTER: 'A cluster of equipment failures was detected.',
    UNSAFE_OBSERVATION_SURGE: 'A surge in unsafe observations was detected.',
  };
  return known[signalType] ?? signalType.replaceAll('_', ' ').toLowerCase();
}
