"""Production OIDC/OAuth2 access-token verification — SIE Milestone 20:
Production Authentication & Identity Foundation v0.1.

    Bearer <JWT>  ->  OIDCTokenVerifier.verify()  ->  ExternalIdentityClaims
        -> app.services.identity_service.IdentityResolverService
        -> SIE User -> OrganizationMembership -> TenantContext (UNCHANGED)

This module is the one concrete, real implementation of
`app.services.identity_service.TokenVerifier` this codebase ships — see
that module's own docstring, which named this exact file as the future
extension point. It does not touch, and is not imported by, anything in
the authorization pipeline downstream of `ExternalIdentityClaims`:
`IdentityResolverService`, `AuthorizationService`, `TenantContext`, and
`Permission` are all completely unaware this module exists.

**Provider-neutral.** Nothing here imports or references any specific
identity provider's SDK (no `msal`, no `okta-jwt-verifier`, ...) — a
deployment points this at whatever standards-compliant OIDC/OAuth2
provider it uses (Azure AD, Okta, Auth0, Google, a self-hosted Keycloak,
...) purely through `app.core.config.Settings`' `OIDC_*` fields:
`OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_ALGORITHMS`,
`OIDC_JWKS_CACHE_TTL_SECONDS`, `OIDC_PROVIDER_LABEL`.

**No hand-rolled cryptography.** Every signature/claim check below is
performed by PyJWT (`jwt.decode`, `jwt.PyJWKClient`) — an established,
widely used JWT/OIDC library — not reimplemented here. This module's own
code is limited to: routing configuration into PyJWT's own API, turning
its exceptions into one clearly-worded `TokenVerificationError` (never
echoing token content), and shaping the result into
`ExternalIdentityClaims`.

**Fail closed on missing configuration.** `get_oidc_verifier()` raises
`OIDCConfigurationError` — never returns a permissive/partial verifier —
whenever `OIDC_ISSUER`, `OIDC_AUDIENCE`, or `OIDC_JWKS_URL` is not set.
Every caller of this module (see `app.api.deps_auth`) is required to
translate that into a fail-closed HTTP response (501, "not configured"),
never into any fallback authentication mechanism, insecure or otherwise.
"""

from __future__ import annotations

from typing import Protocol

import jwt
from jwt import PyJWKClient
from jwt.api_jwk import PyJWK

from app.core.config import settings
from app.services.identity_service import ExternalIdentityClaims


class OIDCConfigurationError(Exception):
    """Raised by `get_oidc_verifier()` when production authentication is
    invoked but `OIDC_ISSUER`/`OIDC_AUDIENCE`/`OIDC_JWKS_URL` are not all
    configured. Callers must treat this as a fail-closed condition (HTTP
    501, "authentication is not configured") — never as a signal to fall
    back to any other mechanism."""


class TokenVerificationError(Exception):
    """Raised for any token that fails verification for any reason: bad
    signature, expired, wrong issuer, wrong audience, missing subject,
    malformed token, unknown key id, or an unreachable/invalid JWKS. The
    message is always safe to log or return to a caller — it never
    includes the raw token or any key material."""


class JWKSKeyResolver(Protocol):
    """The narrow slice of `jwt.PyJWKClient`'s interface
    `OIDCTokenVerifier` actually depends on — letting a test (or a
    deployment that prefers to pin its provider's keys rather than fetch
    them live) supply `StaticJWKSKeyResolver` below instead of a real
    network-backed client, without `OIDCTokenVerifier` itself knowing the
    difference."""

    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


class StaticJWKSKeyResolver:
    """A `JWKSKeyResolver` backed by an already-fetched JSON Web Key Set
    (a plain `{"keys": [...]}` dict, the same shape a provider's JWKS
    endpoint returns) rather than a live HTTPS fetch.

    Used by this milestone's own test suite so real RSA/EC signature
    verification is exercised end-to-end without a live identity provider
    or network access (see tests/test_oidc_verifier.py and
    tests/test_production_auth.py) — never a mock of the verification
    logic itself, only of *where the key set comes from*. Also usable by
    a real deployment that prefers to pin a provider's keys rather than
    fetch them at request time.
    """

    def __init__(self, jwks: dict) -> None:
        self._keys_by_kid: dict[str, PyJWK] = {}
        for raw_key in jwks.get("keys", []):
            key = PyJWK.from_dict(raw_key)
            if key.key_id:
                self._keys_by_kid[key.key_id] = key

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenVerificationError(f"Malformed token header: {exc}") from exc
        kid = header.get("kid")
        if not kid or kid not in self._keys_by_kid:
            raise TokenVerificationError(f"Unknown signing key id: {kid!r}.")
        return self._keys_by_kid[kid]


class OIDCTokenVerifier:
    """Provider-neutral OIDC/OAuth2 access-token verifier — the concrete
    `app.services.identity_service.TokenVerifier` implementation this
    milestone adds.

    Validates, via PyJWT (never reimplemented here):

      * **signature** — against a key resolved from the configured JWKS
        by the token's own `kid` header (see `JWKSKeyResolver`).
      * **issuer** (`iss`) — must equal the configured issuer exactly.
      * **audience** (`aud`) — must contain the configured audience.
      * **expiry** (`exp`) — must not have passed. Required to be present.
      * **not-before** (`nbf`) — checked by PyJWT automatically whenever
        the claim is present (optional per the JWT spec, so its absence
        is not itself an error).
      * **subject** (`sub`) — must be present and a non-empty string.

    A successfully verified token yields `ExternalIdentityClaims` with
    `issuer` set to *this verifier's own configured issuer* (not
    whatever the token happened to claim before the issuer check ran) —
    claims are only ever read from an already-validated payload.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        algorithms: list[str],
        key_resolver: JWKSKeyResolver,
        provider_label: str,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._algorithms = algorithms
        self._key_resolver = key_resolver
        self._provider_label = provider_label

    def verify(self, token: str) -> ExternalIdentityClaims:
        if not token or token.count(".") != 2:
            raise TokenVerificationError("Malformed token: expected a three-segment JWT.")

        try:
            signing_key = self._key_resolver.get_signing_key_from_jwt(token)
        except TokenVerificationError:
            raise
        except Exception as exc:  # jwt.PyJWKClientError, network failures, ...
            raise TokenVerificationError(
                f"Could not resolve a signing key for this token: {exc}"
            ) from exc

        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenVerificationError("Token has expired.") from exc
        except jwt.InvalidAudienceError as exc:
            raise TokenVerificationError("Token audience does not match this deployment.") from exc
        except jwt.InvalidIssuerError as exc:
            raise TokenVerificationError("Token issuer does not match this deployment.") from exc
        except jwt.MissingRequiredClaimError as exc:
            raise TokenVerificationError(f"Token is missing a required claim: {exc}") from exc
        except jwt.InvalidSignatureError as exc:
            raise TokenVerificationError("Token signature is invalid.") from exc
        except jwt.PyJWTError as exc:
            raise TokenVerificationError(f"Token failed verification: {exc}") from exc

        subject = payload.get("sub")
        if not subject or not isinstance(subject, str):
            # Belt-and-braces: options={"require": [..., "sub"]} above
            # already rejects a token with no "sub" claim at all; this
            # additionally rejects one where "sub" is present but empty
            # or not a string.
            raise TokenVerificationError("Token is missing a subject (sub) claim.")

        email = payload.get("email")
        display_name = payload.get("name")

        return ExternalIdentityClaims(
            subject=subject,
            issuer=self._issuer,
            email=email if isinstance(email, str) and email else None,
            display_name=display_name if isinstance(display_name, str) and display_name else None,
            provider=self._provider_label,
        )


def _build_key_resolver() -> JWKSKeyResolver:
    assert settings.OIDC_JWKS_URL is not None  # guarded by get_oidc_verifier() before this runs
    return PyJWKClient(
        settings.OIDC_JWKS_URL,
        cache_keys=True,
        lifespan=settings.OIDC_JWKS_CACHE_TTL_SECONDS,
    )


# Cache keyed by the exact configuration used to build each verifier —
# rebuilt automatically whenever OIDC_* settings change (e.g. between
# tests, which mutate `settings` directly the same way `DEV_MODE` already
# is in tests/conftest.py), while still reusing one verifier/JWKS-client
# instance (and its own internal key cache — see OIDC_JWKS_CACHE_TTL_SECONDS)
# across requests for a stable configuration, exactly the way it would run
# in a real long-lived deployment process.
_verifier_cache: dict[tuple[str, str, str, tuple[str, ...]], OIDCTokenVerifier] = {}


def get_oidc_verifier() -> OIDCTokenVerifier:
    """Build (and cache) the production `OIDCTokenVerifier` from
    `Settings`. Raises `OIDCConfigurationError` — callers must fail closed
    (HTTP 501), never fall back to any other authentication mechanism —
    when `OIDC_ISSUER`, `OIDC_AUDIENCE`, or `OIDC_JWKS_URL` is not
    configured."""
    missing = [
        name
        for name, value in (
            ("OIDC_ISSUER", settings.OIDC_ISSUER),
            ("OIDC_AUDIENCE", settings.OIDC_AUDIENCE),
            ("OIDC_JWKS_URL", settings.OIDC_JWKS_URL),
        )
        if not value
    ]
    if missing:
        raise OIDCConfigurationError(
            "Production authentication is not fully configured; missing: " + ", ".join(missing)
        )

    cache_key = (
        settings.OIDC_ISSUER,
        settings.OIDC_AUDIENCE,
        settings.OIDC_JWKS_URL,
        tuple(settings.oidc_algorithms_list),
    )
    cached = _verifier_cache.get(cache_key)
    if cached is not None:
        return cached

    verifier = OIDCTokenVerifier(
        issuer=settings.OIDC_ISSUER,
        audience=settings.OIDC_AUDIENCE,
        algorithms=settings.oidc_algorithms_list,
        key_resolver=_build_key_resolver(),
        provider_label=settings.OIDC_PROVIDER_LABEL,
    )
    _verifier_cache[cache_key] = verifier
    return verifier


__all__ = [
    "OIDCConfigurationError",
    "TokenVerificationError",
    "JWKSKeyResolver",
    "StaticJWKSKeyResolver",
    "OIDCTokenVerifier",
    "get_oidc_verifier",
]
