import { useEffect, useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Select } from '../../components/ui/Select';
import { Textarea } from '../../components/ui/Textarea';
import {
  assessControlEffectiveness,
  type RiskControl,
} from '../../services/api/riskAssessments';
import { ASSESSABLE_CONTROL_EFFECTIVENESS_OPTIONS } from './riskAssessmentLabels';

export interface ControlEffectivenessDialogProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  assessmentId: string;
  findingId: string;
  control: RiskControl;
  /** Called with the authoritative, server-returned control once the
   * assessment succeeds — the caller refreshes from this, never from a
   * locally-guessed value (SIE Milestone UI-02 Part 6: "do not locally
   * mutate the UI as if the server succeeded before receiving
   * confirmation"). */
  onAssessed: (control: RiskControl) => void;
}

/**
 * The one restrained interaction for assessing a control's effectiveness
 * — SIE Milestone UI-02 Part 6. Always calls the dedicated
 * `POST .../controls/{control_id}/assess-effectiveness` route (SIE
 * Milestone 29A's own single authoritative mutation path) — never the
 * generic finding update. `NOT_ASSESSED` is never offered as a target
 * (the backend rejects it as a conclusion), and the rationale is
 * required because the backend requires it — this dialog cannot submit
 * without one.
 */
export function ControlEffectivenessDialog({
  isOpen,
  onClose,
  organizationId,
  assessmentId,
  findingId,
  control,
  onAssessed,
}: ControlEffectivenessDialogProps) {
  const [effectiveness, setEffectiveness] = useState('EFFECTIVE');
  const [rationale, setRationale] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    setEffectiveness(control.effectiveness === 'NOT_ASSESSED' ? 'EFFECTIVE' : control.effectiveness);
    setRationale(control.effectiveness_rationale ?? '');
    setError(null);
    setIdempotencyKey(crypto.randomUUID());
  }, [isOpen, control]);

  async function handleSubmit() {
    if (!rationale.trim()) {
      setError('A rationale is required to record this assessment.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const updated = await assessControlEffectiveness(
        organizationId,
        assessmentId,
        findingId,
        control.id,
        {
          effectiveness_rating: effectiveness as 'EFFECTIVE' | 'PARTIALLY_EFFECTIVE' | 'INEFFECTIVE',
          effectiveness_rationale: rationale.trim(),
        },
        idempotencyKey,
      );
      onAssessed(updated);
      onClose();
    } catch (submitError) {
      // Preserve what was entered — never clear the form on failure — and
      // never fabricate success (Part 6's own explicit requirement).
      setError(submitError instanceof Error ? submitError.message : 'Could not record this assessment.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Assess control effectiveness">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-text-secondary">{control.description}</p>

        <Select
          label="Effectiveness"
          value={effectiveness}
          onChange={(event) => setEffectiveness(event.target.value)}
          options={ASSESSABLE_CONTROL_EFFECTIVENESS_OPTIONS}
        />

        <Textarea
          label="Rationale"
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          maxLength={2000}
          required
          helperText="Explain why this control is rated this way — required to record an assessment."
        />

        {control.assessed_at && (
          <p className="text-xs text-text-muted">
            Last assessed {new Date(control.assessed_at).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            {control.assessed_by_user_id ? ' by a recorded assessor.' : '.'}
          </p>
        )}

        {error && (
          <p role="alert" className="text-sm text-critical">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Saving…' : 'Record assessment'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
