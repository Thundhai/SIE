"""Test-only production-JWT fixtures — SIE Milestone 20: Production
Authentication & Identity Foundation v0.1.

Generates a real RSA keypair once per test session and issues genuinely
RS256-signed JWTs against it, so the test suite exercises *real* PyJWT
signature verification end to end (never a mock of the verification logic
itself) without any live identity provider or network access — the same
role `app/services/oidc_verifier.py::StaticJWKSKeyResolver` plays for a
deployment that prefers to pin its provider's keys rather than fetch them
live.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.api import deps_auth
from app.services.oidc_verifier import OIDCTokenVerifier, StaticJWKSKeyResolver

TEST_ISSUER = "https://test-issuer.example.com"
TEST_AUDIENCE = "sie-test-audience"
TEST_KID = "test-key-1"
OTHER_KID = "test-key-2"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
# A second keypair — used to sign a token whose signature must be
# rejected even though everything else about it (issuer, audience,
# subject, kid claimed) looks legitimate, i.e. the "invalid signature"
# security-test case.
_other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64url_uint(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwk_from_public_key(private_key, kid: str) -> dict:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


TEST_JWKS = {"keys": [_jwk_from_public_key(_private_key, TEST_KID)]}


def make_test_verifier(
    *,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    jwks: dict | None = None,
    provider_label: str = "test-idp",
) -> OIDCTokenVerifier:
    return OIDCTokenVerifier(
        issuer=issuer,
        audience=audience,
        algorithms=["RS256"],
        key_resolver=StaticJWKSKeyResolver(jwks if jwks is not None else TEST_JWKS),
        provider_label=provider_label,
    )


def make_test_token(
    *,
    subject: str | None = "user-subject-1",
    issuer: str = TEST_ISSUER,
    audience: str | list[str] | None = TEST_AUDIENCE,
    kid: str | None = TEST_KID,
    expires_delta: timedelta | None = timedelta(hours=1),
    not_before_delta: timedelta | None = None,
    extra_claims: dict | None = None,
    signing_key=None,
    algorithm: str = "RS256",
    omit_iat: bool = False,
) -> str:
    """Build a real, signed JWT. Defaults produce a token that passes
    every check `OIDCTokenVerifier.verify()` performs against
    `make_test_verifier()`'s defaults — every test overrides exactly the
    one thing it wants to make invalid."""
    now = datetime.now(timezone.utc)
    payload: dict = {}
    if subject is not None:
        payload["sub"] = subject
    if issuer is not None:
        payload["iss"] = issuer
    if audience is not None:
        payload["aud"] = audience
    if not omit_iat:
        payload["iat"] = now
    if expires_delta is not None:
        payload["exp"] = now + expires_delta
    if not_before_delta is not None:
        payload["nbf"] = now + not_before_delta
    if extra_claims:
        payload.update(extra_claims)

    headers = {"kid": kid} if kid else {}
    key = signing_key if signing_key is not None else _private_key
    return jwt.encode(payload, key, algorithm=algorithm, headers=headers)


def make_token_signed_by_other_key(**kwargs) -> str:
    """A token that claims the legitimate `TEST_KID` in its header (so a
    naive resolver would happily hand back the real signing key) but is
    actually signed with an unrelated private key — the "signature does
    not match" case, distinct from "unknown kid"."""
    return make_test_token(signing_key=_other_private_key, **kwargs)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def production_auth(monkeypatch):
    """Wires the test RSA-backed verifier into the app in place of a real
    network JWKS fetch — see module docstring. Also sets the `OIDC_*`
    settings themselves (rather than only patching `get_oidc_verifier`)
    so `get_authenticated_user_id`'s own "is OIDC configured at all"
    check (used to distinguish 501 "not configured" from 401 "missing
    token") observes production auth as configured too."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setattr(settings, "OIDC_JWKS_URL", "https://test-issuer.example.com/.well-known/jwks.json")

    verifier = make_test_verifier()
    monkeypatch.setattr(deps_auth, "get_oidc_verifier", lambda: verifier)
    return verifier
