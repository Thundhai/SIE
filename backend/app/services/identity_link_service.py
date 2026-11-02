"""Invitations and account-link grants: the explicit ways an external
identity (issuer, subject) becomes bound to a SIE user. See
app/models/identity_link_grant.py for the two kinds.

Rules that hold for every redemption:

* The one-time code is 256 bits from `secrets`. Only its SHA-256 hash is
  stored, and it is compared by hash lookup. The code is returned once,
  at creation, and never logged or audited.
* A code is single-use and expires (`IDENTITY_LINK_GRANT_TTL_HOURS`).
  Redemption locks the grant row, so two concurrent redemptions cannot
  both succeed.
* An identity already bound to a user is never re-bound (no silent
  reassignment). An orphaned identity, one whose user link was lost, can
  be re-bound only through an ACCOUNT_LINK grant.
* Invitations are accepted only through app/services/invitation_service.py,
  which also requires a verified, matching email. This module refuses them.
* A platform-administrator account can be linked only through a grant
  the operator script issued (`allows_platform_admin`), never through
  the API or by email.
* Every success and every refusal is audited, with a fixed reason code.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.base import utcnow
from app.models.identity import Identity
from app.models.identity_link_grant import (
    GRANT_KIND_ACCOUNT_LINK,
    STATUS_ACCEPTED,
    IdentityLinkGrant,
)
from app.models.user import User
from app.services.audit_service import AuditAction, audit_service
from app.services.identity_service import (
    ExternalIdentityClaims,
    log_link_rejection,
    subject_fingerprint,
    user_has_identity_for_issuer,
)

CODE_PREFIX = "sie_link_"


class GrantRedemptionError(Exception):
    """Redemption refused. `reason` is a fixed code; `status_code` is the
    HTTP status the API returns."""

    def __init__(self, reason: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code
        self.message = message


class GrantCreationError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class CreatedGrant:
    grant: IdentityLinkGrant
    code: str  # shown to the creator once; never stored or logged


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _new_code() -> str:
    return CODE_PREFIX + secrets.token_urlsafe(32)


def _expiry():
    return utcnow() + timedelta(hours=settings.IDENTITY_LINK_GRANT_TTL_HOURS)


def _is_expired(expires_at) -> bool:
    # Stored timezone-aware; a backend that drops the zone (SQLite) hands
    # back naive UTC.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= utcnow()


def _audit_created(db: Session, grant: IdentityLinkGrant, *, actor_user_id: uuid.UUID | None) -> None:
    metadata: dict = {"grant_id": str(grant.id), "kind": grant.kind, "expires_at": grant.expires_at.isoformat()}
    if grant.target_user_id is not None:
        metadata["target_user_id"] = str(grant.target_user_id)
    if grant.role is not None:
        metadata["role"] = grant.role
    if grant.allows_platform_admin:
        metadata["allows_platform_admin"] = True
    audit_service.log(
        db,
        action=AuditAction.IDENTITY_LINK_GRANT_CREATED,
        resource_type="IdentityLinkGrant",
        resource_id=grant.id,
        organization_id=grant.organization_id,
        user_id=actor_user_id,
        metadata=metadata,
        commit=False,
    )



class IdentityLinkService:
    def create_account_link(
        self,
        db: Session,
        *,
        target_user_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        allow_platform_admin: bool = False,
    ) -> CreatedGrant:
        """A grant binding the redeemer's identity to an existing user.
        `allow_platform_admin` is for the operator script only; the API
        always passes False."""
        target = db.get(User, target_user_id)
        if target is None:
            raise GrantCreationError(404, "User not found.")
        if target.platform_role is not None and not allow_platform_admin:
            raise GrantCreationError(
                403,
                "A platform administrator account can only be linked with the operator script "
                "(scripts/create_identity_link_grant.py).",
            )
        if target.status != "active":
            raise GrantCreationError(409, "The target user is not active.")
        code = _new_code()
        grant = IdentityLinkGrant(
            kind=GRANT_KIND_ACCOUNT_LINK,
            token_sha256=hash_code(code),
            target_user_id=target.id,
            allows_platform_admin=bool(allow_platform_admin and target.platform_role is not None),
            created_by_user_id=actor_user_id,
            expires_at=_expiry(),
        )
        db.add(grant)
        db.flush()
        _audit_created(db, grant, actor_user_id=actor_user_id)
        db.commit()
        return CreatedGrant(grant=grant, code=code)

    def redeem(self, db: Session, *, claims: ExternalIdentityClaims, code: str) -> tuple[User, IdentityLinkGrant]:
        """Bind the caller's verified identity using `code`. Returns the
        bound user and the grant. Raises `GrantRedemptionError` (audited)."""
        grant = db.execute(
            select(IdentityLinkGrant).where(IdentityLinkGrant.token_sha256 == hash_code(code)).with_for_update()
        ).scalar_one_or_none()
        if grant is None or grant.redeemed_at is not None or _is_expired(grant.expires_at):
            # One answer for unknown, used and expired: no oracle.
            self._refuse(
                db,
                claims,
                "grant_invalid_or_expired",
                404,
                "This code is invalid or has expired.",
                grant_id=grant.id if grant is not None else None,
            )

        identity = db.execute(
            select(Identity)
            .where(Identity.issuer == claims.issuer, Identity.subject == claims.subject)
            .with_for_update()
        ).scalar_one_or_none()
        if grant.kind != GRANT_KIND_ACCOUNT_LINK:
            # Invitations need a verified, matching email: accept them at
            # /auth/invitations/accept (invitation_service), never here.
            self._refuse(
                db,
                claims,
                "invitation_requires_acceptance",
                409,
                "Open the invitation link to accept this invitation.",
                grant_id=grant.id,
            )
        if identity is not None and identity.user_id is not None:
            self._refuse(
                db,
                claims,
                "identity_already_bound",
                409,
                "This sign-in is already linked to a SIE account.",
                grant_id=grant.id,
            )
        grant_id = grant.id  # readable after a failed flush, unlike grant.id
        try:
            user = self._account_link_target(db, claims, grant)

            if identity is None:
                identity = Identity(
                    user_id=user.id,
                    subject=claims.subject,
                    issuer=claims.issuer,
                    email=claims.email,
                    display_name=claims.display_name,
                    provider=claims.provider,
                )
            else:
                identity.user_id = user.id  # orphan recovery
            identity.last_authenticated_at = utcnow()
            db.add(identity)
            db.flush()

            grant.redeemed_at = utcnow()
            grant.status = STATUS_ACCEPTED
            grant.redeemed_identity_id = identity.id
            grant.target_user_id = user.id
            db.add(grant)
            audit_service.log(
                db,
                action=AuditAction.IDENTITY_LINKED,
                resource_type="Identity",
                resource_id=identity.id,
                organization_id=grant.organization_id,
                user_id=user.id,
                metadata={
                    "issuer": claims.issuer,
                    "provider": claims.provider,
                    "method": grant.kind.lower(),
                    "grant_id": str(grant.id),
                    "subject_fingerprint": subject_fingerprint(claims.issuer, claims.subject),
                },
                commit=False,
            )
            db.commit()
        except IntegrityError:
            # A concurrent redemption bound this identity or created this
            # email first; the database's unique constraint caught it.
            self._refuse(
                db,
                claims,
                "concurrent_conflict",
                409,
                "This sign-in or account was linked by a concurrent request. Try signing in again.",
                grant_id=grant_id,
            )
        return user, grant

    def _account_link_target(self, db: Session, claims: ExternalIdentityClaims, grant: IdentityLinkGrant) -> User:
        # Lock the target row: concurrent links for one user then run the
        # "already bound for this issuer" check one at a time.
        user = db.execute(
            select(User)
            .where(User.id == grant.target_user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if user is None:
            self._refuse(
                db, claims, "grant_invalid_or_expired", 404, "This code is invalid or has expired.", grant_id=grant.id
            )
        if user.platform_role is not None and not grant.allows_platform_admin:
            # E.g. the user was promoted after the grant was issued.
            self._refuse(
                db,
                claims,
                "target_is_platform_admin",
                403,
                "This code cannot link a platform administrator account.",
                grant_id=grant.id,
                user_id=user.id,
            )
        if user.status != "active":
            self._refuse(
                db,
                claims,
                "target_user_inactive",
                403,
                "The target account is not active.",
                grant_id=grant.id,
                user_id=user.id,
            )
        if user_has_identity_for_issuer(db, user_id=user.id, issuer=claims.issuer):
            self._refuse(
                db,
                claims,
                "target_already_bound_for_issuer",
                409,
                "That account is already linked to a different sign-in from this provider.",
                grant_id=grant.id,
                user_id=user.id,
            )
        return user

    def _refuse(
        self,
        db: Session,
        claims: ExternalIdentityClaims,
        reason: str,
        status_code: int,
        message: str,
        *,
        grant_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ):
        db.rollback()
        log_link_rejection(
            db, issuer=claims.issuer, subject=claims.subject, reason=reason, user_id=user_id, grant_id=grant_id
        )
        raise GrantRedemptionError(reason, status_code, message)


identity_link_service = IdentityLinkService()
