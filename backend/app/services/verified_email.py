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


#: `VerifiedEmail.source` values.
SOURCE_ACCESS_TOKEN = "access_token"
SOURCE_USERINFO = "userinfo"
#: The UserInfo endpoint could not be reached or gave no usable answer
#: (network error, timeout, non-200, not a JSON object). Retryable.
SOURCE_USERINFO_UNAVAILABLE = "userinfo_unavailable"
#: UserInfo answered for a different subject. Not retryable.
SOURCE_USERINFO_SUBJECT_MISMATCH = "userinfo_subject_mismatch"
#: OIDC_USERINFO_URL is not https:// on a deployment; the token was not sent.
SOURCE_USERINFO_INSECURE = "userinfo_insecure"


@dataclass(frozen=True)
class VerifiedEmail:
    email: str | None
    email_verified: bool | None
    source: str


class _Unavailable(Exception):
    pass


def userinfo_url_is_allowed(url: str) -> bool:
    """https:// always. Plain http:// only off a deployment (local
    development against a local provider): a deployment never sends a
    bearer token, or trusts verification claims, over cleartext."""
    lowered = url.strip().lower()
    if lowered.startswith("https://"):
        return True
    return lowered.startswith("http://") and not settings.is_deployed


def _fetch_userinfo(url: str, access_token: str) -> dict:
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_USERINFO_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise _Unavailable from exc
    if response.status_code != 200:
        raise _Unavailable
    try:
        body = response.json()
    except ValueError as exc:
        raise _Unavailable from exc
    if not isinstance(body, dict):
        raise _Unavailable
    return body


def resolve_verified_email(claims: ExternalIdentityClaims, access_token: str) -> VerifiedEmail:
    url = settings.OIDC_USERINFO_URL
    if not url:
        return VerifiedEmail(claims.email, claims.email_verified, SOURCE_ACCESS_TOKEN)
    # Every non-success outcome below verifies nothing (fail closed); the
    # source only tells the caller whether retrying can help.
    if not userinfo_url_is_allowed(url):
        return VerifiedEmail(None, None, SOURCE_USERINFO_INSECURE)
    try:
        body = _fetch_userinfo(url, access_token)
    except _Unavailable:
        return VerifiedEmail(None, None, SOURCE_USERINFO_UNAVAILABLE)
    if body.get("sub") != claims.subject:
        return VerifiedEmail(None, None, SOURCE_USERINFO_SUBJECT_MISMATCH)
    email = body.get("email")
    verified = body.get("email_verified")
    return VerifiedEmail(
        email if isinstance(email, str) and email else None,
        verified if isinstance(verified, bool) else None,
        SOURCE_USERINFO,
    )
