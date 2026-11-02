# Invitation-based registration

A new person can reach an organization only by this path:

1. An administrator sends them an invitation.
2. They register with the configured identity provider.
3. Their verified email matches the invitation.
4. Their membership is activated in one transaction.

An existing SIE user joins another organization the same way, by signing in with their **already-linked** account.

Built on the identity-linking foundation from PR #69: `(issuer, subject)` is the only identity key, unknown sign-ins are refused, and no email is ever matched automatically.

## Architecture

| Concern | Where |
|---|---|
| **Sign-in, passwords, email verification, MFA** | At the **identity provider**. SIE stores no passwords and sends no email. "Email and password" is the provider's own database connection. "Enterprise SSO" is the provider federating to the customer's directory (Entra, Okta, SAML, …). Both produce a token from the one configured issuer. |
| Token validation (signature, issuer, audience, expiry, `iat`, `sub`) | `app/services/oidc_verifier.py` (unchanged) |
| Where a verified email comes from | `app/services/verified_email.py`: the access token's `email` / `email_verified`, or, when `OIDC_USERINFO_URL` is set, the provider's standard UserInfo endpoint (its `sub` must match) |
| Invitation lifecycle and acceptance | `app/services/invitation_service.py` |
| Invitation rows | `identity_link_grants` (kind `INVITATION`), the same table as PR #69's account links. There is no second invitation system. |
| API | `app/api/v1/invitations.py` |
| Public rate limit | `app/api/deps_public_rate_limit.py` |
| Frontend | `src/auth/InvitationPages.tsx` (`/invite`, `/invite/complete`), `src/features/administration/InvitationsSection.tsx` |

**Both sign-in methods end in the same place:**
- one `User`
- one `Identity` keyed by `(issuer, subject)`
- one `OrganizationMembership` with the invited role

From there, the unchanged RBAC and tenant model applies.

## Lifecycle

```
PENDING ──start──▶ REGISTRATION_STARTED ──verified + matched──▶ VERIFIED ──membership──▶ ACCEPTED
   │                       │
   ├── expires_at passed ──┴──▶ EXPIRED   (derived on every read; persisted when touched)
   └── admin revoke / too many email mismatches ──▶ REVOKED
```

`VERIFIED` and `ACCEPTED` are written in the same transaction (`verified_at` and `redeemed_at` record both). A refusal because the email isn't verified yet leaves the invitation at `REGISTRATION_STARTED`.

## Registration sequence

```mermaid
sequenceDiagram
    actor Admin
    actor Invitee
    participant SPA as SIE frontend
    participant API as SIE backend
    participant IdP as Identity provider

    Admin->>API: POST /organizations/{org}/invitations {email, role, expires_in_hours}
    API-->>Admin: {invitation, code}  (code shown once, hash stored)
    Admin-->>Invitee: link  /invite#token=<code>  (trusted channel)
    Invitee->>SPA: open link (code in URL fragment, never sent to a server)
    SPA->>API: POST /invitations/inspect {token}
    API-->>SPA: org, role, invited email, status
    Invitee->>SPA: choose "email and password" or "SSO"
    SPA->>API: POST /invitations/start {token, method}  → REGISTRATION_STARTED
    SPA->>IdP: authorize (PKCE, login_hint=invited email, state.returnTo=/invite/complete)
    Invitee->>IdP: register / sign in, verify email
    IdP-->>SPA: /callback → /invite/complete
    SPA->>API: POST /auth/invitations/accept {token, full_name}  + Bearer access token
    API->>API: verify token; lock invitation + identity rows
    API->>IdP: (optional) GET userinfo  → email, email_verified
    API->>API: issuer trusted? email_verified true? email == invited?
    API->>API: create user + identity (new) OR use linked account (existing)
    API->>API: create ACTIVE membership; ACCEPTED; audit
    API-->>SPA: {organization_id, role, outcome}
    SPA->>SPA: select organization → dashboard
```

## Acceptance rules (`invitation_service.accept`)

The organization and role always come from the invitation, never the request. The accept body forbids extra fields, so a request that carries them gets a 422.

**New account.** The caller's `(issuer, subject)` is not linked yet. All of these must hold:
- The issuer is in `OIDC_EMAIL_LINKING_TRUSTED_ISSUERS`. Empty by default, so nothing is trusted.
- `email_verified` is the JSON boolean `true`.
- The email equals the invited email (case-insensitive).
- **No SIE user has that email.** If one does, acceptance is refused with `existing_account_sign_in_required`, and the person signs in with their existing linked account instead. A new identity never attaches to an existing account, including a platform administrator's.

**Existing account.** The caller's identity is already linked to an active user.
- That user's email must equal the invited email.
- Only a membership is added. No identity moves, other memberships are untouched, and if a membership in this organization already exists (any status) the invitation is refused (`membership_exists`), so roles are never overwritten.

**Refusals.**
- Every refusal is an `INVITATION_REJECTED` error with `details.reason`, and every refusal is audited.
- An email mismatch increments `failed_attempts`. At `INVITATION_MAX_FAILED_ATTEMPTS` (default 5) the invitation is revoked.

**Concurrency.**
- Acceptance locks the invitation row (`SELECT … FOR UPDATE`), the identity row and the existing user row.
- The unique constraints on `identities(issuer, subject)` and `users.email` catch anything a lock can't. A conflict becomes an audited 409 (`concurrent_conflict`), never a 500.
- A partial unique index allows one open invitation per (organization, email).

## API

All routes are under `/api/v1`. Errors use the standard envelope. Invitation refusals have `error.code = INVITATION_REJECTED` and `error.details.reason`.

| Method and path | Who | Body | Returns |
|---|---|---|---|
| `POST /organizations/{org}/invitations` | `users:manage` in `org`; role permissions ⊆ the inviter's | `{email, role, expires_in_hours?}` (1–720) | 201 `{invitation, code}`, `Cache-Control: no-store` |
| `GET /organizations/{org}/invitations[?status=]` | `users:manage` in `org` | — | `[Invitation]` (no code, no hash) |
| `GET /organizations/{org}/invitations/{id}` | `users:manage` in `org` | — | `Invitation` (status, email, role, creator, created, expiry; no code) |
| `POST /organizations/{org}/invitations/{id}/resend` | `users:manage` in `org` | `{expires_in_hours?}` | `{invitation, code}`. The old code stops working; `issue_count`+1 |
| `POST /organizations/{org}/invitations/{id}/revoke` | `users:manage` in `org` | — | `Invitation` |
| `POST /invitations/inspect` | anyone with the code; IP rate-limited | `{token}` | `{status, organization_id, organization_name, role, invited_email, expires_at, methods}` |
| `POST /invitations/start` | anyone with the code; IP rate-limited | `{token, method: "password"\|"sso"}` | same as inspect |
| `POST /auth/invitations/accept` | Bearer access token; IP rate-limited | `{token, full_name?}` | `{organization_id, user_id, role, outcome: "account_created"\|"existing_account"}` |

**Tenant isolation.** An invitation ID is looked up only together with the organization in the path. Another organization's invitation is a 404 through your own path, and a 403 through its path.

**Reason codes:**
- **Lookup:** `invitation_not_found`, `invitation_expired`, `invitation_revoked`, `invitation_already_used`
- **Email checks:** `issuer_not_trusted_for_email`, `email_claim_missing`, `email_not_verified`, `email_mismatch`
- **Existing accounts:** `existing_account_sign_in_required`, `account_inactive`, `membership_exists`, `orphaned_identity_requires_account_link`
- **Concurrency:** `concurrent_conflict`
- **Creation:** `role_exceeds_authority`, `already_member`, `open_invitation_exists`

**PR #69's redeem route.** `/auth/identity-links/redeem` refuses invitation codes (`invitation_requires_acceptance`), so the email checks above can't be bypassed.

## Database: migration 0038

Adds to `identity_link_grants`:
- `status` (CHECK: the six states)
- `registration_started_at`, `verified_at`, `revoked_at`
- `revoked_by_user_id` (FK users, SET NULL)
- `accepted_membership_id` (FK organization_memberships, SET NULL)
- `issue_count`, `failed_attempts`

Indexes:
- **Partial unique index:** `uq_identity_link_grants_open_invitation` on `(organization_id, invited_email)`, where the invitation is open.
- `ix_identity_link_grants_org_status` on `(organization_id, status)`.

Upgrade and rollback:
- Additive. Existing redeemed rows become `ACCEPTED`.
- Downgrade drops these columns and indexes. That loses only lifecycle history, never a user, identity or membership.
- Depends on 0037 (PR #69).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OIDC_EMAIL_LINKING_TRUSTED_ISSUERS` | empty | Issuers whose `email_verified` SIE believes. **Required for new-user invitations.** Set it to the exact `OIDC_ISSUER` only after confirming the provider verifies email before setting `email_verified=true`. |
| `OIDC_USERINFO_URL` | unset | Read email from UserInfo instead of the access token (for providers that keep it out of access tokens). |
| `IDENTITY_LINK_GRANT_TTL_HOURS` | 72 | Default invitation lifetime. |
| `INVITATION_MAX_FAILED_ATTEMPTS` | 5 | Email mismatches before auto-revoke. |
| `INVITATION_RATE_LIMIT_PER_MINUTE` | 20 | Per client IP, on inspect, start and accept. Always on. |
| `TRUSTED_PROXY_HOPS` | 0 | Set to `1` on Render so the limit is per real client, not per proxy. |
| `VITE_OIDC_SIGNUP_PROMPT_CREATE` (frontend) | unset | `true` sends OIDC `prompt=create` for the email and password option. |

**Identity-provider setup** (owner, outside this repo):
- Enable an email and password connection that **requires email verification**.
- Make `email` and `email_verified` available, in the access token or via UserInfo.
- Add the SPA's `/callback` as the redirect URI.
- Connect enterprise directories through the same provider.

## Threat assessment

| Threat | Control |
|---|---|
| Account takeover via an unverified or edited email | Email counts only with `email_verified=true` from an explicitly trusted issuer, **plus** possession of the invitation code. A new identity never attaches to an existing account. |
| Existing account hijack through an invitation | Existing accounts accept only through their already-linked identity, and their own email must match. |
| Code theft from logs or Referer | The code travels in the URL fragment and request bodies, never a query string. `no-store` is set. Only the SHA-256 hash is stored; the code is shown once and never audited. |
| Code guessing | 256-bit codes; per-IP limit on all invitation endpoints (with `Retry-After`); auto-revoke after repeated mismatches. |
| Replay or reuse | Single use under a row lock. Resend replaces the hash. Expiry and revocation are checked on every use. |
| Role or organization tampering | The organization and role come only from the invitation (the body forbids extra fields). An inviter can't grant permissions they lack. |
| Cross-tenant access | Every administrator route needs `users:manage` in the path's organization, and invitation lookups are scoped to it. |
| Duplicate accounts | Case-insensitive email check, lower-cased storage, the `users.email` unique constraint, and one open invitation per organization and email. |
| Concurrent redemption | Row locks plus unique constraints; conflicts become audited 409s. Postgres race tests force each interleaving. |
| Platform-administrator protection | Unchanged from PR #69. Invitations can't link a new identity to any existing account. |
| Open redirect after sign-in | `/callback` follows `state.returnTo` only for same-origin absolute paths. |
| Audit | `INVITATION_CREATED`, `_RESENT`, `_REVOKED`, `_REGISTRATION_STARTED`, `_ACCEPTED`, `_REJECTED`, plus `IDENTITY_LINKED` and `MEMBER_ADDED`. All are org-scoped and carry no codes, tokens, emails or subjects. |

## Security assessment: the 18 required areas

| # | Area | Assessment |
|---|---|---|
| 1 | Authentication bypass | Accept needs a valid Bearer access token, verified as everywhere else (signature, `iss`, `aud`, `exp`, `iat`, `sub`). The dev header and machine credentials are refused. Inspect and start grant nothing. |
| 2 | Identity spoofing | `(issuer, subject)` from the verified token is the only identity key. The body carries no identity. |
| 3 | Unverified email claims | Only `email_verified` as the JSON boolean `true`, from an issuer explicitly listed in `OIDC_EMAIL_LINKING_TRUSTED_ISSUERS`, counts. If UserInfo is used, its `sub` must equal the token's. |
| 4 | Invitation token theft | 256-bit code, only in the URL fragment and request bodies, so it never reaches server logs or the Referer header. `no-store`. Hashed at rest, shown once, never audited. Possession alone isn't enough: a verified matching email or the linked account is also required. |
| 5 | Replay | Single use under a row lock. Resend replaces the hash. Expiry and revocation are checked on every use. |
| 6 | Brute force | Per-IP limit on inspect, start and accept (`Retry-After`); 256-bit search space; auto-revoke after `INVITATION_MAX_FAILED_ATTEMPTS` mismatches. |
| 7 | Cross-tenant access | Administrator routes need `users:manage` in the path's organization; invitation IDs are only looked up together with that organization. |
| 8 | Privilege escalation | An inviter can grant only roles whose permissions they hold. `platform_role` is never touched. |
| 9 | Role manipulation | The role comes only from the invitation; the accept body forbids extra fields (422). |
| 10 | Duplicate accounts | Case-insensitive email check, the `users.email` unique constraint, lower-cased invitations, and one open invitation per organization and email. |
| 11 | Concurrent acceptance | Invitation, identity and user rows locked; unique constraints as backstop; conflicts become audited 409s (Postgres race tests). |
| 12 | Membership manipulation | Acceptance only adds a membership. It never changes or overwrites one (`membership_exists`). |
| 13 | Platform administrators | A new identity can't attach to any existing account, including admins. PR #69's operator-only admin linking is unchanged. |
| 14 | Audit integrity | The audit row is written in the same transaction as the change it records. Refusals are committed separately, so they survive the rollback. |
| 15 | Sensitive data exposure | No code, hash, token, email or subject in audit metadata or logs. The code appears only in the one-time creation or resend response. |
| 16 | Rate-limit bypass | The client IP is the socket peer, or the X-Forwarded-For entry `TRUSTED_PROXY_HOPS` from the right, so a client-supplied header can't change it. The limit is process-local (see limitations). |
| 17 | CSRF, redirects, sessions | Bearer tokens, not cookies, so no ambient credentials to forge. OIDC state and PKCE via `oidc-client-ts`. `/callback` follows only same-origin `state.returnTo` paths. The pending code is in tab-scoped `sessionStorage`. |
| 18 | Federation and issuer misconfiguration | One issuer (`OIDC_ISSUER`) is accepted. Email trust is a separate, exact-match allow-list that is empty by default. Users can't pick a provider: the SPA only talks to the configured authority. |

## Extensibility (multiple providers later)

Nothing here assumes a single provider:
- identities are keyed by `(issuer, subject)`
- invitations store no issuer
- email trust is a *set* of issuers

A later phase can add per-organization trusted issuers without changing this schema. Multi-provider trust is out of scope for this PR.

## Limitations

- **Locking the email at the provider:** SIE can only prefill it there (`login_hint`); the provider decides whether it is locked. SIE enforces the match on the backend.
- **No emails sent:** SIE sends no invitation email. The administrator copies the link, which is shown once.
- **Rate limiter is per instance:** it is process-local, which is exact on today's single Render instance but counts per instance if the service scales out.
- **Inactive until configured:** new-user invitations do nothing until `OIDC_EMAIL_LINKING_TRUSTED_ISSUERS` is set. Existing-account invitations work without it.
- **Other gaps:** an org admin can't yet see the audit trail in the UI, and there is no membership revocation API (audit finding N6).
