"""Where a caller's email and `email_verified` come from, for invitation
acceptance.

By default they come from the verified access token's own claims
(`ExternalIdentityClaims`). When `OIDC_USERINFO_URL` is set, they come
from the provider's standard OIDC UserInfo endpoint instead, called with
the caller's access token. Its `sub` must equal the token's, or the
response is ignored. Only a JSON boolean `email_verified` counts.

Whether the issuer is *trusted* to verify email is decided by the caller
(`OIDC_EMAIL_LINKING_TRUSTED_ISSUERS`), not here.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.services.identity_service import ExternalIdentityClaims

_USERINFO_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class VerifiedEmail:
    email: str | None
    email_verified: bool | None
    source: str  # "access_token" | "userinfo" | "userinfo_unavailable"


def _fetch_userinfo(url: str, access_token: str) -> dict | None:
    try:
        response = httpx.get(
            url, headers={"Authorization": f"Bearer {access_token}"}, timeout=_USERINFO_TIMEOUT_SECONDS
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def resolve_verified_email(claims: ExternalIdentityClaims, access_token: str) -> VerifiedEmail:
    url = settings.OIDC_USERINFO_URL
    if not url:
        return VerifiedEmail(claims.email, claims.email_verified, "access_token")
    body = _fetch_userinfo(url, access_token)
    if body is None or body.get("sub") != claims.subject:
        # Fail closed: nothing verified.
        return VerifiedEmail(None, None, "userinfo_unavailable")
    email = body.get("email")
    verified = body.get("email_verified")
    return VerifiedEmail(
        email if isinstance(email, str) and email else None,
        verified if isinstance(verified, bool) else None,
        "userinfo",
    )
