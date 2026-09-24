import { type FormEvent, useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { ApiError } from '../../services/api/errors';
import { createApiClient, type ApiClientCreated } from '../../services/api/administration';
import { PERMISSION_SCOPE_OPTIONS } from './administrationLabels';

export interface CreateApiClientDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  onCreated: (client: ApiClientCreated) => void;
}

/**
 * "Create API client" — `POST /organizations/{organization_id}/api-clients`.
 * The response secret is handed to the parent's `onCreated` purely to be
 * displayed once (see `ApiClientsSection`'s own secret-reveal panel);
 * this drawer itself never retains it after closing.
 */
export function CreateApiClientDrawer({ isOpen, onClose, organizationId, onCreated }: CreateApiClientDrawerProps) {
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<string[]>([]);
  const [expiresAt, setExpiresAt] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setName('');
    setScopes([]);
    setExpiresAt('');
    setValidationError(null);
    setSubmitError(null);
  }, [isOpen]);

  function toggleScope(value: string) {
    setScopes((current) => (current.includes(value) ? current.filter((scope) => scope !== value) : [...current, value]));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setValidationError('Client name is required.');
      return;
    }
    if (scopes.length === 0) {
      setValidationError('Choose at least one scope.');
      return;
    }
    setValidationError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const client = await createApiClient(organizationId, {
        name: name.trim(),
        scopes,
        expiresAt: expiresAt ? new Date(`${expiresAt}T00:00:00Z`).toISOString() : undefined,
      });
      onCreated(client);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError("You don't have permission to create API clients in this organization. Ask an administrator for users:manage access.");
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not create this API client.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Create API client">
      <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
        <Input label="Name" value={name} onChange={(event) => setName(event.target.value)} maxLength={255} required />

        <fieldset className="flex flex-col gap-1.5">
          <legend className="text-xs font-medium text-text-secondary">Scopes</legend>
          <div className="max-h-56 overflow-y-auto rounded-md border border-border-strong p-2">
            {PERMISSION_SCOPE_OPTIONS.map((option) => (
              <label key={option.value} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm text-text-primary hover:bg-surface-muted">
                <input
                  type="checkbox"
                  checked={scopes.includes(option.value)}
                  onChange={() => toggleScope(option.value)}
                  className="h-4 w-4 rounded border-border-strong"
                />
                {option.label}
              </label>
            ))}
          </div>
          <p className="text-xs text-text-muted">Each scope grants exactly one existing SIE permission — least privilege by default.</p>
        </fieldset>

        <Input
          label="Expires"
          type="date"
          value={expiresAt}
          min={new Date().toISOString().slice(0, 10)}
          onChange={(event) => setExpiresAt(event.target.value)}
          helperText="Optional — leave blank for a credential that does not expire."
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
            {submitting ? 'Creating…' : 'Create API client'}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
