import { useEffect, useState } from 'react';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { listDecisions, type IntelligenceDecision } from '../../services/api/decisions';
import type { IntelligenceOutcome } from '../../services/api/outcomes';
import type { AsyncState } from '../../types/common';
import { attentionCategoryLabel, decisionLabel, decisionTone, outcomeClassificationLabel, outcomeClassificationTone } from './intelligenceLabels';

export interface DecisionHistorySectionProps {
  organizationId: string;
  /** Bump this to force a reload (e.g. right after a new decision was
   * recorded elsewhere on the page). */
  refreshToken: number;
  /** The most recent outcome recorded for each decision's own `id`, when
   * one exists — built once from a real `GET /intelligence/outcomes`
   * response (never inferred client-side; see `IntelligencePage`'s own
   * `outcomesByDecision` construction, mirroring `decisionsByReference`'s
   * identical pattern). */
  outcomesByDecision: Map<string, IntelligenceOutcome>;
  onRecordOutcome: (decision: IntelligenceDecision) => void;
  /** Opens verification for the decision's own recorded outcome — only
   * ever called from the "Verify outcome" action below, which itself
   * only renders once `outcomesByDecision` has an entry for that
   * decision (there is nothing to verify before an outcome exists). */
  onVerifyOutcome: (decision: IntelligenceDecision, outcome: IntelligenceOutcome) => void;
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
export function DecisionHistorySection({ organizationId, refreshToken, outcomesByDecision, onRecordOutcome, onVerifyOutcome }: DecisionHistorySectionProps) {
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
          {state.data.map((record) => {
            const outcome = outcomesByDecision.get(record.id);
            return (
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
                <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2">
                  {outcome ? (
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-text-muted">Outcome:</span>
                      <StatusBadge tone={outcomeClassificationTone(outcome.classification)} label={outcomeClassificationLabel(outcome.classification)} />
                      <span className="text-xs text-text-muted">
                        {new Date(outcome.outcome_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                      </span>
                    </div>
                  ) : (
                    <span className="text-xs text-text-muted">No outcome recorded yet</span>
                  )}
                  <div className="flex items-center gap-2">
                    {outcome && (
                      <Button size="sm" variant="secondary" onClick={() => onVerifyOutcome(record, outcome)}>
                        Verify outcome
                      </Button>
                    )}
                    <Button size="sm" variant="secondary" onClick={() => onRecordOutcome(record)}>
                      Record outcome
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
