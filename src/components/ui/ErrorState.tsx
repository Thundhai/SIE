import { AlertTriangle } from 'lucide-react';
import { Button } from './Button';

export interface ErrorStateProps {
  title?: string;
  description: string;
  onRetry?: () => void;
}

/** A per-request error panel — distinct from `AppErrorBoundary`, which
 * only catches unexpected render-time exceptions. This is for an
 * ordinary, expected failure (the API returned an error, or the network
 * request never reached the server) and always says so honestly rather
 * than silently showing stale/empty content. `role="alert"` announces it
 * immediately to assistive tech. */
export function ErrorState({ title = 'Something went wrong', description, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-2 rounded-lg border border-critical/30 bg-critical-surface py-10 text-center">
      <AlertTriangle className="h-5 w-5 text-critical" aria-hidden="true" />
      <p className="text-sm font-medium text-text-primary">{title}</p>
      <p className="max-w-sm text-sm text-text-secondary">{description}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-1">
          Try again
        </Button>
      )}
    </div>
  );
}
