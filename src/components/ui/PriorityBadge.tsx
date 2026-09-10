import type { StatusTone } from '../../types/common';
import { StatusBadge } from './StatusBadge';

export type PriorityLevel = 'low' | 'medium' | 'high' | 'critical';

const PRIORITY_TONE: Record<PriorityLevel, StatusTone> = {
  low: 'neutral',
  medium: 'informational',
  high: 'warning',
  critical: 'critical',
};

const PRIORITY_LABEL: Record<PriorityLevel, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
};

export interface PriorityBadgeProps {
  priority: PriorityLevel;
  className?: string;
}

/** A `StatusBadge` specialized for priority/severity — kept as a
 * separate component (rather than callers reaching for `StatusBadge`
 * with a manually-chosen tone) so every priority level maps to exactly
 * one tone/label pair everywhere it appears. */
export function PriorityBadge({ priority, className }: PriorityBadgeProps) {
  return <StatusBadge tone={PRIORITY_TONE[priority]} label={PRIORITY_LABEL[priority]} className={className} />;
}
