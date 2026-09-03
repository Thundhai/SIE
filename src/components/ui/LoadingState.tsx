import { Loader2 } from 'lucide-react';

export interface LoadingStateProps {
  label?: string;
}

/** A restrained loading indicator — a single small spinner and a
 * sentence, never a skeleton wall or an animated "AI thinking" affect.
 * `role="status"` + `aria-live="polite"` so assistive tech announces it
 * once, not on every re-render. */
export function LoadingState({ label = 'Loading…' }: LoadingStateProps) {
  return (
    <div role="status" aria-live="polite" className="flex items-center justify-center gap-2.5 py-12 text-sm text-text-secondary">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
