import { useEffect, useState } from 'react';
import { Section } from '../../components/layout/Section';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { listDecisions, type IntelligenceDecision } from '../../services/api/decisions';
import { listOutcomes, type IntelligenceOutcome } from '../../services/api/outcomes';
import type { AsyncState } from '../../types/common';
import {
  attentionCategoryLabel,
  decisionLabel,
  decisionTone,
  outcomeClassificationLabel,
  outcomeClassificationTone,
} from '../intelligence/intelligenceLabels';

export interface ActionIntelligenceReferencesProps {
  actionId: string;
  /** `undefined` when no real organization is established (fixture-
   * backed Actions data) — this section renders nothing in that case,
   * matching `useActionRepository()`'s own real-API-vs-fixture split. */
  organizationId: string | undefined;
}

function formatDecidedAt(value: string): string {
  return new Date(value).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatOutcomeAt(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

/**
 * "Referenced by Intelligence" (SIE Operational Linkage Audit, finding
 * #1 — the audit's own recommended next milestone). A **read-only**
 * view of the existing, already-built reverse relationship from this
 * SafetyAction back to any `IntelligenceDecision`/`IntelligenceOutcome`
 * that named it via `linked_action_id`. Uses only the backend's own
 * already-tested `GET /intelligence/decisions?linked_action_id=` and
 * `GET /intelligence/outcomes?linked_action_id=` filters — no new
 * backend endpoint, query, field, or permission.
 *
 * A human-established reference only: this section never implies SIE
 * created, performed, owns, or automatically generated anything from
 * this action, and offers no create/edit/link/unlink control of its
 * own — those workflows live where they already do, in the Intelligence
 * Workspace's own Decision/Outcome drawers.
 *
 * Hides itself once both lookups have resolved and found nothing —
 * intelligence-linkage is the exception for most actions, not the rule,
 * so an empty section would be noise on every other action's page.
 * While either lookup is loading, or if either fails, it stays mounted
 * so those states are visible rather than silently absent — but a
 * failure here never blocks or replaces anything else on the page (each
 * lookup is its own independent loading lane, exactly like
 * `VerifyOutcomeDrawer`'s own verification-state lane).
 */
export function ActionIntelligenceReferences({ actionId, organizationId }: ActionIntelligenceReferencesProps) {
  const [decisionsState, setDecisionsState] = useState<AsyncState<IntelligenceDecision[]>>({ status: 'loading' });
  const [outcomesState, setOutcomesState] = useState<AsyncState<IntelligenceOutcome[]>>({ status: 'loading' });

  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    setDecisionsState({ status: 'loading' });
    listDecisions({ organizationId, linkedActionId: actionId, pageSize: 50 }, controller.signal)
      .then((result) => setDecisionsState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setDecisionsState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load linked Intelligence Decisions.' });
      });
    return () => controller.abort();
  }, [organizationId, actionId]);

  useEffect(() => {
    if (!organizationId) return;
    const controller = new AbortController();
    setOutcomesState({ status: 'loading' });
    listOutcomes({ organizationId, linkedActionId: actionId, pageSize: 50 }, controller.signal)
      .then((result) => setOutcomesState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setOutcomesState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load linked Intelligence Outcomes.' });
      });
    return () => controller.abort();
  }, [organizationId, actionId]);

  if (!organizationId) return null;

  const stillLoading = decisionsState.status === 'loading' || outcomesState.status === 'loading';
  const hasAnyError = decisionsState.status === 'error' || outcomesState.status === 'error';
  const decisions = decisionsState.status === 'success' ? decisionsState.data : [];
  const outcomes = outcomesState.status === 'success' ? outcomesState.data : [];
  const hasAnyReference = decisions.length > 0 || outcomes.length > 0;

  if (!stillLoading && !hasAnyError && !hasAnyReference) return null;

  return (
    <Section
      title="Referenced by Intelligence"
      description="Intelligence Decisions and Outcomes a human has linked to this action — a human-established reference, not something SIE created, performed, or owns."
    >
      <div className="flex flex-col gap-3">
        {stillLoading && <LoadingState label="Checking for Intelligence references…" />}

        {decisionsState.status === 'error' && (
          <p className="text-xs text-text-muted">Linked Intelligence Decisions are unavailable right now ({decisionsState.message}).</p>
        )}
        {decisions.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Intelligence Decision{decisions.length > 1 ? 's' : ''}
            </p>
            {decisions.map((decision) => (
              <div key={decision.id} className="rounded-lg border border-border bg-surface p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-text-primary">{decision.attention_title}</p>
                  <StatusBadge tone={decisionTone(decision.decision)} label={decisionLabel(decision.decision)} />
                </div>
                <p className="mt-0.5 text-xs text-text-muted">
                  {attentionCategoryLabel(decision.attention_category)}
                  {decision.site_label ? ` · ${decision.site_label}` : ' · Organization-wide'}
                </p>
                <p className="mt-1.5 text-sm text-text-secondary">{decision.rationale}</p>
                <p className="mt-1.5 text-xs text-text-muted">Decided {formatDecidedAt(decision.decided_at)}</p>
              </div>
            ))}
          </div>
        )}

        {outcomesState.status === 'error' && (
          <p className="text-xs text-text-muted">Linked Intelligence Outcomes are unavailable right now ({outcomesState.message}).</p>
        )}
        {outcomes.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Intelligence Outcome{outcomes.length > 1 ? 's' : ''}
            </p>
            {outcomes.map((outcome) => (
              <div key={outcome.id} className="rounded-lg border border-border bg-surface p-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={outcomeClassificationTone(outcome.classification)} label={outcomeClassificationLabel(outcome.classification)} />
                  <span className="text-xs text-text-muted">{formatOutcomeAt(outcome.outcome_at)}</span>
                </div>
                <p className="mt-1.5 text-sm text-text-secondary">{outcome.summary}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}
