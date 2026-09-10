"""Unit tests: `app/services/oidc_verifier.py` — SIE Milestone 20:
Production Authentication & Identity Foundation v0.1, requirement #10's
"Token validation" case list, exercised directly against
`OIDCTokenVerifier` (no HTTP layer, no database) so each failure mode is
isolated.
"""

from datetime import timedelta

import pytest

from app.services.identity_service import ExternalIdentityClaims
from app.services.oidc_verifier import (
    OIDCConfigurationError,
    StaticJWKSKeyResolver,
    TokenVerificationError,
    get_oidc_verifier,
)
from tests.oidc_test_helpers import (
    OTHER_KID,
    TEST_AUDIENCE,
    TEST_ISSUER,
    TEST_JWKS,
    TEST_KID,
    make_test_token,
    make_test_verifier,
    make_token_signed_by_other_key,
)


def test_valid_token_verifies_and_returns_claims():
    verifier = make_test_verifier()
    token = make_test_token(subject="sub-1", extra_claims={"email": "a@example.com", "name": "A Person"})

    claims = verifier.verify(token)

    assert claims == ExternalIdentityClaims(
        subject="sub-1",
        issuer=TEST_ISSUER,
        email="a@example.com",
        display_name="A Person",
        provider="test-idp",
    )


def test_expired_token_is_rejected():
    verifier = make_test_verifier()
    token = make_test_token(expires_delta=timedelta(hours=-1))

    with pytest.raises(TokenVerificationError, match="expired"):
        verifier.verify(token)


def test_invalid_signature_is_rejected():
    verifier = make_test_verifier()
    # Signed with an unrelated key while still claiming the real kid.
    token = make_token_signed_by_other_key()

    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_wrong_issuer_is_rejected():
    verifier = make_test_verifier()
    token = make_test_token(issuer="https://not-the-configured-issuer.example.com")

    with pytest.raises(TokenVerificationError, match="issuer"):
        verifier.verify(token)


def test_wrong_audience_is_rejected():
    verifier = make_test_verifier()
    token = make_test_token(audience="some-other-audience")

    with pytest.raises(TokenVerificationError, match="audience"):
        verifier.verify(token)


def test_missing_subject_claim_is_rejected():
    verifier = make_test_verifier()
    token = make_test_token(subject=None)

    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_malformed_token_is_rejected():
    verifier = make_test_verifier()

    with pytest.raises(TokenVerificationError, match="Malformed"):
        verifier.verify("this-is-not-a-jwt-at-all")


def test_empty_token_is_rejected():
    verifier = make_test_verifier()

    with pytest.raises(TokenVerificationError):
        verifier.verify("")


def test_unknown_key_id_is_rejected():
    verifier = make_test_verifier()
    token = make_test_token(kid=OTHER_KID)  # a kid never published in TEST_JWKS

    with pytest.raises(TokenVerificationError, match="Unknown signing key"):
        verifier.verify(token)


def test_missing_kid_header_is_rejected():
    verifier = make_test_verifier()
    token = make_test_token(kid=None)

    with pytest.raises(TokenVerificationError, match="Unknown signing key"):
        verifier.verify(token)


def test_token_with_no_expiry_claim_at_all_is_rejected():
    """`options={"require": [...]}` — a token that never carries `exp` is
    rejected outright, not silently treated as "never expires"."""
    verifier = make_test_verifier()
    token = make_test_token(expires_delta=None)

    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_not_before_in_the_future_is_rejected():
    verifier = make_test_verifier()
    token = make_test_token(not_before_delta=timedelta(hours=1))

    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_not_before_in_the_past_is_accepted():
    verifier = make_test_verifier()
    token = make_test_token(not_before_delta=timedelta(hours=-1))

    claims = verifier.verify(token)
    assert claims.subject == "user-subject-1"


def test_wrong_algorithm_is_rejected():
    """A verifier configured for RS256 must not accept an HS256 (shared-
    secret) token, even one an attacker could trivially forge without any
    knowledge of the real RSA private key — PyJWT's own algorithm
    allowlist enforces this, not custom code here."""
    verifier = make_test_verifier()
    token = make_test_token(signing_key="attacker-guessable-secret", algorithm="HS256")

    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_static_key_resolver_exposes_configured_keys_by_kid():
    resolver = StaticJWKSKeyResolver(TEST_JWKS)
    token = make_test_token()

    key = resolver.get_signing_key_from_jwt(token)

    assert key.key_id == TEST_KID


# --- get_oidc_verifier() configuration gate ---------------------------------------------


def test_get_oidc_verifier_fails_closed_when_unconfigured(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "OIDC_ISSUER", None)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", None)
    monkeypatch.setattr(settings, "OIDC_JWKS_URL", None)

    with pytest.raises(OIDCConfigurationError):
        get_oidc_verifier()


def test_get_oidc_verifier_fails_closed_when_partially_configured(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setattr(settings, "OIDC_JWKS_URL", None)  # missing

    with pytest.raises(OIDCConfigurationError, match="OIDC_JWKS_URL"):
        get_oidc_verifier()
