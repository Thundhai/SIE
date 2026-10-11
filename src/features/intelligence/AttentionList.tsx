import type { AttentionItem } from '../../services/api/attention';
import type { IntelligenceDecision } from '../../services/api/decisions';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { attentionCategoryLabel, attentionPriorityTone, decisionLabel, decisionTone } from './intelligenceLabels';

export interface AttentionListProps {
  items: AttentionItem[];
  /** The most recent decision recorded for each item's own
   * `attention_reference`, when one exists — built once from a real
   * `GET /intelligence/decisions` response (never inferred or ranked
   * client-side; see `IntelligencePage`'s own `decisionsByReference`
   * construction). */
  decisionsByReference: Map<string, IntelligenceDecision>;
  onReview: (item: AttentionItem) => void;
  emptyTitle?: string;
  emptyDescription?: string;
}

/**
 * The ranked "what should I look at first?" list — SIE Milestone 33's
 * own `GET /intelligence/attention` result, rendered in the exact order
 * the backend returned it (`_sort_items()`: priority band, then
 * category, then title). This is the primary prioritization mechanism
 * (SIE Milestone 42 spec §5) — it replaces flat counts like "Open
 * Actions: 3" as the thing a decision-maker scans first.
 */
export function AttentionList({ items, decisionsByReference, onReview, emptyTitle, emptyDescription }: AttentionListProps) {
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
      {items.map((item, index) => {
        const lastDecision = decisionsByReference.get(item.reference);
        return (
          <li key={item.reference} className="rounded-lg border border-border bg-surface p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex min-w-0 flex-1 items-start gap-3">
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
                  {lastDecision && (
                    <div className="mt-2 flex items-center gap-1.5">
                      <span className="text-xs text-text-muted">Last decision:</span>
                      <StatusBadge tone={decisionTone(lastDecision.decision)} label={decisionLabel(lastDecision.decision)} />
                    </div>
                  )}
                </div>
              </div>
              <Button size="sm" variant="secondary" onClick={() => onReview(item)} className="shrink-0">
                Review
              </Button>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
