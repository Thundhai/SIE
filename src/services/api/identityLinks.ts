/**
 * Account-link redemption — thin typed wrapper around
 * `POST /api/v1/auth/identity-links/redeem`
 * (`backend/app/api/v1/identity_links.py`).
 *
 * The person has signed in with the identity provider, but that sign-in
 * isn't bound to a SIE account yet. Redeeming a one-time code from an
 * administrator binds it. The request carries the caller's own Bearer
 * token (registered by `ProductionSessionGate`), and the code travels
 * only in the JSON body: never in the URL, so it can't reach browser
 * history, server access logs or a `Referer` header.
 */
import { apiRequest } from './client';

export interface AccountLinkRedeemed {
  user_id: string;
  kind: string;
  organization_id: string | null;
}

/** Codes are issued with this prefix (`identity_link_service.CODE_PREFIX`). */
export const ACCOUNT_LINK_CODE_PREFIX = 'sie_link_';
/** The backend accepts 10–200 characters (`schemas/identity_link.py`). */
export const ACCOUNT_LINK_CODE_MAX_LENGTH = 200;

export function redeemAccountLinkCode(code: string, signal?: AbortSignal): Promise<AccountLinkRedeemed> {
  return apiRequest<AccountLinkRedeemed>('/auth/identity-links/redeem', {
    method: 'POST',
    body: { code },
    signal,
  });
}
