import { type FormEvent, useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { SearchInput } from '../../components/ui/SearchInput';
import { Textarea } from '../../components/ui/Textarea';
import { Input } from '../../components/ui/Input';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { ApiError } from '../../services/api/errors';
import type { IntelligenceDecision } from '../../services/api/decisions';
import type { EventSummaryResponse } from '../../services/api/events';
import { listEvents } from '../../services/api/events';
import { createOutcome, type IntelligenceOutcome } from '../../services/api/outcomes';
import { useActionRepository } from '../actions/useActionRepository';
import type { ActionOption } from '../actions/actionRepository';
import { formatCanonicalLabel } from '../events/eventStatus';
import {
  OUTCOME_CLASSIFICATION_OPTIONS,
  attentionCategoryLabel,
  decisionLabel,
  decisionTone,
  outcomeClassificationDescription,
  outcomeClassificationLabel,
} from './intelligenceLabels';

export interface RecordOutcomeDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  decision: IntelligenceDecision | null;
  organizationId: string;
  onRecorded: (outcome: IntelligenceOutcome) => void;
}

/** Today's date in the browser's own local time zone, as `yyyy-MM-dd` —
 * built from local date fields rather than `toISOString()` specifically
 * to avoid a UTC-boundary shift making "today" look like tomorrow (or
 * yesterday) depending on the viewer's offset. */
function todayDateInputValue(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** A date picked in the user's own local time, at local midnight, as a
 * real ISO instant — always at or before "now" for today or any past
 * date (so a legitimate pick is never rejected as a future timestamp by
 * the backend's own `reject_future_outcome_at()`), while a genuinely
 * future date is still correctly rejected. */
function dateInputValueToIsoInstant(value: string): string {
  return new Date(`${value}T00:00:00`).toISOString();
}

/**
 * Decision -> Outcome (SIE Milestone 37/42). Mirrors
 * `AttentionReviewDrawer`'s own "SIE signal" / "Human decision" split:
 * the top card is **what was decided** (already recorded, immutable),
 * the form below is **what actually happened** — a distinct, later,
 * separately-authored fact about the real world, never a correction to
 * the decision itself. Uses the real, already-tested
 * `POST /intelligence/outcomes` endpoint
 * (`backend/app/api/v1/intelligence_outcomes.py`) — no new backend
 * capability, no new field the backend does not already accept.
 */
export function RecordOutcomeDrawer({ isOpen, onClose, decision, organizationId, onRecorded }: RecordOutcomeDrawerProps) {
  const actionRepository = useActionRepository();

  const [classification, setClassification] = useState('');
  const [summary, setSummary] = useState('');
  const [outcomeAtDate, setOutcomeAtDate] = useState(todayDateInputValue());
  const [linkedActionId, setLinkedActionId] = useState('');
  const [actionOptions, setActionOptions] = useState<ActionOption[]>([]);
  const [evidenceSearch, setEvidenceSearch] = useState('');
  const [evidenceResults, setEvidenceResults] = useState<EventSummaryResponse[]>([]);
  const [selectedEvidenceEvents, setSelectedEvidenceEvents] = useState<EventSummaryResponse[]>([]);
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [justRecorded, setJustRecorded] = useState<IntelligenceOutcome | null>(null);

  useEffect(() => {
    if (!isOpen || !decision) return;
    setClassification('');
    setSummary('');
    setOutcomeAtDate(todayDateInputValue());
    setLinkedActionId('');
    setEvidenceSearch('');
    setEvidenceResults([]);
    setSelectedEvidenceEvents([]);
    setValidationError(null);
    setSubmitError(null);
    setJustRecorded(null);
    setIdempotencyKey(crypto.randomUUID());
  }, [isOpen, decision]);

  // Evidence events this outcome can cite (e.g. a follow-up
  // observation) — required for its verification to ever reach
  // VERIFIED (an outcome with no evidence is NO_EVIDENCE, which the
  // backend's own `evaluate_evidence()` never counts as eligible).
  // Scoped to the decision's own site when it has one, same convention
  // as the open-action lookup above.
  useEffect(() => {
    if (!isOpen || !decision || !evidenceSearch.trim()) {
      setEvidenceResults([]);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    listEvents({
      organizationId,
      page: 1,
      pageSize: 10,
      siteId: decision.site_id ?? undefined,
      search: evidenceSearch.trim(),
      signal: controller.signal,
    })
      .then((page) => {
        if (cancelled) return;
        setEvidenceResults(page.items);
      })
      .catch(() => {
        if (!cancelled) setEvidenceResults([]);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [isOpen, decision, organizationId, evidenceSearch]);

  // Candidate actions to link — an outcome may optionally reference an
  // existing open action regardless of which decision type was recorded
  // (SIE Milestone 42 spec: "Do NOT implement automatic action
  // creation" — only ever an existing, already-open action, same
  // convention as `AttentionReviewDrawer`'s own action-linking).
  useEffect(() => {
    if (!isOpen || !decision) return;
    let cancelled = false;
    actionRepository
      .list({ page: 1, pageSize: 50, status: 'OPEN', site: decision.site_id ?? undefined })
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
  }, [isOpen, decision, actionRepository]);

  if (!decision) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    if (!classification) {
      setValidationError('Choose a classification.');
      return;
    }
    if (!summary.trim()) {
      setValidationError('Summary is required.');
      return;
    }
    if (!outcomeAtDate) {
      setValidationError('Choose when this outcome became observable.');
      return;
    }
    setValidationError(null);
    setSubmitting(true);
    try {
      const record = await createOutcome(
        {
          organizationId,
          input: {
            decisionId: decision!.id,
            siteId: decision!.site_id ?? undefined,
            classification: classification as IntelligenceOutcome['classification'],
            summary: summary.trim(),
            outcomeAt: dateInputValueToIsoInstant(outcomeAtDate),
            linkedActionId: linkedActionId || undefined,
            evidenceEventIds: selectedEvidenceEvents.length > 0 ? selectedEvidenceEvents.map((event) => event.id) : undefined,
          },
        },
        idempotencyKey,
      );
      setJustRecorded(record);
      onRecorded(record);
    } catch (error) {
      // A 403 (missing intelligence:decision_write in this organization)
      // gets its own, distinct message rather than being folded into the
      // generic catch-all below — the backend already distinguishes
      // this case (see intelligence_outcomes.py's
      // require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
      // so the UI must not hide that distinction behind one flat error
      // string.
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError("You don't have permission to record outcomes in this organization. Ask an administrator for intelligence:decision_write access.");
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not record this outcome.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Record outcome">
      <div className="flex flex-col gap-5">
        {/* --- What did we decide? --------------------------------------------- */}
        <section className="rounded-lg border border-border-strong bg-surface-muted p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Decision — what did we decide?</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-text-primary">{decision.attention_title}</p>
            <StatusBadge tone={decisionTone(decision.decision)} label={decisionLabel(decision.decision)} />
          </div>
          <p className="mt-0.5 text-xs text-text-muted">
            {attentionCategoryLabel(decision.attention_category)}
            {decision.site_label ? ` · ${decision.site_label}` : ' · Organization-wide'}
          </p>
          <p className="mt-2 text-sm text-text-secondary">{decision.rationale}</p>
          <div className="mt-2.5 border-t border-border pt-2.5 text-xs text-text-muted">
            <p>
              Decided {new Date(decision.decided_at).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              {' · '}
              Signal reference <span className="font-mono">{decision.attention_reference}</span>
            </p>
          </div>
        </section>

        {/* --- What actually happened? ------------------------------------------ */}
        <section className="border-t border-border pt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Outcome — what actually happened?</p>
          {justRecorded ? (
            <div className="mt-2 flex flex-col gap-2 rounded-md border border-success/30 bg-success-surface p-3">
              <div className="flex items-center gap-2">
                <StatusBadge tone="success" label={outcomeClassificationLabel(justRecorded.classification)} />
                <span className="text-sm text-text-primary">recorded.</span>
              </div>
              <p className="text-xs text-text-secondary">{justRecorded.summary}</p>
              <Button type="button" variant="secondary" size="sm" onClick={onClose} className="self-start">
                Close
              </Button>
            </div>
          ) : (
            <form className="mt-2 flex flex-col gap-3" onSubmit={handleSubmit}>
              <p className="text-xs text-text-secondary">
                A separate, later fact about the real world — not a correction to the decision above.
              </p>
              <Select
                label="Classification"
                value={classification}
                onChange={(event) => setClassification(event.target.value)}
                options={[{ value: '', label: 'Choose a classification' }, ...OUTCOME_CLASSIFICATION_OPTIONS]}
              />
              {classification && <p className="-mt-1.5 text-xs text-text-muted">{outcomeClassificationDescription(classification)}</p>}

              <Input
                label="When did this become observable?"
                type="date"
                value={outcomeAtDate}
                max={todayDateInputValue()}
                onChange={(event) => setOutcomeAtDate(event.target.value)}
                helperText="Must not be in the future."
              />

              <Select
                label="Link to an existing open action (optional)"
                value={linkedActionId}
                onChange={(event) => setLinkedActionId(event.target.value)}
                options={[{ value: '', label: 'No linked action' }, ...actionOptions]}
              />

              <div className="flex flex-col gap-1.5">
                <p className="text-xs font-medium text-text-secondary">Evidence events (optional)</p>
                <p className="text-xs text-text-muted">
                  Search for a follow-up observation supporting this outcome. Required for this outcome to later reach "Verified".
                </p>
                <SearchInput
                  label="Search events"
                  placeholder="Search by event type, status, or reference…"
                  value={evidenceSearch}
                  onChange={(event) => setEvidenceSearch(event.target.value)}
                  onClear={() => setEvidenceSearch('')}
                />
                {evidenceResults.length > 0 && (
                  <ul className="flex flex-col gap-1 rounded-md border border-border bg-surface-muted p-1.5">
                    {evidenceResults
                      .filter((result) => !selectedEvidenceEvents.some((selected) => selected.id === result.id))
                      .map((result) => (
                        <li key={result.id} className="flex items-center justify-between gap-2 rounded px-1.5 py-1 text-xs hover:bg-surface">
                          <span className="text-text-secondary">
                            {formatCanonicalLabel(result.event_type)} · {new Date(result.event_time).toLocaleDateString()}
                            {result.site_name ? ` · ${result.site_name}` : ''}
                          </span>
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                              setSelectedEvidenceEvents((current) => [...current, result]);
                              setEvidenceSearch('');
                            }}
                          >
                            Add
                          </Button>
                        </li>
                      ))}
                  </ul>
                )}
                {selectedEvidenceEvents.length > 0 && (
                  <ul className="flex flex-wrap gap-1.5">
                    {selectedEvidenceEvents.map((event) => (
                      <li key={event.id} className="flex items-center gap-1 rounded-full border border-border-strong bg-surface px-2 py-0.5 text-xs text-text-secondary">
                        {formatCanonicalLabel(event.event_type)} · {new Date(event.event_time).toLocaleDateString()}
                        <button
                          type="button"
                          aria-label={`Remove ${formatCanonicalLabel(event.event_type)} evidence event`}
                          className="text-text-muted hover:text-critical"
                          onClick={() => setSelectedEvidenceEvents((current) => current.filter((selected) => selected.id !== event.id))}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <Textarea
                label="Summary"
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                maxLength={4000}
                helperText="Required — why you believe this outcome occurred, for the record."
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
                  {submitting ? 'Recording…' : 'Record outcome'}
                </Button>
              </div>
            </form>
          )}
        </section>
      </div>
    </Drawer>
  );
}
