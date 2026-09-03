# Production Authentication & Identity

**SIE Milestone 20: Production Authentication & Identity Foundation
v0.1.** Replaces the development-only human authentication seam with a
production-ready, provider-neutral authentication boundary, while
preserving every existing authorization, tenant isolation, and
permission decision this codebase already made. It does not redesign
`AuthorizationService`, `Permission`, role mappings, `TenantContext`,
machine-client authorization, or organization isolation — production
authentication *feeds* that existing pipeline; it does not replace or
duplicate it.

## What already existed before this milestone

`Identity` (`app/models/identity.py`), `IdentityResolverService`,
`TokenVerifier` (a `Protocol`), and `ExternalIdentityClaims`
(`app/services/identity_service.py`) were all built in an earlier
milestone as the seam a real verifier would plug into — but nothing
concrete implemented `TokenVerifier`, and nothing wired the resolver
into a live request path. `DevTokenVerifier` (the one implementation
that existed) performs no cryptography and is explicitly documented as
unsafe outside `DEV_MODE`.

## What this milestone adds

```
Authorization: Bearer <JWT>
    │
    ▼
OIDCTokenVerifier             app/services/oidc_verifier.py  (NEW)
    │  signature (JWKS + kid) / issuer / audience / expiry / nbf / subject
    │  via PyJWT — no hand-rolled cryptography
    ▼
ExternalIdentityClaims        app/services/identity_service.py  (UNCHANGED shape)
    │
    ▼
IdentityResolverService.resolve_or_create_user()   (UNCHANGED logic,
    │                                                now actually called)
    ▼
SIE User                      app/models/user.py
    │
    ▼
authorize_tenant_context()    app/services/tenant_context.py  (UNCHANGED)
    │
    ▼
TenantContext -> AuthorizationService -> existing routes  (UNCHANGED)
```

### 1. `app/services/oidc_verifier.py` — the real `TokenVerifier`

`OIDCTokenVerifier` validates, via PyJWT (`jwt.decode`, `jwt.PyJWKClient`
— an established library, not custom cryptography):

- **signature**, against a key resolved from the configured JWKS by the
  token's `kid` header (`JWKSKeyResolver` — a real `PyJWKClient` in
  production, `StaticJWKSKeyResolver` for tests or a deployment that
  prefers to pin keys rather than fetch them live)
- **issuer** (`iss`) — must equal the configured issuer exactly
- **audience** (`aud`) — must contain the configured audience
- **expiry** (`exp`) — required, must not have passed
- **not-before** (`nbf`) — checked automatically when present
- **subject** (`sub`) — required, non-empty

`get_oidc_verifier()` builds (and caches) the verifier from
`Settings` and raises `OIDCConfigurationError` — never a silent
pass-through — when `OIDC_ISSUER`, `OIDC_AUDIENCE`, or `OIDC_JWKS_URL`
is not configured.

**Provider-neutral by construction.** Nothing in this codebase imports
or references a specific identity provider's SDK. Any standards-compliant
OIDC/OAuth2 provider (Azure AD, Okta, Auth0, Google, a self-hosted
Keycloak, ...) is supported purely through configuration:

| Setting | Purpose |
|---|---|
| `OIDC_ISSUER` | Exact `iss` claim to require |
| `OIDC_AUDIENCE` | Exact `aud` to require |
| `OIDC_JWKS_URL` | The provider's JWKS endpoint |
| `OIDC_ALGORITHMS` | Comma-separated accepted JWS algorithms (default `RS256`) |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | JWKS key-set cache lifetime (default 3600s) |
| `OIDC_PROVIDER_LABEL` | Display label recorded on `Identity.provider` (e.g. `"azuread"`) |

### 2. Request routing — `app/api/deps_auth.py`, `app/api/deps_context.py`

A request's `Authorization: Bearer <credential>` is disambiguated by
shape, not by a new header or endpoint:

- contains a `:` → the existing machine `<client_id>:<secret>` credential
  (`app/api/deps_machine_auth.py`) — **completely unchanged**.
- no `:` (a JWT's base64url segments never contain one) → routed to
  `get_production_authenticated_user_id()`, the new production path.
- no `Authorization` header at all → the existing `DEV_MODE`-gated
  dev-header mechanism (`get_dev_authenticated_user_id`) —
  **completely unchanged** — or, once OIDC is configured, a clear 401
  "missing token" rather than 501.

`get_authenticated_user_id()` is the one dispatcher every human-only
route depends on (directly, or via `get_tenant_context`). It never falls
back from production authentication to the development mechanism, or the
reverse — satisfying "no insecure fallback to development authentication
when `DEV_MODE=false`" by construction: a Bearer JWT is either verified
for real or rejected, full stop.

### 3. Identity resolution — `app/services/identity_service.py`

Unchanged logic, two additions:

- `Identity.last_authenticated_at` is now actually set on every resolve
  (it existed on the model since the earlier milestone but was never
  written).
- A brand-new `Identity` (a genuinely new external identity, whether or
  not it links to a pre-existing `User` by email) is now logged as
  `AuditAction.IDENTITY_PROVISIONED`.

The `(issuer, subject)` identity key — never email — remains exactly as
it was: email/display name stay profile attributes on `Identity`,
synced on every resolve, never the primary key.

### 4. "Inactive identity" — reusing `User.status`, no new column

Rather than adding a new `is_active`/`revoked_at` column to `Identity`
(explicitly out of scope: "no new database ontology"), a resolved
identity whose `User.status != "active"` is rejected (401), reusing the
`status` field that already existed on `User`. `OrganizationMembership`
status (ACTIVE/SUSPENDED/INVITED/REVOKED) already governs per-organization
access via the unchanged `authorize_tenant_context()`/
`AuthorizationService` pipeline — this is the identity-level analogue.

### 5. `GET /api/v1/auth/me` and `GET /api/v1/auth/organizations`

`/auth/me` is extended (not redesigned) with two fields, computed from
non-secret data only:

- `auth_mode`: `"dev"` or `"production"` — which mechanism resolved this
  request.
- `identity_provider`: the `Identity.provider` label of the most
  recently authenticated production identity linked to this user, or
  `null` for a dev-mode identity. Never an issuer, subject, or token.

`GET /api/v1/auth/organizations` (new) lists the authenticated identity's
active organization memberships — the mechanism for requirement #3's
"if a user belongs to multiple organizations, the architecture must
explicitly handle organization selection rather than silently choosing
one." The client must still always name an organization explicitly via
the existing required `organization_id` query parameter on every
tenant-scoped route (unchanged); this endpoint only lets a client
discover *which* organizations are valid choices before making that
call, rather than guessing or defaulting to one.

### 6. Frontend — `src/auth/authToken.ts`, `src/auth/ProdAuthProvider.tsx`

- `authToken.ts` — a pluggable, provider-neutral access-token source
  (`setAccessTokenGetter()`/`getAccessToken()`), read by
  `services/api/client.ts` on every request: a registered production
  token takes priority over the existing dev-identity header, never
  both at once.
- `ProdAuthProvider.tsx` — implements the exact same `AuthContextValue`
  interface `DevAuthProvider` does. Takes a `getAccessToken` function and
  an already-selected `organizationId` as props (never picks an
  organization itself); resolves `GET /auth/me` + `GET
  /auth/organizations` for the real, backend-authoritative
  user/organization/role/permissions. Any failure (no token, an
  unauthenticated/401 response, a network error) resolves to the same
  clean `NOT_AUTHENTICATED` state `DevAuthProvider` already falls back
  to — never a raw `ApiError` surfacing as a generic app error.

Not wired into `App.tsx` by default: a concrete token source (a real
login flow for a specific provider) is external infrastructure this
milestone does not build — see "Explicitly not in this milestone" below.
Swapping `DevAuthProvider` for `ProdAuthProvider` touches exactly one
file and zero screens/routes/repositories.

### 7. Auditability — `app/services/audit_service.py`

Three new `AuditAction` values:

- `AUTH_SUCCEEDED` — a production token verified and resolved to an
  active identity.
- `AUTH_REJECTED` — any verification/resolution failure (bad signature,
  expired, wrong issuer/audience, missing subject, malformed, unknown
  `kid`, inactive identity). Metadata carries a fixed, human-readable
  reason string — never the token, a header value, or exception
  internals that could carry one.
- `IDENTITY_PROVISIONED` — a new `Identity` row was created.

## Explicitly not in this milestone

Google/Microsoft/Okta-specific UI, password authentication, SSO
administration UI, MFA, SCIM, a user-provisioning portal, social login,
session-management redesign, RBAC redesign, new permissions, new
database ontology beyond what's described above, and a concrete
production login flow (which provider, redirect handling, token refresh)
— `ProdAuthProvider` is the seam that flow plugs into, not the flow
itself.

## Tests

- `backend/tests/test_oidc_verifier.py` — unit tests against
  `OIDCTokenVerifier` directly: valid token, expired, invalid signature,
  wrong issuer, wrong audience, missing subject, malformed token, empty
  token, unknown/missing key id, missing `exp`, `nbf` in the future/past,
  wrong algorithm, and `get_oidc_verifier()`'s fail-closed configuration
  gate. Uses a real, locally generated RSA keypair
  (`tests/oidc_test_helpers.py`) — genuine PyJWT signature verification,
  no live identity provider or network access.
- `backend/tests/test_production_auth.py` — HTTP-layer tests through the
  real FastAPI app: every token-validation case above at the `/auth/me`
  boundary; identity cases (known, unknown/auto-provisioned, inactive,
  one organization, multiple organizations); authorization cases
  (permitted, denied, cross-tenant, inactive membership, organization
  mismatch, platform admin); audit-log assertions (success/rejection
  logged, token never appears in metadata); and a regression check that
  a production human token and a machine `client_id:secret` credential
  both work correctly, unconfused, on the same dual-mode route.
- Existing suites (`test_auth_me_api.py`, `test_dev_mode_gate.py`,
  `test_identity_resolution.py`, `test_machine_client_security.py`,
  `test_authorization.py`, and the full backend/frontend suites) continue
  passing unchanged — see the milestone's own completion report for the
  exact numbers.
