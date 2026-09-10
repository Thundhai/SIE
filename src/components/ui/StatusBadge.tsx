import { AlertOctagon, AlertTriangle, CheckCircle2, Circle, Info } from 'lucide-react';
import type { StatusTone } from '../../types/common';
import { cn } from '../../lib/cn';

const TONE_STYLES: Record<StatusTone, { surface: string; text: string; Icon: typeof Circle }> = {
  success: { surface: 'bg-success-surface', text: 'text-success', Icon: CheckCircle2 },
  warning: { surface: 'bg-warning-surface', text: 'text-warning', Icon: AlertTriangle },
  critical: { surface: 'bg-critical-surface', text: 'text-critical', Icon: AlertOctagon },
  informational: { surface: 'bg-informational-surface', text: 'text-informational', Icon: Info },
  neutral: { surface: 'bg-neutral-status-surface', text: 'text-neutral-status', Icon: Circle },
};

export interface StatusBadgeProps {
  label: string;
  tone: StatusTone;
  className?: string;
}

/**
 * Restrained status indicator. Status is never communicated by color
 * alone (§18 accessibility) — every badge always pairs its color with
 * both an icon AND a text label, so the status reads correctly for a
 * colorblind user or when printed in grayscale. No glow, no pulse, no
 * saturated neon — see src/styles/tokens.css's own status colors.
 */
export function StatusBadge({ label, tone, className }: StatusBadgeProps) {
  const { surface, text, Icon } = TONE_STYLES[tone];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
        surface,
        text,
        className,
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {label}
    </span>
  );
}
