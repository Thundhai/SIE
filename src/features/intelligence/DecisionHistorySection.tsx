import { useEffect, useState } from 'react';
import { Section } from '../../components/layout/Section';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { listDecisions, type IntelligenceDecision } from '../../services/api/decisions';
import type { AsyncState } from '../../types/common';
import { attentionCategoryLabel, decisionLabel, decisionTone } from './intelligenceLabels';

export interface DecisionHistorySectionProps {
  organizationId: string;
  /** Bump this to force a reload (e.g. right after a new decision was
   * recorded elsewhere on the page). */
  refreshToken: number;
}

/**
 * "What decision has been made, and why?" (SIE Milestone 42 spec §6/
 * question 7) — the append-only `IntelligenceDecision` history (SIE
 * Milestone 34), most recent first, exactly as `GET /intelligence/
 * decisions` already orders it. Every row preserves the human
 * traceability the backend recorded: decision type, rationale, the
 * signal it concerned, and the linked action where one exists — never
 * implying SIE itself decided anything.
 */
export function DecisionHistorySection({ organizationId, refreshToken }: DecisionHistorySectionProps) {
  const [state, setState] = useState<AsyncState<IntelligenceDecision[]>>({ status: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    listDecisions({ organizationId, pageSize: 10 }, controller.signal)
      .then((result) => setState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load recent decisions.' });
      });
    return () => controller.abort();
  }, [organizationId, refreshToken]);

  return (
    <Section title="Recent decisions" description="Human decisions recorded against SIE's intelligence signals, most recent first.">
      {state.status === 'loading' && <LoadingState label="Loading recent decisions…" />}
      {state.status === 'error' && <ErrorState description={state.message} />}
      {state.status === 'success' && state.data.length === 0 && (
        <EmptyState title="No decisions recorded yet" description="Decisions recorded from the Attention list appear here." />
      )}
      {state.status === 'success' && state.data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {state.data.map((record) => (
            <li key={record.id} className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface p-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-text-primary">{record.attention_title}</p>
                <StatusBadge tone={decisionTone(record.decision)} label={decisionLabel(record.decision)} />
              </div>
              <p className="text-xs text-text-muted">
                {attentionCategoryLabel(record.attention_category)}
                {record.site_label ? ` · ${record.site_label}` : ' · Organization-wide'}
              </p>
              <p className="text-sm text-text-secondary">{record.rationale}</p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
                <span>{new Date(record.decided_at).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                {record.linked_action && <span>· Linked action: {record.linked_action.title}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
