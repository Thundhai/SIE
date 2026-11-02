import { FormEvent, useEffect, useId, useRef, useState } from 'react';
import { CheckCircle2, Link2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { ApiError } from '../services/api/errors';
import {
  ACCOUNT_LINK_CODE_MAX_LENGTH,
  ACCOUNT_LINK_CODE_PREFIX,
  redeemAccountLinkCode,
} from '../services/api/identityLinks';

type Phase = 'idle' | 'submitting' | 'linked';

/** Fixed, user-facing wording per outcome. The backend's own messages for
 * 403 and 409 are fixed SIE strings (never caller input, never the code),
 * so they are shown as given; everything else gets a message written here. */
export function redemptionErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'Could not link your account. Try again, or contact your administrator.';
  }
  if (error.isNetworkError) {
    return 'Could not reach SIE. Check your connection and try again.';
  }
  switch (error.status) {
    case 404:
      return 'This code is invalid, already used, or has expired. Ask your administrator for a new one.';
    case 422:
      return "That isn't a valid account-link code. Check it and try again.";
    case 401:
      return 'Your sign-in has expired. Sign in again, then enter the code.';
    case 429:
      return 'Too many attempts. Wait a minute, then try again.';
    case 403:
    case 409:
      return error.message || 'This code cannot be used with this sign-in. Contact your administrator.';
    default:
      return 'Could not link your account. Try again, or contact your administrator.';
  }
}

function looksLikeAccountLinkCode(code: string): boolean {
  return (
    code.startsWith(ACCOUNT_LINK_CODE_PREFIX) &&
    code.length > ACCOUNT_LINK_CODE_PREFIX.length &&
    code.length <= ACCOUNT_LINK_CODE_MAX_LENGTH &&
    !/\s/.test(code)
  );
}

/**
 * Shown by `ProductionSessionGate` when the identity provider signed the
 * person in but SIE refused the sign-in because it isn't linked to a SIE
 * account (403 from the session bootstrap). They enter the one-time
 * account-link code an administrator gave them; it is redeemed with their
 * own, live access token.
 *
 * The code is handled as a secret:
 * - typed or pasted into one field, with autofill, spell-check and
 *   autocorrect off, and never given a `name`, so the browser doesn't
 *   remember it
 * - sent only in the request body; never in the URL, history or storage
 * - kept only in component state, which is cleared the moment it is
 *   submitted
 * - never logged; the error messages never contain it
 */
export function AccountLinkRedemption({ onLinked, onSignOut }: { onLinked: () => void; onSignOut: () => void }) {
  const [code, setCode] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const fieldRef = useRef<HTMLInputElement>(null);
  const errorId = useId();

  useEffect(() => () => controllerRef.current?.abort(), []);

  // After a refusal, put the person back in the (re-enabled) field. The
  // message itself is announced by the alert region below.
  useEffect(() => {
    if (phase === 'idle' && error) fieldRef.current?.focus();
  }, [phase, error]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (phase !== 'idle') return;
    const candidate = code.trim();
    setCode('');
    if (!looksLikeAccountLinkCode(candidate)) {
      setError(`Account-link codes start with ${ACCOUNT_LINK_CODE_PREFIX}. Check the code and try again.`);
      return;
    }

    setError(null);
    setPhase('submitting');
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      await redeemAccountLinkCode(candidate, controller.signal);
      if (controller.signal.aborted) return;
      setPhase('linked');
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(redemptionErrorMessage(err));
      setPhase('idle');
    }
  }

  if (phase === 'linked') {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div
          role="status"
          className="flex w-full max-w-sm flex-col items-center gap-3 rounded-lg border border-border bg-surface py-10 text-center"
        >
          <CheckCircle2 className="h-5 w-5 text-success" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">Your account is linked</p>
          <p className="max-w-xs text-sm text-text-secondary">
            From now on, signing in with this account opens SIE directly.
          </p>
          <Button onClick={onLinked}>Continue to SIE</Button>
        </div>
      </div>
    );
  }

  const submitting = phase === 'submitting';
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6">
        <div className="mb-4 flex items-center gap-2">
          <Link2 className="h-5 w-5 text-text-secondary" aria-hidden="true" />
          <h1 className="text-base font-medium text-text-primary">Link your account</h1>
        </div>
        <p className="mb-4 text-sm text-text-secondary">
          You're signed in, but this sign-in isn't linked to a SIE account yet. If an administrator gave you an
          account-link code, enter it below. Codes work once and expire.
        </p>
        <form onSubmit={submit} noValidate className="flex flex-col gap-3">
          <Input
            ref={fieldRef}
            label="Account-link code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={ACCOUNT_LINK_CODE_MAX_LENGTH + 20}
            disabled={submitting}
            helperText="Paste the code exactly as you received it."
            className={error ? 'border-critical font-mono' : 'font-mono'}
            {...(error ? { 'aria-invalid': true, 'aria-describedby': errorId } : {})}
          />
          {/* Always present, so assistive technology announces each new
              message as it arrives, not only the first. */}
          <p id={errorId} role="alert" className="text-xs text-critical empty:hidden">
            {error ?? ''}
          </p>
          <Button type="submit" disabled={submitting || code.trim() === ''}>
            {submitting ? 'Linking…' : 'Link account'}
          </Button>
        </form>
        <p className="mt-4 text-xs text-text-muted">
          No code? Ask your administrator for an invitation or an account-link code.{' '}
          <button type="button" className="underline" onClick={onSignOut} disabled={submitting}>
            Use a different sign-in
          </button>
        </p>
      </div>
    </div>
  );
}
