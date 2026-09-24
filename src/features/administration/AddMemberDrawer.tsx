import { type FormEvent, useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { ApiError } from '../../services/api/errors';
import { addMember, type MembershipStatus, type OrganizationRole } from '../../services/api/administration';
import type { OrganizationMembership } from '../../services/api/organizations';
import { MEMBERSHIP_STATUS_OPTIONS, ORGANIZATION_ROLE_OPTIONS } from './administrationLabels';

export interface AddMemberDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  onAdded: (membership: OrganizationMembership) => void;
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * "Add member" — `POST /organizations/{organization_id}/members`, gated
 * by `users:manage`. Names an *existing* user by id: the backend has no
 * self-registration/invitation flow and no `GET /users` endpoint to
 * resolve a name or email from (SIE Milestone 18's own documented
 * contract gap, unchanged here) — so this is deliberately a raw user-id
 * field, never a fabricated people-picker.
 */
export function AddMemberDrawer({ isOpen, onClose, organizationId, onAdded }: AddMemberDrawerProps) {
  const [userId, setUserId] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('ACTIVE');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setUserId('');
    setRole('');
    setStatus('ACTIVE');
    setValidationError(null);
    setSubmitError(null);
  }, [isOpen]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!UUID_PATTERN.test(userId.trim())) {
      setValidationError('Enter a valid existing user id (UUID).');
      return;
    }
    if (!role) {
      setValidationError('Choose a role.');
      return;
    }
    setValidationError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const membership = await addMember(organizationId, {
        userId: userId.trim(),
        role: role as OrganizationRole,
        status: status as MembershipStatus,
      });
      onAdded(membership);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError("You don't have permission to add members in this organization. Ask an administrator for users:manage access.");
      } else if (error instanceof ApiError && error.status === 404) {
        setSubmitError('No user exists with that id.');
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not add this member.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Add member">
      <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
        <Input
          label="User ID"
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          placeholder="00000000-0000-0000-0000-000000000000"
          helperText="The id of an existing SIE user — there is no name/email lookup available."
        />
        <Select
          label="Role"
          value={role}
          onChange={(event) => setRole(event.target.value)}
          options={[{ value: '', label: 'Choose a role' }, ...ORGANIZATION_ROLE_OPTIONS]}
        />
        <Select
          label="Status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          options={MEMBERSHIP_STATUS_OPTIONS}
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
            {submitting ? 'Adding…' : 'Add member'}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
