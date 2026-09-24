import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Textarea } from '../../components/ui/Textarea';
import {
  createIntelligenceOutcome,
  createOutcomeVerification,
  getOutcomeVerificationState,
  listIntelligenceOutcomes,
  type IntelligenceOutcome,
  type IntelligenceOutcomeClassification,
  type IntelligenceOutcomeVerificationStatus,
  type OutcomeVerificationState,
} from '../../services/api/intelligenceOutcomes';
import { listIntelligenceDecisions, type IntelligenceDecision } from '../../services/api/intelligenceDecisions';
import type { SafetyAction } from '../../types/actions';

function todayDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function dateAtNoonIso(value: string): string {
  return new Date(`${value}T12:00:00`).toISOString();
}

function classificationLabel(value: IntelligenceOutcomeClassification): string {
  return {
    EFFECTIVE: 'Effective',
    PARTIALLY_EFFECTIVE: 'Partially effective',
    INEFFECTIVE: 'Ineffective',
    NO_OUTCOME_RECORDED: 'No outcome established',
  }[value];
}

function verificationLabel(value: IntelligenceOutcomeVerificationStatus): string {
  return {
    VERIFIED: 'Verified',
    INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
    DISPUTED: 'Disputed',
  }[value];
}

/**
 * Outcome lifecycle for a completed SafetyAction.
 *
 * Deliberately keeps Action completion separate from outcome recording and
 * verification. The backend is authoritative for evidence eligibility and
 * verification rules.
 */
export function ActionOutcomeLifecycle({ action }: { action: SafetyAction }) {
  const { organization, hasPermission } = useAuth();
  const canWrite = hasPermission('intelligence:decision_write');

  const [decision, setDecision] = useState<IntelligenceDecision | null>(null);
  const [outcome, setOutcome] = useState<IntelligenceOutcome | null>(null);
  const [verificationState, setVerificationState] = useState<OutcomeVerificationState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [classification, setClassification] =
    useState<IntelligenceOutcomeClassification>('EFFECTIVE');
  const [summary, setSummary] = useState('');
  const [outcomeDate, setOutcomeDate] = useState(todayDate());
  const [evidenceIds, setEvidenceIds] = useState('');

  const [verificationStatus, setVerificationStatus] =
    useState<IntelligenceOutcomeVerificationStatus>('VERIFIED');
  const [verificationRationale, setVerificationRationale] = useState('');
  const [verificationDate, setVerificationDate] = useState(todayDate());
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!organization) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    Promise.all([
      listIntelligenceDecisions({
        organizationId: organization.id,
        linkedActionId: action.id,
        page: 1,
        pageSize: 25,
      }),
      listIntelligenceOutcomes({
        organizationId: organization.id,
        linkedActionId: action.id,
        page: 1,
        pageSize: 25,
      }),
    ])
      .then(([decisions, outcomes]) => {
        setDecision(decisions.items[0] ?? null);
        setOutcome(outcomes.items[0] ?? null);
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return;
        setError(requestError instanceof Error ? requestError.message : 'Could not load outcome lifecycle.');
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [organization, action.id]);

  useEffect(() => {
    if (!organization || !outcome) {
      setVerificationState(null);
      return;
    }
    const controller = new AbortController();
    getOutcomeVerificationState(organization.id, outcome.id, controller.signal)
      .then(setVerificationState)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return;
        setError(requestError instanceof Error ? requestError.message : 'Could not load verification state.');
      });
    return () => controller.abort();
  }, [organization, outcome]);

  const parsedEvidenceIds = useMemo(
    () =>
      evidenceIds
        .split(/[\s,]+/)
        .map((value) => value.trim())
        .filter(Boolean),
    [evidenceIds],
  );

  async function handleRecordOutcome() {
    if (!organization || !decision) return;
    if (!summary.trim()) {
      setError('Enter a summary explaining the observed outcome.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const created = await createIntelligenceOutcome(
        organization.id,
        {
          decision_id: decision.id,
          site_id: action.siteId ?? undefined,
          linked_action_id: action.id,
          classification,
          summary: summary.trim(),
          evidence_event_ids: parsedEvidenceIds,
          outcome_at: dateAtNoonIso(outcomeDate),
        },
        crypto.randomUUID(),
      );
      setOutcome(created);
      setVerificationState(null);
      setSummary('');
      setEvidenceIds('');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not record the outcome.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerify() {
    if (!organization || !outcome) return;
    if (!verificationRationale.trim()) {
      setError('Enter the rationale for the verification judgment.');
      return;
    }
    if (verificationStatus === 'VERIFIED' && !verificationState?.evidence_evaluation.evidence_eligible_for_verification) {
      setError('The backend requires valid evidence before an outcome can be marked VERIFIED.');
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await createOutcomeVerification(
        organization.id,
        outcome.id,
        {
          status: verificationStatus,
          rationale: verificationRationale.trim(),
          verified_at: dateAtNoonIso(verificationDate),
        },
        crypto.randomUUID(),
      );
      const refreshed = await getOutcomeVerificationState(organization.id, outcome.id);
      setVerificationState(refreshed);
      setVerificationRationale('');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not record verification.');
    } finally {
      setSubmitting(false);
    }
  }

  if (action.status !== 'COMPLETED') return null;

  return (
    <section className="mt-6">
      <h2 className="text-base font-semibold text-navy-900">Outcome verification</h2>
      <p className="mt-1 text-sm text-text-secondary">
        Action completion records that the intervention was carried out. Outcome verification records what happened afterward.
      </p>

      <div className="mt-3 rounded-lg border border-border bg-surface p-4">
        {loading && <p className="text-sm text-text-secondary">Loading outcome lifecycle…</p>}

        {!loading && !decision && (
          <p className="text-sm text-text-secondary">
            No intelligence decision is linked to this action. An outcome requires an explicit Intelligence Decision reference;
            SIE will not infer one from action completion.
          </p>
        )}

        {!loading && decision && !outcome && (
          <div className="space-y-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Decision</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{decision.attention_title}</p>
              <p className="mt-1 text-xs text-text-secondary">
                {decision.decision} · {decision.attention_reference}
              </p>
            </div>

            {!canWrite && (
              <p className="text-sm text-text-secondary">You do not have permission to record an intelligence outcome.</p>
            )}

            {canWrite && (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Select
                    label="Observed outcome"
                    value={classification}
                    onChange={(event) => setClassification(event.target.value as IntelligenceOutcomeClassification)}
                    options={[
                      { value: 'EFFECTIVE', label: classificationLabel('EFFECTIVE') },
                      { value: 'PARTIALLY_EFFECTIVE', label: classificationLabel('PARTIALLY_EFFECTIVE') },
                      { value: 'INEFFECTIVE', label: classificationLabel('INEFFECTIVE') },
                      { value: 'NO_OUTCOME_RECORDED', label: classificationLabel('NO_OUTCOME_RECORDED') },
                    ]}
                  />
                  <Input
                    label="Outcome date"
                    type="date"
                    value={outcomeDate}
                    onChange={(event) => setOutcomeDate(event.target.value)}
                    max={todayDate()}
                  />
                </div>
                <Textarea
                  label="Outcome summary"
                  value={summary}
                  onChange={(event) => setSummary(event.target.value)}
                  placeholder="Describe what happened after the intervention and why this classification is appropriate."
                  rows={4}
                  maxLength={4000}
                />
                <Input
                  label="Evidence event IDs (optional)"
                  value={evidenceIds}
                  onChange={(event) => setEvidenceIds(event.target.value)}
                  placeholder="Paste Safety Event UUIDs separated by commas or spaces"
                  helperText="The backend validates every referenced event. Evidence is not treated as a confidence score."
                />
                <Button onClick={handleRecordOutcome} disabled={submitting}>
                  {submitting ? 'Recording…' : 'Record outcome'}
                </Button>
              </>
            )}
          </div>
        )}

        {!loading && outcome && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Outcome</p>
                <p className="mt-1 text-sm font-medium text-text-primary">{classificationLabel(outcome.classification)}</p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Outcome date</p>
                <p className="mt-1 text-sm text-text-primary">{new Date(outcome.outcome_at).toLocaleDateString()}</p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Evidence references</p>
                <p className="mt-1 text-sm text-text-primary">{outcome.evidence_event_ids.length}</p>
              </div>
            </div>

            <div className="rounded-md border border-border bg-canvas px-3 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Summary</p>
              <p className="mt-1 text-sm leading-relaxed text-text-primary">{outcome.summary}</p>
            </div>

            {verificationState && (
              <div className="space-y-3 rounded-md border border-border bg-canvas p-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Evidence evaluation</p>
                  <p className="mt-1 text-sm text-text-primary">
                    {verificationState.evidence_evaluation.evidence_status.replaceAll('_', ' ')}
                    {' · '}
                    {verificationState.evidence_evaluation.valid_evidence_count}/
                    {verificationState.evidence_evaluation.evidence_count} valid
                  </p>
                  {verificationState.evidence_evaluation.reasons.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-xs text-text-secondary">
                      {verificationState.evidence_evaluation.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                    </ul>
                  )}
                </div>

                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Current verification</p>
                  <p className="mt-1 text-sm text-text-primary">
                    {verificationState.current_verification
                      ? verificationLabel(verificationState.current_verification.status)
                      : 'Not verified'}
                  </p>
                </div>

                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Learning eligibility</p>
                  <p className="mt-1 text-sm text-text-primary">
                    {verificationState.learning_eligibility.eligible ? 'Eligible for learning consideration' : 'Not eligible'}
                  </p>
                  {verificationState.learning_eligibility.reasons.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-xs text-text-secondary">
                      {verificationState.learning_eligibility.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                    </ul>
                  )}
                </div>
              </div>
            )}

            {canWrite && verificationState && (
              <div className="space-y-3 border-t border-border pt-4">
                <h3 className="text-sm font-semibold text-text-primary">Record human verification</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Select
                    label="Verification judgment"
                    value={verificationStatus}
                    onChange={(event) => setVerificationStatus(event.target.value as IntelligenceOutcomeVerificationStatus)}
                    options={[
                      {
                        value: 'VERIFIED',
                        label: 'Verified',
                      },
                      {
                        value: 'INSUFFICIENT_EVIDENCE',
                        label: 'Insufficient evidence',
                      },
                      {
                        value: 'DISPUTED',
                        label: 'Disputed',
                      },
                    ]}
                  />
                  <Input
                    label="Verification date"
                    type="date"
                    value={verificationDate}
                    onChange={(event) => setVerificationDate(event.target.value)}
                    max={todayDate()}
                  />
                </div>
                <Textarea
                  label="Verification rationale"
                  value={verificationRationale}
                  onChange={(event) => setVerificationRationale(event.target.value)}
                  placeholder="Explain why the outcome/evidence is accepted, insufficient, or disputed."
                  rows={3}
                  maxLength={4000}
                />
                <Button onClick={handleVerify} disabled={submitting || (verificationStatus === 'VERIFIED' && !verificationState.evidence_evaluation.evidence_eligible_for_verification)}>
                  {submitting ? 'Recording…' : 'Record verification'}
                </Button>
              </div>
            )}
          </div>
        )}

        {error && <p role="alert" className="mt-3 text-sm text-critical">{error}</p>}
      </div>
    </section>
  );
}
