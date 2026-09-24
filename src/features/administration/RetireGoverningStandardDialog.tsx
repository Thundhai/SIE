import { type FormEvent, useEffect, useState } from 'react';
import { Modal } from '../../components/ui/Modal';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Textarea } from '../../components/ui/Textarea';
import { ApiError } from '../../services/api/errors';
import {
  retireGoverningStandard,
  type ActiveGoverningStandard,
  type OrganizationGoverningStandardEntry,
} from '../../services/api/administration';

export interface RetireGoverningStandardDialogProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  /** The one currently-SELECTED entry this dialog is offering to
   * retire. */
  entry: ActiveGoverningStandard | null;
  onRetired: (retirement: OrganizationGoverningStandardEntry) => void;
}

/**
 * RETIRED — `POST /organization-governing-standards/{standard_id}/retire`.
 * Always a new append-only event, never a deletion of the prior
 * selection (the backend has no DELETE on this log).
 */
export function RetireGoverningStandardDialog({
  isOpen,
  onClose,
  organizationId,
  entry,
  onRetired,
}: RetireGoverningStandardDialogProps) {
  const [retirementDate, setRetirementDate] = useState('');
  const [rationale, setRationale] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setRetirementDate('');
    setRationale('');
    setSubmitError(null);
    setIdempotencyKey(crypto.randomUUID());
  }, [isOpen, entry]);

  if (!entry) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      const retirement = await retireGoverningStandard(
        organizationId,
        entry!.standard.id,
        { retirementDate: retirementDate || undefined, rationale: rationale.trim() || undefined },
        idempotencyKey,
      );
      onRetired(retirement);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError("You don't have permission to retire governing standards in this organization.");
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not retire this standard.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Retire governing standard">
      <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
        <p className="text-sm text-text-secondary">
          Retiring <span className="font-medium text-text-primary">{entry.standard.name}</span> records that this
          organization has withdrawn it as a governing standard. The prior selection remains in the history — this
          does not delete it.
        </p>
        <Input
          label="Retirement date"
          type="date"
          value={retirementDate}
          max={new Date().toISOString().slice(0, 10)}
          onChange={(event) => setRetirementDate(event.target.value)}
          helperText="Optional."
        />
        <Textarea
          label="Rationale"
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          maxLength={4000}
          helperText="Optional — why this standard is being retired, for the record."
        />

        {submitError && (
          <p role="alert" className="text-sm text-critical">
            {submitError}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" disabled={submitting}>
            {submitting ? 'Retiring…' : 'Retire standard'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
