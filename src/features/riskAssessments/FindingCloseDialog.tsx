import { useEffect, useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Textarea } from '../../components/ui/Textarea';
import { closeFinding, type RiskAssessmentFinding } from '../../services/api/riskAssessments';

export interface FindingCloseDialogProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  assessmentId: string;
  finding: RiskAssessmentFinding;
  onClosed: (finding: RiskAssessmentFinding) => void;
}

/**
 * The one, deliberate finding-closure interaction — SIE Milestone UI-02
 * Part 11. Always calls the dedicated `POST .../findings/{finding_id}/close`
 * route (SIE Milestone 27's own "closure governance" gate); `CLOSED` is
 * never offered as a generic editable status anywhere else in this
 * frontend. Closing is never triggered automatically by a linked
 * action's own completion.
 */
export function FindingCloseDialog({ isOpen, onClose, organizationId, assessmentId, finding, onClosed }: FindingCloseDialogProps) {
  const [closureReason, setClosureReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setClosureReason('');
    setError(null);
  }, [isOpen]);

  async function handleSubmit() {
    if (!closureReason.trim()) {
      setError('A closure reason is required.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const updated = await closeFinding(organizationId, assessmentId, finding.id, closureReason.trim());
      onClosed(updated);
      onClose();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not close this finding.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Close finding">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-text-secondary">{finding.title}</p>

        <Textarea
          label="Closure reason"
          value={closureReason}
          onChange={(event) => setClosureReason(event.target.value)}
          maxLength={2000}
          required
          helperText="Explain why this finding is being closed — required, and recorded against this finding's history."
        />

        {error && (
          <p role="alert" className="text-sm text-critical">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="button" variant="danger" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Closing…' : 'Close finding'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
