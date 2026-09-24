import { type FormEvent, useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { ApiError } from '../../services/api/errors';
import { createSite, type Site } from '../../services/api/sites';

export interface CreateSiteDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  onCreated: (site: Site) => void;
}

/**
 * "Create site" — the one write operation `POST
 * /organizations/{organization_id}/sites` supports. No edit/delete
 * control exists here or anywhere else, because the backend offers
 * neither (`backend/app/api/v1/sites.py` has only `POST`/`GET`).
 */
export function CreateSiteDrawer({ isOpen, onClose, organizationId, onCreated }: CreateSiteDrawerProps) {
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [country, setCountry] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setName('');
    setLocation('');
    setCountry('');
    setValidationError(null);
    setSubmitError(null);
  }, [isOpen]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setValidationError('Site name is required.');
      return;
    }
    setValidationError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const site = await createSite(organizationId, {
        name: name.trim(),
        location: location.trim() || undefined,
        country: country.trim() || undefined,
      });
      onCreated(site);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError("You don't have permission to create sites in this organization.");
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not create this site.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Create site">
      <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
        <Input
          label="Site name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={255}
          required
        />
        <Input
          label="Location"
          value={location}
          onChange={(event) => setLocation(event.target.value)}
          maxLength={255}
          helperText="Optional."
        />
        <Input
          label="Country"
          value={country}
          onChange={(event) => setCountry(event.target.value)}
          maxLength={255}
          helperText="Optional."
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
            {submitting ? 'Creating…' : 'Create site'}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
