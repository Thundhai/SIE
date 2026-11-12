# Adding users (administrator-added accounts)

Administration → **Add user** is how a person joins an organization. The administrator enters their email, an optional name and a role, then clicks **Add**.

SIE takes it from there:

| Situation | What SIE does | What the person does |
|---|---|---|
| New to SIE and to Auth0 | Creates their Auth0 account (random password nobody is told) and their SIE account, binds the two, adds the membership, and asks Auth0 to email a **set-password link** | Clicks the email link, sets a password, signs in |
| Already has a **verified** Auth0 account | Creates their SIE account bound to it and adds the membership. No email | Signs in with their existing password |
| Already has an SIE account | Adds the membership only | Signs in as usual |

The copy-a-link **Invitations** section is hidden. Set `VITE_INVITATIONS_ENABLED=true` on the frontend to show it again.

## Security model

- **Binding:** SIE binds `(OIDC_ISSUER, Auth0 user_id)` only to an Auth0 database account that Auth0 says has that email and either:
  - is **verified**, or
  - was **created by SIE** (`app_metadata.sie_provisioned`).

  A created account's password is unknown to everyone, so only whoever controls the mailbox can set one and sign in.
- **Unverified accounts SIE didn't create are refused** (`auth0_account_unverified`). Anyone can sign up with someone else's address. Switching off public sign-up (below) also closes this.
- **Reusing an existing SIE account** (adding it to another organization) requires the bound Auth0 account to have this email and be verified, or be created by SIE. Older accounts' stored emails came from unverified claims.
- **Never touched:** platform administrators. **Never changed:** an existing membership.
- **Role limit:** an administrator can't grant permissions they don't have.
- **Auth0 unreachable:** the request fails closed with a retryable 503, and nothing is written.
  - If the Auth0 account was created but the SIE write failed, a retry reuses that account (it is tagged as SIE's).
- **Audit:**
  - every addition: `MEMBER_ADDED` with `via: admin_added`, plus `IDENTITY_LINKED` for a new binding
  - every refusal: `USER_ADD_REJECTED`, with the reason code and never the email
- **Logs:** the Auth0 client secret, tokens, emails and Auth0 user ids never appear.

## API

Both routes need `users:manage` in the organization in the path.

| Action | Route |
|---|---|
| Add a person | `POST /api/v1/organizations/{org}/users` with `{email, role, name?}` |
| Resend the set-password email (SIE-created sign-ins only) | `POST /api/v1/organizations/{org}/users/{user_id}/password-email` |

Responses:
- `outcome`: `account_created`, `existing_sign_in` or `existing_sie_account`
- `email_sent` and `email_failed`
- refusals: `USER_ADD_REJECTED` with `details.reason`

## One-time setup (owner)

### 1. Auth0: machine-to-machine application
1. Go to Applications → Applications → **Create Application**.
2. Choose **Machine to Machine** and name it "SIE Backend".
3. Authorize it for the **Auth0 Management API** with only these scopes:
   - `read:users`
   - `create:users`

### 2. Auth0: switch off public sign-up
1. Go to Authentication → Database → **Username-Password-Authentication**.
2. Turn on **Disable Sign Ups**.

People then get accounts only through Add user.

### 3. Render: SIE service settings
| Key | Value |
|---|---|
| `AUTH0_MANAGEMENT_DOMAIN` | the tenant host, e.g. `<tenant>.us.auth0.com` (no `https://`) |
| `AUTH0_MANAGEMENT_CLIENT_ID` | the "SIE Backend" client id |
| `AUTH0_MANAGEMENT_CLIENT_SECRET` | the "SIE Backend" client secret (secret) |
| `AUTH0_PASSWORD_EMAIL_CLIENT_ID` | the **SPA's** client id (the same value as `VITE_OIDC_CLIENT_ID`) |

The service refuses to start if only some of these are set.

### 4. Before real customers: an email sender
Auth0's built-in email provider is for testing and sends only a few emails per hour.
1. Go to Branding → Email Provider and connect one, for example SendGrid, Mailgun or Resend.
2. Optionally adjust Branding → Email Templates → **Change Password** wording, e.g. "Set your SIE password".

## Limits
- **Database connection only.** People are added there. A person who signs in with Google instead gets a different Auth0 account, which SIE refuses. They should use the emailed link and password.
- **No removal yet.** There is still no endpoint to remove a member.
