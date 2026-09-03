/**
 * Pluggable production access-token source — SIE Milestone 20: Production
 * Authentication & Identity Foundation v0.1.
 *
 * Mirrors `devIdentity.ts`'s "one source of truth" shape: the API client
 * (`services/api/client.ts`) and a real production auth provider (see
 * `ProdAuthProvider.tsx`) both read/write through this one module, so
 * they can never disagree about what token a request should carry.
 *
 * Inert by default — no getter registered means no token, which means no
 * `Authorization` header is ever sent (the API client falls back to the
 * existing dev-identity header, exactly as it always has — see
 * `client.ts`'s own `buildHeaders()`). Nothing here imports or hardcodes
 * any specific identity provider's SDK: whatever production auth
 * mechanism a deployment eventually wires up supplies a plain function
 * here (`getAccessToken(): string | null`), not a provider-specific
 * object.
 */

export type AccessTokenGetter = () => string | null;

let currentTokenGetter: AccessTokenGetter | null = null;

/** Registers (or clears, with `null`) the function the API client calls
 * on every request to get the current production Bearer token. Call this
 * once, from a `ProdAuthProvider`-style component's own setup — never
 * from a page/feature component. */
export function setAccessTokenGetter(getter: AccessTokenGetter | null): void {
  currentTokenGetter = getter;
}

/** Read by `services/api/client.ts::buildHeaders()` on every request. */
export function getAccessToken(): string | null {
  return currentTokenGetter ? currentTokenGetter() : null;
}
