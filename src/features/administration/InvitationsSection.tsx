import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { roleLabel } from '../../auth/InvitationPages';
import { ADMINISTRATION_SECTION_PERMISSIONS } from '../../auth/routePermissions';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Input } from '../../components/ui/Input';
import { LoadingState } from '../../components/ui/LoadingState';
import { Select } from '../../components/ui/Select';
import { StatusBadge } from '../../components/ui/StatusBadge';
import {
  createInvitation,
  INVITABLE_ROLES,
  invitationLink,
  listInvitations,
  resendInvitation,
  revokeInvitation,
  type InvitableRole,
  type Invitation,
  type InvitationStatus,
  type IssuedInvitation,
} from '../../services/api/invitations';
import type { AsyncState, StatusTone } from '../../types/common';

/**
 * Administration → Invitations. Invite by email and role, see each
 * invitation's status, resend (a new link; the old one stops working)
 * or revoke. SIE sends no email: the link is shown once, right here, for
 * the administrator to pass on through a trusted channel.
 */

const STATUS_TONES: Record<InvitationStatus, StatusTone> = {
  PENDING: 'informational',
  REGISTRATION_STARTED: 'informational',
  VERIFIED: 'informational',
  ACCEPTED: 'success',
  EXPIRED: 'warning',
  REVOKED: 'neutral',
};

const STATUS_LABELS: Record<InvitationStatus, string> = {
  PENDING: 'Pending',
  REGISTRATION_STARTED: 'Registration started',
  VERIFIED: 'Verified',
  ACCEPTED: 'Accepted',
  EXPIRED: 'Expired',
  REVOKED: 'Revoked',
};

const EXPIRY_OPTIONS = [
  { value: '24', label: '24 hours' },
  { value: '72', label: '3 days' },
  { value: '168', label: '7 days' },
];

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '—';
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function InvitationsSection({ organizationId }: { organizationId: string }) {
  const auth = useAuth();
  const permitted = auth.hasPermission(ADMINISTRATION_SECTION_PERMISSIONS.invitations);
  const [state, setState] = useState<AsyncState<Invitation[]>>({ status: 'loading' });
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<InvitableRole>('VIEWER');
  const [expiry, setExpiry] = useState('72');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [issued, setIssued] = useState<IssuedInvitation | null>(null);
  const [copied, setCopied] = useState(false);
  const [rowBusy, setRowBusy] = useState<string | null>(null);

  const reload = useCallback(
    (signal?: AbortSignal) =>
      listInvitations(organizationId, signal)
        .then((rows) => setState({ status: 'success', data: rows }))
        .catch((error: unknown) => {
          if (signal?.aborted) return;
          setState({ status: 'error', message: errorText(error, 'Could not load invitations.') });
        }),
    [organizationId],
  );

  useEffect(() => {
    if (!permitted) return;
    const controller = new AbortController();
    setState({ status: 'loading' });
    void reload(controller.signal);
    return () => controller.abort();
  }, [permitted, reload]);

  if (!permitted) return null;

  function showIssued(result: IssuedInvitation) {
    setIssued(result);
    setCopied(false);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      showIssued(await createInvitation(organizationId, { email: email.trim(), role, expires_in_hours: Number(expiry) }));
      setEmail('');
      await reload();
    } catch (error) {
      setFormError(errorText(error, 'Could not create the invitation.'));
    } finally {
      setSubmitting(false);
    }
  }

  async function onRowAction(invitation: Invitation, action: 'resend' | 'revoke') {
    if (action === 'revoke' && !window.confirm(`Revoke the invitation for ${invitation.email}?`)) return;
    setRowBusy(invitation.id);
    setFormError(null);
    try {
      if (action === 'resend') showIssued(await resendInvitation(organizationId, invitation.id));
      else await revokeInvitation(organizationId, invitation.id);
      await reload();
    } catch (error) {
      setFormError(errorText(error, `Could not ${action} the invitation.`));
    } finally {
      setRowBusy(null);
    }
  }

  async function copyLink(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Section
      title="Invitations"
      description="Invite people by email. They register with email and password or your organization's single sign-on, and get access only after verifying the invited email."
    >
      <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end" aria-label="Invite a person">
        <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
        <Select
          label="Role"
          value={role}
          onChange={(e) => setRole(e.target.value as InvitableRole)}
          options={INVITABLE_ROLES.map((r) => ({ value: r, label: roleLabel(r) }))}
        />
        <Select label="Expires in" value={expiry} onChange={(e) => setExpiry(e.target.value)} options={EXPIRY_OPTIONS} />
        <Button type="submit" variant="primary" disabled={submitting || !email.trim()}>
          {submitting ? 'Inviting…' : 'Invite'}
        </Button>
      </form>

      {formError && (
        <p role="alert" className="mt-3 text-sm text-critical">
          {formError}
        </p>
      )}

      {issued && (
        <div role="status" className="mt-4 rounded-lg border border-border bg-surface-muted p-4">
          <p className="text-sm font-medium text-text-primary">Invitation link for {issued.invitation.email}</p>
          <p className="mt-1 text-xs text-text-secondary">
            Shown only once. Send it through a trusted channel. It expires {formatDate(issued.invitation.expires_at)}.
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <code className="block min-w-0 flex-1 break-all rounded bg-surface px-2 py-1 font-mono text-xs" data-testid="invitation-link">
              {invitationLink(issued.code)}
            </code>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" size="sm" onClick={() => copyLink(invitationLink(issued.code))}>
                {copied ? 'Copied' : 'Copy link'}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setIssued(null)}>
                Done
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="mt-6">
        {state.status === 'loading' && <LoadingState label="Loading invitations…" />}
        {state.status === 'error' && <ErrorState description={state.message} />}
        {state.status === 'success' &&
          (state.data.length === 0 ? (
            <EmptyState title="No invitations yet" description="Invitations you send appear here with their status." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                    {['Email', 'Role', 'Status', 'Expires', 'Actions'].map((h) => (
                      <th key={h} className="px-3 py-2">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {state.data.map((inv) => {
                    const closed = inv.status === 'ACCEPTED' || inv.status === 'REVOKED';
                    return (
                      <tr key={inv.id} className="border-b border-border">
                        <td className="px-3 py-3">{inv.email}</td>
                        <td className="px-3 py-3">{roleLabel(inv.role)}</td>
                        <td className="px-3 py-3">
                          <StatusBadge label={STATUS_LABELS[inv.status] ?? inv.status} tone={STATUS_TONES[inv.status] ?? 'neutral'} />
                        </td>
                        <td className="px-3 py-3">{inv.status === 'ACCEPTED' ? formatDate(inv.accepted_at) : formatDate(inv.expires_at)}</td>
                        <td className="px-3 py-3">
                          {!closed && (
                            <div className="flex gap-2">
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                disabled={rowBusy === inv.id}
                                onClick={() => onRowAction(inv, 'resend')}
                                aria-label={`Resend invitation to ${inv.email}`}
                              >
                                Resend
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="danger"
                                disabled={rowBusy === inv.id}
                                onClick={() => onRowAction(inv, 'revoke')}
                                aria-label={`Revoke invitation to ${inv.email}`}
                              >
                                Revoke
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
      </div>
    </Section>
  );
}
