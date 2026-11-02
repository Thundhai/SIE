import { type ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { LoadingState } from '../components/ui/LoadingState';
import { ApiError } from '../services/api/errors';
import {
  acceptInvitation,
  inspectInvitation,
  invitationErrorReason,
  startInvitation,
  type AcceptedInvitation,
  type InvitationMethod,
  type PublicInvitation,
} from '../services/api/invitations';
import { getAuthMode } from './authMode';
import {
  clearPendingInvitation,
  INVITATION_COMPLETE_PATH,
  readPendingInvitation,
  readTokenFromHash,
  storePendingInvitation,
} from './invitationFlow';
import { useOidcSession } from './oidcSession';
import { persistActiveOrganizationId } from './organizationPersistence';

/**
 * Invitation-based registration (backend: app/api/v1/invitations.py).
 *
 *   /invite#token=…    InvitationLandingPage: what the invitation is for,
 *                      and the sign-in choices
 *   identity provider  email + password sign-up, or the organization's SSO
 *   /callback          returns here via `state.returnTo`
 *   /invite/complete   InvitationCompletePage: accept, then into the app
 *
 * Neither page is inside the signed-in app shell. Neither grants anything
 * by itself: the backend admits someone only with a verified email that
 * matches the invitation (new account), or with their already-linked
 * account (existing account).
 */

const ROLE_LABELS: Record<string, string> = {
  ORG_ADMIN: 'Organization administrator',
  HSE_MANAGER: 'HSE manager',
  HSE_ANALYST: 'HSE analyst',
  HSE_USER: 'HSE user',
  VIEWER: 'Viewer',
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4 py-8">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-sm sm:p-8">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-navy-800 text-sm font-bold text-white">
            SIE
          </div>
          <h1 className="text-lg font-semibold text-navy-900">{title}</h1>
        </div>
        {children}
      </div>
    </div>
  );
}

function Notice({ tone = 'neutral', children }: { tone?: 'neutral' | 'critical'; children: ReactNode }) {
  return (
    <p
      role={tone === 'critical' ? 'alert' : 'status'}
      className={'text-center text-sm ' + (tone === 'critical' ? 'text-critical' : 'text-text-secondary')}
    >
      {children}
    </p>
  );
}

/** The terminal screens: nothing to do here but contact the administrator. */
function ClosedInvitation({ reason }: { reason: string }) {
  const copy: Record<string, [string, string]> = {
    EXPIRED: ['This invitation has expired', 'Ask your administrator to send you a new invitation.'],
    invitation_expired: ['This invitation has expired', 'Ask your administrator to send you a new invitation.'],
    REVOKED: ['This invitation is no longer valid', 'It was withdrawn. Ask your administrator if you still need access.'],
    invitation_revoked: [
      'This invitation is no longer valid',
      'It was withdrawn. Ask your administrator if you still need access.',
    ],
    ACCEPTED: ['This invitation has already been used', 'Sign in to SIE to continue.'],
    invitation_already_used: ['This invitation has already been used', 'Sign in to SIE to continue.'],
    invitation_not_found: ['This invitation link is not valid', 'Check that you opened the full link, or ask for a new one.'],
  };
  const [title, body] = copy[reason] ?? ['This invitation cannot be used', 'Ask your administrator for help.'];
  return (
    <Card title={title}>
      <Notice>{body}</Notice>
      <div className="mt-6 text-center">
        <a href="/login" className="text-sm font-medium text-navy-800 underline-offset-2 hover:underline">
          Go to sign in
        </a>
      </div>
    </Card>
  );
}

function InvitationSummary({ invitation }: { invitation: PublicInvitation }) {
  return (
    <div className="mb-6 space-y-4">
      <p className="text-center text-sm text-text-secondary">
        You've been invited to join <span className="font-semibold text-text-primary">{invitation.organization_name}</span>{' '}
        as <span className="font-semibold text-text-primary">{roleLabel(invitation.role)}</span>.
      </p>
      <Input
        label="Invited email"
        value={invitation.invited_email}
        readOnly
        aria-readonly="true"
        helperText="Register or sign in with exactly this email address."
      />
    </div>
  );
}

function isOpen(status: string): boolean {
  return status === 'PENDING' || status === 'REGISTRATION_STARTED' || status === 'VERIFIED';
}

// --- /invite -------------------------------------------------------------------------

type LandingState =
  | { phase: 'loading' }
  | { phase: 'ready'; token: string; invitation: PublicInvitation }
  | { phase: 'closed'; reason: string }
  | { phase: 'error'; message: string };

export function InvitationLandingPage() {
  const oidc = useOidcSession();
  const [state, setState] = useState<LandingState>({ phase: 'loading' });
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const fromHash = readTokenFromHash(window.location.hash);
    if (fromHash) {
      storePendingInvitation(fromHash);
      // Take the code out of the address bar and history.
      window.history.replaceState(null, '', window.location.pathname);
    }
    const token = fromHash ?? readPendingInvitation();
    if (!token) {
      setState({ phase: 'closed', reason: 'invitation_not_found' });
      return;
    }
    const controller = new AbortController();
    inspectInvitation(token, controller.signal)
      .then((invitation) =>
        setState(isOpen(invitation.status) ? { phase: 'ready', token, invitation } : { phase: 'closed', reason: invitation.status }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const reason = invitationErrorReason(error);
        if (reason) {
          if (reason === 'invitation_not_found') clearPendingInvitation();
          setState({ phase: 'closed', reason });
        } else {
          setState({ phase: 'error', message: errorMessage(error) });
        }
      });
    return () => controller.abort();
  }, []);

  if (getAuthMode() === 'dev') {
    return (
      <Card title="Invitations need production sign-in">
        <Notice>This deployment runs in development mode, where invitations cannot be accepted.</Notice>
      </Card>
    );
  }
  if (state.phase === 'loading') {
    return (
      <Card title="Checking your invitation">
        <LoadingState label="Checking your invitation…" />
      </Card>
    );
  }
  if (state.phase === 'closed') return <ClosedInvitation reason={state.reason} />;
  if (state.phase === 'error') {
    return (
      <Card title="We couldn't check this invitation">
        <Notice tone="critical">{state.message}</Notice>
      </Card>
    );
  }

  const { token, invitation } = state;

  async function begin(method: InvitationMethod | 'existing') {
    setBusy(true);
    setActionError(null);
    try {
      if (method !== 'existing') await startInvitation(token, method);
      const promptCreate = method === 'password' && import.meta.env.VITE_OIDC_SIGNUP_PROMPT_CREATE === 'true';
      await oidc.signIn({
        login_hint: invitation.invited_email,
        state: { returnTo: INVITATION_COMPLETE_PATH },
        ...(promptCreate ? { prompt: 'create' } : {}),
      });
    } catch (error) {
      setBusy(false);
      setActionError(errorMessage(error));
    }
  }

  return (
    <Card title="Join the Safety Intelligence Engine">
      <InvitationSummary invitation={invitation} />
      <div className="flex flex-col gap-3">
        <Button type="button" variant="primary" className="w-full justify-center" disabled={busy} onClick={() => begin('password')}>
          Create an account with email and password
        </Button>
        <Button type="button" variant="secondary" className="w-full justify-center" disabled={busy} onClick={() => begin('sso')}>
          Continue with your organization's single sign-on
        </Button>
      </div>
      <div className="mt-6 border-t border-border pt-4 text-center">
        <p className="text-sm text-text-secondary">Already have an SIE account with this email?</p>
        <Button type="button" variant="ghost" className="mt-1" disabled={busy} onClick={() => begin('existing')}>
          Sign in to accept
        </Button>
      </div>
      {actionError && (
        <div className="mt-4">
          <Notice tone="critical">{actionError}</Notice>
        </div>
      )}
    </Card>
  );
}

// --- /invite/complete ----------------------------------------------------------------

type CompleteState =
  | { phase: 'loading' }
  | { phase: 'confirm'; token: string; invitation: PublicInvitation }
  | { phase: 'accepting' }
  | { phase: 'accepted'; result: AcceptedInvitation; organizationName: string }
  | { phase: 'refused'; reason: string; invitation: PublicInvitation | null }
  | { phase: 'closed'; reason: string }
  | { phase: 'error'; message: string };

const CLOSED_REASONS = new Set(['invitation_expired', 'invitation_revoked', 'invitation_already_used', 'invitation_not_found']);

export function InvitationCompletePage() {
  const oidc = useOidcSession();
  const navigate = useNavigate();
  const [state, setState] = useState<CompleteState>({ phase: 'loading' });
  const [fullName, setFullName] = useState('');

  useEffect(() => {
    if (oidc.status !== 'authenticated') return;
    const token = readPendingInvitation();
    if (!token) {
      setState({ phase: 'closed', reason: 'invitation_not_found' });
      return;
    }
    const profileName = oidc.user?.profile?.name;
    if (typeof profileName === 'string') setFullName(profileName);
    inspectInvitation(token)
      .then((invitation) =>
        setState(isOpen(invitation.status) ? { phase: 'confirm', token, invitation } : { phase: 'closed', reason: invitation.status }),
      )
      .catch((error: unknown) => {
        const reason = invitationErrorReason(error);
        setState(reason ? { phase: 'closed', reason } : { phase: 'error', message: errorMessage(error) });
      });
  }, [oidc.status, oidc.user]);

  if (oidc.status === 'loading') {
    return (
      <Card title="Finishing sign-in">
        <LoadingState label="Checking your session…" />
      </Card>
    );
  }
  if (oidc.status !== 'authenticated') {
    return (
      <Card title="Sign in to accept your invitation">
        <Button
          type="button"
          variant="primary"
          className="w-full justify-center"
          onClick={() => oidc.signIn({ state: { returnTo: INVITATION_COMPLETE_PATH } })}
        >
          Sign in
        </Button>
      </Card>
    );
  }

  async function signInAgain(invitation: PublicInvitation | null, differentAccount: boolean) {
    if (differentAccount) await oidc.signOutLocally();
    await oidc.signIn({
      prompt: 'login',
      ...(invitation ? { login_hint: invitation.invited_email } : {}),
      state: { returnTo: INVITATION_COMPLETE_PATH },
    });
  }

  async function accept(token: string, invitation: PublicInvitation) {
    const accessToken = oidc.getAccessTokenLive();
    if (!accessToken) {
      await signInAgain(invitation, false);
      return;
    }
    setState({ phase: 'accepting' });
    try {
      const result = await acceptInvitation(token, accessToken, fullName.trim() || undefined);
      clearPendingInvitation();
      persistActiveOrganizationId(result.organization_id);
      setState({ phase: 'accepted', result, organizationName: invitation.organization_name });
    } catch (error) {
      const reason = invitationErrorReason(error);
      if (reason && CLOSED_REASONS.has(reason)) {
        clearPendingInvitation();
        setState({ phase: 'closed', reason });
      } else if (reason) {
        setState({ phase: 'refused', reason, invitation });
      } else {
        setState({ phase: 'error', message: errorMessage(error) });
      }
    }
  }

  switch (state.phase) {
    case 'loading':
    case 'accepting':
      return (
        <Card title={state.phase === 'loading' ? 'Checking your invitation' : 'Joining your organization'}>
          <LoadingState label={state.phase === 'loading' ? 'Checking your invitation…' : 'Activating your membership…'} />
        </Card>
      );
    case 'closed':
      return <ClosedInvitation reason={state.reason} />;
    case 'error':
      return (
        <Card title="Something went wrong">
          <Notice tone="critical">{state.message}</Notice>
        </Card>
      );
    case 'accepted':
      return (
        <Card title="You're in">
          <Notice>
            You've joined <span className="font-semibold text-text-primary">{state.organizationName}</span> as{' '}
            <span className="font-semibold text-text-primary">{roleLabel(state.result.role)}</span>.
          </Notice>
          <Button type="button" variant="primary" className="mt-6 w-full justify-center" onClick={() => navigate('/', { replace: true })}>
            Go to your dashboard
          </Button>
        </Card>
      );
    case 'refused':
      return <RefusedInvitation reason={state.reason} onSignInAgain={(different) => signInAgain(state.invitation, different)} />;
    case 'confirm': {
      const { token, invitation } = state;
      return (
        <Card title="Accept your invitation">
          <InvitationSummary invitation={invitation} />
          <Input label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={255} autoComplete="name" />
          <Button type="button" variant="primary" className="mt-6 w-full justify-center" onClick={() => accept(token, invitation)}>
            Join {invitation.organization_name}
          </Button>
        </Card>
      );
    }
  }
}

function RefusedInvitation({ reason, onSignInAgain }: { reason: string; onSignInAgain: (differentAccount: boolean) => void }) {
  switch (reason) {
    case 'email_not_verified':
      return (
        <Card title="Verify your email address">
          <Notice>
            Your sign-in provider has not confirmed your email address yet. Open the verification email it sent you, then sign in
            again here.
          </Notice>
          <Button type="button" variant="primary" className="mt-6 w-full justify-center" onClick={() => onSignInAgain(false)}>
            I've verified my email — sign in again
          </Button>
        </Card>
      );
    case 'email_mismatch':
      return (
        <Card title="This invitation is for a different email">
          <Notice>You signed in with an email address that doesn't match the invitation. Sign in with the invited email instead.</Notice>
          <Button type="button" variant="primary" className="mt-6 w-full justify-center" onClick={() => onSignInAgain(true)}>
            Sign in with a different account
          </Button>
        </Card>
      );
    case 'existing_account_sign_in_required':
      return (
        <Card title="You already have an SIE account">
          <Notice>An SIE account already uses this email. Sign in with that account to accept the invitation.</Notice>
          <Button type="button" variant="primary" className="mt-6 w-full justify-center" onClick={() => onSignInAgain(true)}>
            Sign in with my existing account
          </Button>
        </Card>
      );
    case 'membership_exists':
      return (
        <Card title="You're already a member">
          <Notice>You already have a membership in this organization. Ask its administrator if your access needs changing.</Notice>
          <div className="mt-6 text-center">
            <a href="/" className="text-sm font-medium text-navy-800 underline-offset-2 hover:underline">
              Go to SIE
            </a>
          </div>
        </Card>
      );
    case 'account_inactive':
      return (
        <Card title="Your SIE account is not active">
          <Notice>Your account has been deactivated. Ask your administrator to reactivate it, then open the invitation again.</Notice>
        </Card>
      );
    case 'orphaned_identity_requires_account_link':
      return (
        <Card title="Your sign-in needs to be relinked">
          <Notice>
            This sign-in was linked to an SIE account that no longer matches it. Ask your administrator for an account-link
            code to restore access.
          </Notice>
        </Card>
      );
    case 'concurrent_conflict':
      return (
        <Card title="Please try again">
          <Notice>Your account changed while this invitation was being accepted. Sign in again to finish.</Notice>
          <Button type="button" variant="primary" className="mt-6 w-full justify-center" onClick={() => onSignInAgain(false)}>
            Sign in again
          </Button>
        </Card>
      );
    default:
      return (
        <Card title="Registration isn't available for this sign-in">
          <Notice>Your administrator needs to finish setting up sign-in for invitations. Please contact them.</Notice>
        </Card>
      );
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) return 'Too many attempts. Please wait a minute and try again.';
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.';
}
