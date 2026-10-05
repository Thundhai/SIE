/**
 * Production OIDC client configuration — SIE Milestone G3-1: Login &
 * Production Session.
 *
 * Mirrors `devIdentity.ts`'s own shape exactly: one function, reading
 * plain Vite env vars, returning `null` when the deployment hasn't
 * configured them rather than throwing or guessing a default — the same
 * "honestly unconfigured, not fabricated" posture `getDevIdentityConfig()`
 * already established.
 *
 * Deliberately provider-neutral, mirroring the backend's own
 * `OIDC_ISSUER`/`OIDC_AUDIENCE`/`OIDC_JWKS_URL` settings
 * (`backend/app/core/config.py`) — nothing here imports or references
 * any specific identity provider's SDK. `authority` is the one value
 * every standards-compliant OIDC provider publishes a discovery document
 * at (`<authority>/.well-known/openid-configuration`); `oidc-client-ts`
 * (see `oidcSession.ts`) uses that document to discover every other
 * endpoint (authorization, token, end-session) rather than this
 * repository hardcoding a specific provider's URL shape.
 *
 * These are new environment variables — no equivalent existed anywhere
 * in this repository before G3-1 (confirmed: the backend's `OIDC_*`
 * settings configure token *verification*, a completely different
 * concern from a browser client's own authorization-code flow, and no
 * equivalent for a frontend OIDC client existed at all). Naming mirrors the
 * backend's own `OIDC_*` convention as closely as Vite's required
 * `VITE_` prefix allows.
 */

export interface OidcConfig {
  /** The provider's issuer URL, e.g. "https://login.example.com/tenant".
   * Used for discovery (`<authority>/.well-known/openid-configuration`)
   * — never a hardcoded per-provider endpoint shape. */
  authority: string;
  /** This SPA's public client id, as registered with the provider. No
   * client secret: a browser-based app is a public OAuth2 client by
   * definition, and `oidc-client-ts` uses Authorization Code + PKCE
   * (RFC 7636), which needs none. */
  clientId: string;
  /** Where the provider redirects back after sign-in. Defaults to
   * `<origin>/callback`, matching the `/callback` route this milestone
   * adds (see `router.tsx`) — overridable for a deployment whose
   * registered redirect URI differs. */
  redirectUri: string;
  /** Space-separated OIDC scopes. Defaults to the three every
   * standards-compliant provider recognizes; a deployment can widen
   * this if its provider requires a specific audience-granting scope,
   * but SIE itself never requires more than identity claims — the
   * backend's own authorization (role/permission) is entirely separate
   * from what this token's scopes request. */
  scope: string;
}

const DEFAULT_SCOPE = 'openid profile email';

export function getOidcConfig(): OidcConfig | null {
  const authority = import.meta.env.VITE_OIDC_AUTHORITY as string | undefined;
  const clientId = import.meta.env.VITE_OIDC_CLIENT_ID as string | undefined;

  // Both are required: an authority with no client id (or vice versa)
  // is a half-finished deployment configuration, not a usable one — see
  // this module's own docstring on failing honestly rather than guessing.
  if (!authority || !clientId) {
    return null;
  }

  const redirectUri =
    (import.meta.env.VITE_OIDC_REDIRECT_URI as string | undefined) ||
    (typeof window !== 'undefined' ? `${window.location.origin}/callback` : '');

  return {
    authority,
    clientId,
    redirectUri,
    scope: (import.meta.env.VITE_OIDC_SCOPE as string | undefined) || DEFAULT_SCOPE,
  };
}
