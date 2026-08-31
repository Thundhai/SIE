"""Identity resolution — turning a verified external identity into a SIE
User.

    External Identity  ->  Identity Resolver  ->  SIE User

This module defines the *boundary* a real OIDC/OAuth2 verifier plugs into
(`TokenVerifier`) without SIE depending on any specific identity provider.
No token verification is implemented here: `TokenVerifier.verify()` is a
`Protocol` — a real implementation (validating a JWT's signature against
an issuer's published JWKS, checking `aud`/`exp`/`iss`, etc.) is future
work, deliberately out of scope for this milestone, and would live in its
own module (e.g. `app/services/oidc_verifier.py`) implementing this same
interface, not bolted onto this one.

`DevTokenVerifier` is the one concrete implementation that exists today.
It performs no cryptography and trusts its input completely — see its own
docstring. It exists only so the rest of the identity/authorization
pipeline (resolver -> user -> membership -> tenant context) can be
exercised end-to-end before real verification exists, via dependency
injection in tests/dev tooling (see app/api/deps.py), never as a
general-purpose way to authenticate.
"""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import Identity
from app.models.user import User
from app.services.user_service import user_service


@dataclass(frozen=True)
class ExternalIdentityClaims:
    """The already-verified output of a token verification step: exactly
    the claims `Identity` needs (see app/models/identity.py), and nothing
    about *how* they were verified. A real OIDC verifier's output is
    expected to be normalized into this same shape before reaching the
    resolver below."""

    subject: str
    issuer: str
    email: str | None
    display_name: str | None
    provider: str


class TokenVerifier(Protocol):
    """Interface a real OIDC/OAuth2 verifier implements. Deliberately
    provider-agnostic: SIE core has no import-time dependency on any
    specific identity provider's SDK."""

    def verify(self, token: str) -> ExternalIdentityClaims:
        """Validate `token` and return the claims it carries. Must raise
        rather than return a partial/unverified result on any failure
        (bad signature, expired, wrong audience, unreachable issuer,
        ...)."""
        ...


class DevTokenVerifier:
    """Development-only stand-in for a real `TokenVerifier`.

    THIS PERFORMS NO CRYPTOGRAPHIC VERIFICATION. It treats its `token`
    argument as already-trusted, pipe-delimited claims
    ("sub|issuer|email|display_name", trailing fields optional) rather
    than a real signed token — pipe-delimited specifically so a
    URL-shaped issuer (e.g. "https://dev.issuer") can be used without
    colliding with the delimiter. It exists solely so local development
    and tests can exercise identity resolution without a real identity
    provider configured. It must never be wired into a request path that
    isn't already gated by `settings.DEV_MODE` (see app/core/config.py and
    app/api/deps_auth.py) — see that module's docstring for the full set
    of guarantees the dev-mode gate provides.
    """

    def verify(self, token: str) -> ExternalIdentityClaims:
        parts = token.split("|")
        subject = parts[0] if parts else token
        issuer = parts[1] if len(parts) > 1 else "dev"
        email = parts[2] if len(parts) > 2 and parts[2] else None
        display_name = parts[3] if len(parts) > 3 and parts[3] else None
        return ExternalIdentityClaims(
            subject=subject,
            issuer=issuer,
            email=email,
            display_name=display_name,
            provider="dev",
        )


class IdentityResolverService:
    """Resolves already-verified claims to a SIE `User`, creating both the
    `Identity` link and (if this is the first time this person has been
    seen) the `User` row itself.

    Deliberately does not accept a raw token — callers verify first (via a
    `TokenVerifier`) and pass in `ExternalIdentityClaims`, keeping this
    service's own logic free of any provider- or crypto-specific concern.
    """

    def resolve_or_create_user(self, db: Session, *, claims: ExternalIdentityClaims) -> User:
        identity = self._get_identity(db, issuer=claims.issuer, subject=claims.subject)
        if identity is not None and identity.user is not None:
            self._sync_identity_fields(db, identity, claims)
            return identity.user

        user = self._resolve_or_create_user_by_email(db, claims=claims)

        if identity is None:
            identity = Identity(
                user_id=user.id,
                subject=claims.subject,
                issuer=claims.issuer,
                email=claims.email,
                display_name=claims.display_name,
                provider=claims.provider,
            )
            db.add(identity)
        else:
            identity.user_id = user.id
            self._sync_identity_fields(db, identity, claims)
        db.commit()
        return user

    def _resolve_or_create_user_by_email(
        self, db: Session, *, claims: ExternalIdentityClaims
    ) -> User:
        if claims.email is not None:
            existing = user_service.get_by_email(db, email=claims.email)
            if existing is not None:
                return existing
            user = User(email=claims.email, name=claims.display_name or claims.email)
        else:
            # No email claim at all — still provision a user rather than
            # failing closed on identity resolution; a stable, synthetic
            # placeholder email keeps `User.email` (unique, not null)
            # satisfiable. This is an edge case a real IdP integration
            # should try to avoid hitting.
            placeholder_email = f"{claims.subject}@{claims.issuer}.identity.invalid"
            user = User(email=placeholder_email, name=claims.display_name or claims.subject)
        db.add(user)
        db.flush()  # assign user.id without committing yet
        return user

    def _sync_identity_fields(
        self, db: Session, identity: Identity, claims: ExternalIdentityClaims
    ) -> None:
        identity.email = claims.email
        identity.display_name = claims.display_name
        identity.provider = claims.provider
        db.add(identity)

    def _get_identity(self, db: Session, *, issuer: str, subject: str) -> Identity | None:
        stmt = select(Identity).where(Identity.issuer == issuer, Identity.subject == subject)
        return db.execute(stmt).scalar_one_or_none()


identity_resolver_service = IdentityResolverService()
