import { type FormEvent, useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Textarea } from '../../components/ui/Textarea';
import { ApiError } from '../../services/api/errors';
import {
  selectGoverningStandard,
  type GoverningStandard,
  type OrganizationGoverningStandardEntry,
} from '../../services/api/administration';
import { standardTypeLabel } from './administrationLabels';

export interface SelectGoverningStandardDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  /** The one AVAILABLE catalogue entry this drawer is offering to
   * select — chosen from the "Available standards" list before this
   * drawer opens, so there is never any ambiguity about which standard
   * is being adopted. */
  standard: GoverningStandard | null;
  onSelected: (selection: OrganizationGoverningStandardEntry) => void;
}

/**
 * SELECTED — `POST /organization-governing-standards`. Selecting a
 * standard is a human governance decision, never inferred from mere
 * catalogue availability (M43A's own "Core principle": available does
 * not mean selected). This drawer records that decision; it makes no
 * claim about legal applicability and performs no AI-based reasoning.
 */
export function SelectGoverningStandardDrawer({
  isOpen,
  onClose,
  organizationId,
  standard,
  onSelected,
}: SelectGoverningStandardDrawerProps) {
  const [effectiveDate, setEffectiveDate] = useState('');
  const [rationale, setRationale] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setEffectiveDate('');
    setRationale('');
    setSubmitError(null);
    setIdempotencyKey(crypto.randomUUID());
  }, [isOpen, standard]);

  if (!standard) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      const selection = await selectGoverningStandard(
        organizationId,
        {
          standardId: standard!.id,
          effectiveDate: effectiveDate || undefined,
          rationale: rationale.trim() || undefined,
        },
        idempotencyKey,
      );
      onSelected(selection);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError("You don't have permission to select governing standards in this organization. Ask an administrator for standards:manage access.");
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not select this standard.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Select governing standard">
      <div className="flex flex-col gap-4">
        <section className="rounded-lg border border-border bg-surface-muted p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Standard being selected</p>
          <p className="mt-1.5 text-sm font-semibold text-text-primary">{standard.name}</p>
          <p className="mt-0.5 text-xs text-text-muted">
            {standard.issuing_organization} · {standardTypeLabel(standard.standard_type)}
            {standard.version ? ` · ${standard.version}` : ''}
          </p>
          <p className="mt-2 text-sm text-text-secondary">{standard.short_description}</p>
        </section>

        <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
          <p className="text-xs text-text-secondary">
            Selecting a standard records that this organization has explicitly adopted it as governing its
            operations. It does not determine legal applicability to any specific site, activity, or hazard.
          </p>
          <Input
            label="Effective date"
            type="date"
            value={effectiveDate}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(event) => setEffectiveDate(event.target.value)}
            helperText="Optional — when the organization considers this standard to take effect."
          />
          <Textarea
            label="Rationale"
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            maxLength={4000}
            helperText="Optional — why this standard was selected, for the record."
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
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Selecting…' : 'Select standard'}
            </Button>
          </div>
        </form>
      </div>
    </Drawer>
  );
}
