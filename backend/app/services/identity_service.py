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

import hashlib
import uuid
from dataclasses import dataclass
from typing import NoReturn, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.base import utcnow
from app.models.identity import Identity
from app.models.user import User
from app.services.audit_service import AuditAction, audit_service


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
    # The token's `email_verified` claim: True or False only when the
    # claim is a JSON boolean, otherwise None ("unknown", never verified).
    email_verified: bool | None = None


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


class IdentityLinkRejectedError(Exception):
    """A verified token whose identity is not bound to a SIE user and may
    not be bound automatically. `reason` is one fixed code from
    `LinkRejection`: safe to audit, never caller-supplied text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LinkRejection:
    """Reason codes for `IdentityLinkRejectedError` and the
    `IDENTITY_LINK_REJECTED` audit event."""

    NO_GRANT = "unknown_identity_no_grant"
    ORPHANED_IDENTITY = "orphaned_identity_requires_account_link"
    EMAIL_LINKING_DISABLED = "email_linking_disabled"
    ISSUER_NOT_TRUSTED = "issuer_not_trusted_for_email"
    EMAIL_MISSING = "email_claim_missing"
    EMAIL_VERIFIED_MISSING = "email_verified_claim_missing"
    EMAIL_NOT_VERIFIED = "email_not_verified"
    NO_MATCHING_USER = "no_matching_user"
    AMBIGUOUS_EMAIL = "ambiguous_email_match"
    TARGET_PLATFORM_ADMIN = "target_is_platform_admin"
    TARGET_INACTIVE = "target_user_inactive"
    TARGET_ALREADY_BOUND = "target_already_bound_for_issuer"
    CONCURRENT_CONFLICT = "concurrent_conflict"


def subject_fingerprint(issuer: str, subject: str) -> str:
    """A short, non-reversible handle for an external identity, so audit
    rows can be correlated without storing the subject itself."""
    return hashlib.sha256(f"{issuer}\n{subject}".encode("utf-8")).hexdigest()[:16]


class IdentityResolverService:
    """Resolves already-verified claims to a SIE `User`.

    `(issuer, subject)` is the only identity key. A token whose pair is
    already bound authenticates as that user. Anything else is refused
    with `IdentityLinkRejectedError`, unless verified-email linking is
    explicitly enabled for that exact issuer (`_link_by_verified_email`).
    The usual way in for a new person is an invitation, and for an
    existing account an account-link grant
    (app/services/identity_link_service.py). No user is ever created
    here.

    Deliberately does not accept a raw token — callers verify first (via a
    `TokenVerifier`) and pass in `ExternalIdentityClaims`.
    """

    def resolve_user(self, db: Session, *, claims: ExternalIdentityClaims) -> User:
        identity = self._get_identity(db, issuer=claims.issuer, subject=claims.subject)
        if identity is not None:
            return self._sign_in_bound(db, identity, claims)

        if not settings.OIDC_TRUST_VERIFIED_EMAIL_FOR_LINKING:
            self._reject(db, claims, LinkRejection.NO_GRANT)
        return self._link_by_verified_email(db, claims=claims)

    def _link_by_verified_email(self, db: Session, *, claims: ExternalIdentityClaims) -> User:
        """Opt-in only. Every condition must hold, or the identity is
        refused: the issuer is explicitly trusted, `email_verified` is the
        boolean true, exactly one user has that email (case-insensitive),
        that user is active, is not a platform administrator, and has no
        identity from this issuer yet."""
        if claims.issuer not in settings.oidc_email_linking_trusted_issuers:
            self._reject(db, claims, LinkRejection.ISSUER_NOT_TRUSTED)
        if not claims.email:
            self._reject(db, claims, LinkRejection.EMAIL_MISSING)
        if claims.email_verified is None:
            self._reject(db, claims, LinkRejection.EMAIL_VERIFIED_MISSING)
        if claims.email_verified is not True:
            self._reject(db, claims, LinkRejection.EMAIL_NOT_VERIFIED)

        # Locked, so concurrent links for one user run the checks below one
        # at a time.
        matches = (
            db.execute(
                select(User)
                .where(func.lower(User.email) == claims.email.lower())
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            .scalars()
            .all()
        )
        if not matches:
            self._reject(db, claims, LinkRejection.NO_MATCHING_USER)
        if len(matches) > 1:
            self._reject(db, claims, LinkRejection.AMBIGUOUS_EMAIL)
        user = matches[0]
        if user.platform_role is not None:
            self._reject(db, claims, LinkRejection.TARGET_PLATFORM_ADMIN, user_id=user.id)
        if user.status != "active":
            self._reject(db, claims, LinkRejection.TARGET_INACTIVE, user_id=user.id)
        # A concurrent request may have bound this exact (issuer, subject)
        # while this one waited for the lock: if so, it is simply that user.
        identity = self._get_identity(db, issuer=claims.issuer, subject=claims.subject)
        if identity is not None:
            return self._sign_in_bound(db, identity, claims)
        if user_has_identity_for_issuer(db, user_id=user.id, issuer=claims.issuer):
            self._reject(db, claims, LinkRejection.TARGET_ALREADY_BOUND, user_id=user.id)

        try:
            return self._bind_verified_email(db, claims=claims, user=user)
        except IntegrityError:
            # Another request (an account-link redemption, say) bound this
            # (issuer, subject) first; the unique constraint caught it.
            db.rollback()
            identity = self._get_identity(db, issuer=claims.issuer, subject=claims.subject)
            if identity is not None:
                return self._sign_in_bound(db, identity, claims)
            self._reject(db, claims, LinkRejection.CONCURRENT_CONFLICT)

    def _bind_verified_email(self, db: Session, *, claims: ExternalIdentityClaims, user: User) -> User:
        identity = Identity(
            user_id=user.id,
            subject=claims.subject,
            issuer=claims.issuer,
            email=claims.email,
            display_name=claims.display_name,
            provider=claims.provider,
            last_authenticated_at=utcnow(),
        )
        db.add(identity)
        db.flush()
        audit_service.log(
            db,
            action=AuditAction.IDENTITY_LINKED,
            resource_type="Identity",
            resource_id=identity.id,
            user_id=user.id,
            metadata={
                "issuer": claims.issuer,
                "provider": claims.provider,
                "method": "verified_email",
                "subject_fingerprint": subject_fingerprint(claims.issuer, claims.subject),
            },
            commit=False,
        )
        db.commit()
        return user

    def _sign_in_bound(self, db: Session, identity: Identity, claims: ExternalIdentityClaims) -> User:
        if identity.user is None:
            # Its user link was lost. Never re-attach it by email: an
            # account-link grant is the recovery path.
            self._reject(db, claims, LinkRejection.ORPHANED_IDENTITY)
        self._sync_identity_fields(db, identity, claims)
        identity.last_authenticated_at = utcnow()
        db.add(identity)
        db.commit()
        return identity.user

    def _reject(
        self,
        db: Session,
        claims: ExternalIdentityClaims,
        reason: str,
        *,
        user_id: uuid.UUID | None = None,
    ) -> NoReturn:
        db.rollback()
        log_link_rejection(db, issuer=claims.issuer, subject=claims.subject, reason=reason, user_id=user_id)
        raise IdentityLinkRejectedError(reason)

    def _sync_identity_fields(self, db: Session, identity: Identity, claims: ExternalIdentityClaims) -> None:
        # Profile attributes only. They never change which user this is.
        identity.email = claims.email
        identity.display_name = claims.display_name
        identity.provider = claims.provider
        db.add(identity)

    def _get_identity(self, db: Session, *, issuer: str, subject: str) -> Identity | None:
        stmt = select(Identity).where(Identity.issuer == issuer, Identity.subject == subject)
        return db.execute(stmt).scalar_one_or_none()


def user_has_identity_for_issuer(db: Session, *, user_id: uuid.UUID, issuer: str) -> bool:
    stmt = select(Identity.id).where(Identity.user_id == user_id, Identity.issuer == issuer).limit(1)
    return db.execute(stmt).first() is not None


def log_link_rejection(
    db: Session,
    *,
    issuer: str,
    subject: str,
    reason: str,
    user_id: uuid.UUID | None = None,
    grant_id: uuid.UUID | None = None,
) -> None:
    """One `IDENTITY_LINK_REJECTED` row: issuer, reason code and subject
    fingerprint. Never the token, the email or a one-time code."""
    metadata = {"issuer": issuer, "reason": reason, "subject_fingerprint": subject_fingerprint(issuer, subject)}
    if grant_id is not None:
        metadata["grant_id"] = str(grant_id)
    audit_service.log(
        db,
        action=AuditAction.IDENTITY_LINK_REJECTED,
        resource_type="Identity",
        user_id=user_id,
        metadata=metadata,
    )


identity_resolver_service = IdentityResolverService()
