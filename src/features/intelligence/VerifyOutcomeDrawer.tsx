import { type FormEvent, useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { Textarea } from '../../components/ui/Textarea';
import { Input } from '../../components/ui/Input';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { LoadingState } from '../../components/ui/LoadingState';
import { ApiError } from '../../services/api/errors';
import type { IntelligenceDecision } from '../../services/api/decisions';
import type { IntelligenceOutcome } from '../../services/api/outcomes';
import {
  createVerification,
  getVerificationState,
  type IntelligenceOutcomeVerification,
  type VerificationState,
} from '../../services/api/verifications';
import type { AsyncState } from '../../types/common';
import {
  VERIFICATION_STATUS_OPTIONS,
  attentionCategoryLabel,
  decisionLabel,
  decisionTone,
  evidenceStatusLabel,
  outcomeClassificationLabel,
  outcomeClassificationTone,
  verificationStatusDescription,
  verificationStatusLabel,
  verificationStatusTone,
} from './intelligenceLabels';

export interface VerifyOutcomeDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  outcome: IntelligenceOutcome | null;
  /** The decision this outcome was recorded against — passed in already
   * fetched (mirrors `RecordOutcomeDrawer`'s own decision-context prop)
   * so this drawer never re-derives "what did we decide?" itself. */
  decision: IntelligenceDecision | null;
  organizationId: string;
  onVerified: (verification: IntelligenceOutcomeVerification) => void;
}

/** Today's date in the browser's own local time zone, as `yyyy-MM-dd` —
 * identical helper to `RecordOutcomeDrawer`'s own, duplicated rather than
 * shared to keep each drawer a single, independently-readable file (the
 * existing codebase convention — see e.g. `intelligence.ts`/
 * `decisions.ts` each defining their own small helpers rather than a
 * shared utils grab-bag). */
function todayDateInputValue(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function dateInputValueToIsoInstant(value: string): string {
  return new Date(`${value}T00:00:00`).toISOString();
}

/**
 * Outcome -> Verification (SIE Milestone 38/42). A **governance**
 * question, distinct from both earlier stages: not "what did we
 * decide?" (Decision), not "what actually happened?" (Outcome), but
 * "has the recorded outcome been adequately supported?" Mirrors
 * `RecordOutcomeDrawer`'s own three-part shape (prior context, current
 * state, human judgment form) and its "SIE never decided anything"
 * discipline: nothing here is computed by SIE except the deterministic,
 * already-existing evidence evaluation this drawer only *displays*,
 * never re-derives. Uses the real, already-tested
 * `POST /intelligence/outcomes/{outcome_id}/verifications` and
 * `GET .../verification-state` endpoints
 * (`backend/app/api/v1/intelligence_outcomes.py`) — no new backend
 * capability. Deliberately never renders `learning_eligibility` — see
 * `services/api/verifications.ts`'s own module docstring for why.
 */
export function VerifyOutcomeDrawer({ isOpen, onClose, outcome, decision, organizationId, onVerified }: VerifyOutcomeDrawerProps) {
  const [stateResult, setStateResult] = useState<AsyncState<VerificationState>>({ status: 'loading' });

  const [status, setStatus] = useState('');
  const [rationale, setRationale] = useState('');
  const [verifiedAtDate, setVerifiedAtDate] = useState(todayDateInputValue());
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [justVerified, setJustVerified] = useState<IntelligenceOutcomeVerification | null>(null);

  useEffect(() => {
    if (!isOpen || !outcome) return;
    setStatus('');
    setRationale('');
    setVerifiedAtDate(todayDateInputValue());
    setValidationError(null);
    setSubmitError(null);
    setJustVerified(null);
    setIdempotencyKey(crypto.randomUUID());
  }, [isOpen, outcome]);

  // The current governance state for this exact outcome — its own
  // independent loading lane, never blocking the rest of the drawer on
  // failure (mirrors AttentionReviewDrawer's organizational-memory lane).
  useEffect(() => {
    if (!isOpen || !outcome) return;
    const controller = new AbortController();
    setStateResult({ status: 'loading' });
    getVerificationState({ organizationId, outcomeId: outcome.id }, controller.signal)
      .then((result) => setStateResult({ status: 'success', data: result }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setStateResult({ status: 'error', message: error instanceof Error ? error.message : 'Could not load verification state.' });
      });
    return () => controller.abort();
  }, [isOpen, outcome, organizationId, justVerified]);

  if (!outcome || !decision) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);

    if (!status) {
      setValidationError('Choose a verification status.');
      return;
    }
    if (!rationale.trim()) {
      setValidationError('Rationale is required.');
      return;
    }
    if (!verifiedAtDate) {
      setValidationError('Choose when this review took place.');
      return;
    }
    setValidationError(null);
    setSubmitting(true);
    try {
      const record = await createVerification(
        {
          organizationId,
          outcomeId: outcome!.id,
          input: {
            status: status as IntelligenceOutcomeVerification['status'],
            rationale: rationale.trim(),
            verifiedAt: dateInputValueToIsoInstant(verifiedAtDate),
          },
        },
        idempotencyKey,
      );
      setJustVerified(record);
      onVerified(record);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError("You don't have permission to verify outcomes in this organization. Ask an administrator for intelligence:decision_write access.");
      } else if (error instanceof ApiError && error.status === 404) {
        setSubmitError('This outcome could not be found. It may have been recorded in a different organization.');
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not record this verification.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Verify outcome">
      <div className="flex flex-col gap-5">
        {/* --- What did we decide? (prior context, unchanged) -------------------- */}
        <section className="rounded-lg border border-border bg-surface-muted p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Decision — what did we decide?</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-text-primary">{decision.attention_title}</p>
            <StatusBadge tone={decisionTone(decision.decision)} label={decisionLabel(decision.decision)} />
          </div>
          <p className="mt-0.5 text-xs text-text-muted">
            {attentionCategoryLabel(decision.attention_category)}
            {decision.site_label ? ` · ${decision.site_label}` : ' · Organization-wide'}
          </p>
        </section>

        {/* --- Outcome being verified --------------------------------------------- */}
        <section className="rounded-lg border border-border-strong bg-surface-muted p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Outcome being verified — what actually happened?</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <StatusBadge tone={outcomeClassificationTone(outcome.classification)} label={outcomeClassificationLabel(outcome.classification)} />
            <span className="text-xs text-text-muted">
              {new Date(outcome.outcome_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
            </span>
          </div>
          <p className="mt-2 text-sm text-text-secondary">{outcome.summary}</p>
        </section>

        {/* --- Current governance state ------------------------------------------- */}
        <section>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Current verification state</p>
          <div className="mt-2">
            {stateResult.status === 'loading' && <LoadingState label="Checking verification state…" />}
            {stateResult.status === 'error' && (
              <p className="text-xs text-text-muted">Verification state is unavailable right now ({stateResult.message}).</p>
            )}
            {stateResult.status === 'success' && (
              <div className="flex flex-col gap-1.5">
                {stateResult.data.current_verification ? (
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-text-muted">
                    <span>Last recorded:</span>
                    <StatusBadge
                      tone={verificationStatusTone(stateResult.data.current_verification.status)}
                      label={verificationStatusLabel(stateResult.data.current_verification.status)}
                    />
                    <span>
                      {new Date(stateResult.data.current_verification.verified_at).toLocaleDateString(undefined, {
                        year: 'numeric', month: 'short', day: 'numeric',
                      })}
                    </span>
                  </div>
                ) : (
                  <p className="text-xs text-text-muted">Not yet verified.</p>
                )}
                <p className="text-xs text-text-muted">Evidence: {evidenceStatusLabel(stateResult.data.evidence_evaluation.evidence_status)}</p>
              </div>
            )}
          </div>
        </section>

        {/* --- Human governance judgment ------------------------------------------- */}
        <section className="border-t border-border pt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Verification — has this outcome been adequately supported?</p>
          {justVerified ? (
            <div className="mt-2 flex flex-col gap-2 rounded-md border border-success/30 bg-success-surface p-3">
              <div className="flex items-center gap-2">
                <StatusBadge tone={verificationStatusTone(justVerified.status)} label={verificationStatusLabel(justVerified.status)} />
                <span className="text-sm text-text-primary">recorded.</span>
              </div>
              <p className="text-xs text-text-secondary">{justVerified.rationale}</p>
              <Button type="button" variant="secondary" size="sm" onClick={onClose} className="self-start">
                Close
              </Button>
            </div>
          ) : (
            <form className="mt-2 flex flex-col gap-3" onSubmit={handleSubmit}>
              <p className="text-xs text-text-secondary">
                Your own governance judgment about this outcome's support — not a re-judgment of the original decision.
              </p>
              <Select
                label="Verification status"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                options={[{ value: '', label: 'Choose a verification status' }, ...VERIFICATION_STATUS_OPTIONS]}
              />
              {status && <p className="-mt-1.5 text-xs text-text-muted">{verificationStatusDescription(status)}</p>}

              <Input
                label="When did this review take place?"
                type="date"
                value={verifiedAtDate}
                max={todayDateInputValue()}
                onChange={(event) => setVerifiedAtDate(event.target.value)}
                helperText="Must not be in the future."
              />

              <Textarea
                label="Rationale"
                value={rationale}
                onChange={(event) => setRationale(event.target.value)}
                maxLength={4000}
                helperText="Required — why this verification judgment was made, for the record."
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
                  {submitting ? 'Recording…' : 'Record verification'}
                </Button>
              </div>
            </form>
          )}
        </section>
      </div>
    </Drawer>
  );
}
