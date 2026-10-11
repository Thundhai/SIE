import { type FormEvent, useEffect, useState } from 'react';
import { Info } from 'lucide-react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { Textarea } from '../../components/ui/Textarea';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import type { AttentionItem } from '../../services/api/attention';
import { createDecision, listDecisions, type IntelligenceDecision } from '../../services/api/decisions';
import { getMemoryContext, getSiteMemoryContext, type IntegratedMemory } from '../../services/api/memoryIntegration';
import { useActionRepository } from '../actions/useActionRepository';
import type { ActionOption } from '../actions/actionRepository';
import { OrganizationalMemoryCard } from './OrganizationalMemoryCard';
import {
  DECISION_OPTIONS,
  attentionCategoryLabel,
  attentionPriorityTone,
  decisionDescription,
  decisionLabel,
  decisionTone,
} from './intelligenceLabels';
import type { AsyncState } from '../../types/common';

export interface AttentionReviewDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  item: AttentionItem | null;
  organizationId: string;
  onDecided: (decision: IntelligenceDecision) => void;
}

/**
 * Attention -> Review -> Decision (SIE Milestone 33/34/42 spec §6). The
 * drawer makes the boundary explicit: the top card is what SIE observed
 * and computed ("SIE signal"); the form below is where a human reviews
 * it and records their own decision ("human decision") — SIE never
 * implies it made the decision itself. Relevant organizational memory
 * (SIE Milestone 41, §11) is fetched for this exact item's own
 * scope/site/`as_of` — never a client-side applicability guess — and
 * shown only when the backend actually returns something.
 */
export function AttentionReviewDrawer({ isOpen, onClose, item, organizationId, onDecided }: AttentionReviewDrawerProps) {
  const actionRepository = useActionRepository();

  const [memoryState, setMemoryState] = useState<AsyncState<IntegratedMemory[]>>({ status: 'loading' });
  const [historyState, setHistoryState] = useState<AsyncState<IntelligenceDecision[]>>({ status: 'loading' });

  const [decision, setDecision] = useState('');
  const [rationale, setRationale] = useState('');
  const [linkedActionId, setLinkedActionId] = useState('');
  const [actionOptions, setActionOptions] = useState<ActionOption[]>([]);
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [justRecorded, setJustRecorded] = useState<IntelligenceDecision | null>(null);

  useEffect(() => {
    if (!isOpen || !item) return;
    setDecision('');
    setRationale('');
    setLinkedActionId('');
    setValidationError(null);
    setSubmitError(null);
    setJustRecorded(null);
    setIdempotencyKey(crypto.randomUUID());
  }, [isOpen, item]);

  // Relevant organizational memory — independent lane, own loading/error
  // state, never blanks the rest of the drawer on failure.
  useEffect(() => {
    if (!isOpen || !item) return;
    const controller = new AbortController();
    setMemoryState({ status: 'loading' });
    const request =
      item.scope === 'site' && item.site_id
        ? getSiteMemoryContext({ organizationId, siteId: item.site_id, asOf: item.as_of }, controller.signal)
        : getMemoryContext({ organizationId, asOf: item.as_of }, controller.signal);
    request
      .then((result) => setMemoryState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setMemoryState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load organizational memory.' });
      });
    return () => controller.abort();
  }, [isOpen, item, organizationId]);

  // This signal's own decision history — independent lane.
  useEffect(() => {
    if (!isOpen || !item) return;
    const controller = new AbortController();
    setHistoryState({ status: 'loading' });
    listDecisions({ organizationId, attentionReference: item.reference, pageSize: 20 }, controller.signal)
      .then((result) => setHistoryState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHistoryState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load decision history.' });
      });
    return () => controller.abort();
  }, [isOpen, item, organizationId, justRecorded]);

  // Candidate actions to link — only fetched once the human has chosen
  // "Act", and only ever an existing, already-open action (SIE Milestone
  // 42 spec §7: never a new corrective-action-management system here).
  useEffect(() => {
    if (!isOpen || !item || decision !== 'ACT') return;
    let cancelled = false;
    actionRepository
      .list({ page: 1, pageSize: 50, status: 'OPEN', site: item.site_id ?? undefined })
      .then((page) => {
        if (cancelled) return;
        setActionOptions(page.items.map((action) => ({ value: action.id, label: action.title })));
      })
      .catch(() => {
        if (!cancelled) setActionOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, item, decision, actionRepository]);

  if (!item) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    if (!decision) {
      setValidationError('Choose a decision.');
      return;
    }
    if (!rationale.trim()) {
      setValidationError('Rationale is required.');
      return;
    }
    setValidationError(null);
    setSubmitting(true);
    try {
      const record = await createDecision(
        {
          organizationId,
          input: {
            scope: item!.scope,
            siteId: item!.site_id ?? undefined,
            asOf: item!.as_of,
            windowDays: item!.window_days,
            attentionReference: item!.reference,
            decision: decision as IntelligenceDecision['decision'],
            rationale: rationale.trim(),
            linkedActionId: decision === 'ACT' && linkedActionId ? linkedActionId : undefined,
          },
        },
        idempotencyKey,
      );
      setJustRecorded(record);
      onDecided(record);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Could not record this decision.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Review">
      <div className="flex flex-col gap-5">
        {/* --- SIE signal ---------------------------------------------------- */}
        <section className="rounded-lg border border-border-strong bg-surface-muted p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">SIE signal</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-text-primary">{item.title}</p>
            <StatusBadge tone={attentionPriorityTone(item.priority)} label={item.priority} />
          </div>
          <p className="mt-0.5 text-xs text-text-muted">
            {attentionCategoryLabel(item.category)}
            {item.site_label ? ` · ${item.site_label}` : ' · Organization-wide'}
          </p>
          <p className="mt-2 text-sm text-text-secondary">{item.explanation}</p>
          {item.limitation && <p className="mt-1.5 text-xs text-text-muted">{item.limitation}</p>}
          <div className="mt-2.5 border-t border-border pt-2.5 text-xs text-text-muted">
            <p>
              Supporting evidence: {item.evidence.source}
              {item.evidence.event_ids.length > 0 ? ` · ${item.evidence.event_ids.length} recorded event(s)` : ''}
              {item.evidence.entity_ids.length > 0 ? ` · ${item.evidence.entity_ids.length} related record(s)` : ''}
            </p>
            <p className="mt-0.5">
              As of {new Date(item.as_of).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              {' · '}
              Reference <span className="font-mono">{item.reference}</span>
            </p>
          </div>
        </section>

        {/* --- Relevant organizational memory --------------------------------- */}
        <section>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Relevant organizational memory</p>
          <div className="mt-2">
            {memoryState.status === 'loading' && <LoadingState label="Checking organizational memory…" />}
            {memoryState.status === 'error' && (
              <p className="flex items-center gap-1.5 text-xs text-text-muted">
                <Info className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                Organizational memory is unavailable right now ({memoryState.message}).
              </p>
            )}
            {memoryState.status === 'success' && memoryState.data.length === 0 && (
              <p className="flex items-center gap-1.5 text-xs text-text-muted">
                <Info className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                No governed organizational memory applies here.
              </p>
            )}
            {memoryState.status === 'success' && memoryState.data.length > 0 && (
              <div className="flex flex-col gap-2">
                {memoryState.data.map((memory) => (
                  <OrganizationalMemoryCard key={memory.memory_id} memory={memory} />
                ))}
              </div>
            )}
          </div>
        </section>

        {/* --- Decision history for this signal -------------------------------- */}
        {historyState.status === 'success' && historyState.data.length > 0 && (
          <section>
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Previous decisions on this signal</p>
            <ul className="mt-2 flex flex-col gap-1.5">
              {historyState.data.map((record) => (
                <li key={record.id} className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-2">
                  <div>
                    <StatusBadge tone={decisionTone(record.decision)} label={decisionLabel(record.decision)} />
                    <p className="mt-1 text-xs text-text-secondary">{record.rationale}</p>
                  </div>
                  <p className="shrink-0 text-xs text-text-muted">{new Date(record.decided_at).toLocaleDateString()}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* --- Human decision -------------------------------------------------- */}
        <section className="border-t border-border pt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Human decision</p>
          {justRecorded ? (
            <div className="mt-2 flex flex-col gap-2 rounded-md border border-success/30 bg-success-surface p-3">
              <div className="flex items-center gap-2">
                <StatusBadge tone={decisionTone(justRecorded.decision)} label={decisionLabel(justRecorded.decision)} />
                <span className="text-sm text-text-primary">recorded.</span>
              </div>
              <p className="text-xs text-text-secondary">{justRecorded.rationale}</p>
              <Button type="button" variant="secondary" size="sm" onClick={onClose} className="self-start">
                Close
              </Button>
            </div>
          ) : (
            <form className="mt-2 flex flex-col gap-3" onSubmit={handleSubmit}>
              <p className="text-xs text-text-secondary">
                This is your own judgment — SIE surfaced the signal above, it did not decide anything.
              </p>
              <Select
                label="Decision"
                value={decision}
                onChange={(event) => setDecision(event.target.value)}
                options={[{ value: '', label: 'Choose a decision' }, ...DECISION_OPTIONS]}
              />
              {decision && <p className="-mt-1.5 text-xs text-text-muted">{decisionDescription(decision)}</p>}

              {decision === 'ACT' && (
                <Select
                  label="Link to an existing open action (optional)"
                  value={linkedActionId}
                  onChange={(event) => setLinkedActionId(event.target.value)}
                  options={[{ value: '', label: 'No linked action' }, ...actionOptions]}
                />
              )}

              <Textarea
                label="Rationale"
                value={rationale}
                onChange={(event) => setRationale(event.target.value)}
                maxLength={4000}
                helperText="Required — why you made this decision, for the record."
              />

              {validationError && (
                <p role="alert" className="text-sm text-critical">
                  {validationError}
                </p>
              )}
              {submitError && (
                <p role="alert" className="text-sm text-critical">
                  {submitError}
                </p>
              )}

              <div className="flex justify-end gap-2">
                <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? 'Recording…' : 'Record decision'}
                </Button>
              </div>
            </form>
          )}
        </section>
      </div>
    </Drawer>
  );
}
