import type { AttentionItem } from '../../services/api/attention';
import { EmptyState } from '../../components/ui/EmptyState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { attentionCategoryLabel, attentionPriorityTone } from './intelligenceLabels';

export interface AttentionListProps {
  items: AttentionItem[];
  emptyTitle?: string;
  emptyDescription?: string;
}

/**
 * The ranked "what should I look at first?" list — SIE Milestone 33's
 * `GET /intelligence/attention` result, rendered in the exact order the
 * backend returned it (priority band, then category, then title) and
 * never re-sorted here.
 *
 * Read-only by design: recording a decision against one of these items
 * (`POST /intelligence/decisions`) is a separate capability that is not
 * yet available on this deployment (its implementation was extracted to
 * the private Commercial Core repository and has no Commercial Core
 * client wired for it yet — see `backend/app/api/v1/intelligence_
 * decisions.py`). This component deliberately offers no "Review"/
 * "Record decision" action rather than offering one that could not
 * succeed.
 */
export function AttentionList({ items, emptyTitle, emptyDescription }: AttentionListProps) {
  if (items.length === 0) {
    return (
      <EmptyState
        title={emptyTitle ?? 'Nothing needs attention right now'}
        description={emptyDescription ?? 'No signal in the current window met the threshold for attention.'}
      />
    );
  }

  return (
    <ol className="flex flex-col gap-2">
      {items.map((item, index) => (
        <li key={item.reference} className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-muted text-xs font-semibold text-text-secondary">
              {index + 1}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-text-primary">{item.title}</p>
                <StatusBadge tone={attentionPriorityTone(item.priority)} label={item.priority} />
              </div>
              <p className="mt-0.5 text-xs font-medium uppercase tracking-wide text-text-muted">
                {attentionCategoryLabel(item.category)}
                {item.site_label ? ` · ${item.site_label}` : ''}
              </p>
              <p className="mt-1.5 text-sm text-text-secondary">{item.explanation}</p>
              {item.limitation && <p className="mt-1 text-xs text-text-muted">{item.limitation}</p>}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
