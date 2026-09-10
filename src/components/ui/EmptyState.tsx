import { Inbox } from 'lucide-react';
import { ReactNode } from 'react';

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}

/** A calm "nothing here yet" panel — used whenever a real, successful
 * query legitimately returned zero results (distinct from ErrorState,
 * which is for a failed request). */
export function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border py-12 text-center">
      <div className="text-text-muted">{icon ?? <Inbox className="h-6 w-6" aria-hidden="true" />}</div>
      <p className="text-sm font-medium text-text-primary">{title}</p>
      {description && <p className="max-w-sm text-sm text-text-secondary">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
