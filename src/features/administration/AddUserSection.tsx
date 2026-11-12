import { type FormEvent, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { roleLabel } from '../../auth/InvitationPages';
import { ADMINISTRATION_SECTION_PERMISSIONS } from '../../auth/routePermissions';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { INVITABLE_ROLES, type InvitableRole } from '../../services/api/invitations';
import { addUser, addUserErrorReason, resendPasswordEmail, type AddedUser } from '../../services/api/users';

/**
 * Administration → Add user. The administrator enters email, name and
 * role. SIE creates (or finds) the person's sign-in and adds them; when it
 * creates one, the sign-in provider emails them a set-password link. No
 * links to copy, nothing to forward.
 */

/** What to tell the administrator for each refusal (`details.reason`). */
const REFUSALS: Record<string, string> = {
  already_member: 'This person is already a member of this organization.',
  role_exceeds_authority: "You can't give someone a role with permissions you don't have.",
  auth0_account_unverified:
    'Someone already signed up with this email but never verified it. Ask them to verify their email, or delete that sign-in in Auth0, then try again.',
  existing_account_unverified: "This person's existing sign-in hasn't verified this email address yet.",
  existing_account_unlinked: 'An SIE account with this email exists but has no sign-in. Ask a platform administrator.',
  platform_admin_account: "A platform administrator's account can't be added here.",
  account_inactive: "This person's SIE account is not active.",
  ambiguous_email: 'More than one SIE account has this email. Ask a platform administrator.',
  orphaned_identity: "This person's sign-in needs to be relinked. Ask a platform administrator.",
  concurrent_conflict: 'Someone added this person at the same moment. Refresh and check the member list.',
  not_configured: "Adding users isn't set up on this deployment yet.",
  auth0_unavailable: "The sign-in service couldn't be reached. Nothing was changed. Try again in a moment.",
};

function refusalText(error: unknown): string {
  const reason = addUserErrorReason(error);
  if (reason && REFUSALS[reason]) return REFUSALS[reason];
  return error instanceof Error ? error.message : 'Could not add this person.';
}

interface Result {
  email: string;
  added: AddedUser;
}

export function AddUserSection({ organizationId, onAdded }: { organizationId: string; onAdded?: () => void }) {
  const auth = useAuth();
  const permitted = auth.hasPermission(ADMINISTRATION_SECTION_PERMISSIONS.addUser);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState<InvitableRole>('VIEWER');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [resending, setResending] = useState(false);

  if (!permitted) return null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = email.trim();
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const added = await addUser(organizationId, { email: trimmed, role, ...(name.trim() ? { name: name.trim() } : {}) });
      setResult({ email: trimmed, added });
      setEmail('');
      setName('');
      onAdded?.();
    } catch (caught) {
      setError(refusalText(caught));
    } finally {
      setSubmitting(false);
    }
  }

  async function onResend() {
    if (!result) return;
    setResending(true);
    setError(null);
    try {
      await resendPasswordEmail(organizationId, result.added.user_id);
      setResult({ ...result, added: { ...result.added, email_sent: true, email_failed: false } });
    } catch (caught) {
      setError(refusalText(caught));
    } finally {
      setResending(false);
    }
  }

  return (
    <Section
      title="Add user"
      description={`Add a person to ${auth.organization?.name ?? 'this organization'}. If they're new, they get an email to set their password, then sign in here.`}
    >
      <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-[2fr_2fr_1fr_auto] sm:items-end" aria-label="Add a user">
        <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
        <Input label="Full name (optional)" value={name} maxLength={255} onChange={(e) => setName(e.target.value)} autoComplete="off" />
        <Select
          label="Role"
          value={role}
          onChange={(e) => setRole(e.target.value as InvitableRole)}
          options={INVITABLE_ROLES.map((r) => ({ value: r, label: roleLabel(r) }))}
        />
        <Button type="submit" variant="primary" disabled={submitting || resending || !email.trim()}>
          {submitting ? 'Adding…' : 'Add'}
        </Button>
      </form>

      {error && (
        <p role="alert" className="mt-3 text-sm text-critical">
          {error}
        </p>
      )}

      {result && (
        <div role="status" className="mt-4 rounded-lg border border-border bg-surface-muted p-4 text-sm">
          <p className="font-medium text-text-primary">
            {result.email} was added as {roleLabel(result.added.role)}.
          </p>
          {result.added.outcome === 'account_created' && result.added.email_sent && (
            <p className="mt-1 text-text-secondary">
              We emailed them a link to set their password. After that they sign in at {window.location.origin}.
            </p>
          )}
          {result.added.outcome === 'account_created' && result.added.email_failed && (
            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
              <p className="text-text-secondary">The set-password email couldn't be sent.</p>
              <Button type="button" size="sm" variant="secondary" disabled={resending} onClick={onResend}>
                {resending ? 'Sending…' : 'Send email again'}
              </Button>
            </div>
          )}
          {result.added.outcome !== 'account_created' && (
            <p className="mt-1 text-text-secondary">They already have a sign-in, so they can sign in now.</p>
          )}
        </div>
      )}
    </Section>
  );
}
