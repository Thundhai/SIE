"""Invitation-based registration: the one way a new person joins an
organization, and the way an existing SIE user joins another one.

Built on `identity_link_grants` (kind INVITATION); see
app/models/identity_link_grant.py for the lifecycle. Account-link grants
stay in identity_link_service.py.

Acceptance (`accept`) is one transaction, with the grant row and the
caller's identity row locked:

* **New user.** The caller's (issuer, subject) is not bound yet. The
  issuer must be trusted to verify email (`OIDC_EMAIL_LINKING_TRUSTED_ISSUERS`),
  `email_verified` must be true, and the email must equal the invited one.
  If any SIE user already has that email, acceptance is refused: that
  person signs in with their existing linked identity instead. No email
  ever attaches a new identity to an existing account.
* **Existing user.** The caller's identity is already bound to an active
  user whose email equals the invited one. Only a membership is added;
  no identity moves, and an existing membership in that organization
  (any status) is left alone and the invitation refused.

Either way the organization and role come from the invitation, never the
request. A mismatched email counts as a failed attempt; after
`INVITATION_MAX_FAILED_ATTEMPTS` the invitation is revoked. Codes are 256
bits, stored only as SHA-256 hashes, shown once, and replaced on resend.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.base import utcnow
from app.models.enums import MembershipStatus
from app.models.identity import Identity
from app.models.identity_link_grant import (
    GRANT_KIND_INVITATION,
    OPEN_STATUSES,
    STATUS_ACCEPTED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_REGISTRATION_STARTED,
    STATUS_REVOKED,
    STATUS_VERIFIED,
    IdentityLinkGrant,
)
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services.audit_service import AuditAction, audit_service
from app.services.identity_link_service import CreatedGrant, _is_expired, _new_code, hash_code
from app.services.identity_service import ExternalIdentityClaims, subject_fingerprint
from app.services.permissions import ROLE_PERMISSIONS, OrganizationRole, Permission
from app.services.verified_email import (
    SOURCE_USERINFO_INSECURE,
    SOURCE_USERINFO_SUBJECT_MISMATCH,
    SOURCE_USERINFO_UNAVAILABLE,
    VerifiedEmail,
)

METHODS = ("password", "sso")


class InvitationError(Exception):
    """`reason` is a fixed code the frontend switches on; `status_code`
    is the HTTP status."""

    def __init__(self, reason: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class InvitationView:
    """What the holder of a valid code may see before signing in."""

    status: str
    organization_id: uuid.UUID
    organization_name: str
    role: str
    invited_email: str
    expires_at: object


@dataclass(frozen=True)
class AcceptedInvitation:
    user: User
    organization_id: uuid.UUID
    role: str
    outcome: str  # "account_created" | "existing_account"


def effective_status(grant: IdentityLinkGrant) -> str:
    if grant.status in OPEN_STATUSES and _is_expired(grant.expires_at):
        return STATUS_EXPIRED
    return grant.status


def _email_taken(db: Session, email: str) -> bool:
    return db.execute(select(User.id).where(func.lower(User.email) == email).limit(1)).first() is not None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _ttl(hours: int | None) -> timedelta:
    return timedelta(hours=hours or settings.IDENTITY_LINK_GRANT_TTL_HOURS)


class InvitationService:
    # --- Administrator operations (caller already holds users:manage in the org) ----

    def create(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        email: str,
        role: OrganizationRole,
        actor_user_id: uuid.UUID,
        actor_permissions: frozenset[Permission],
        expires_in_hours: int | None = None,
    ) -> CreatedGrant:
        if db.get(Organization, organization_id) is None:
            raise InvitationError("organization_not_found", 404, "Organization not found.")
        if not ROLE_PERMISSIONS[role] <= actor_permissions:
            # Nobody can hand out more than they hold.
            raise InvitationError(
                "role_exceeds_authority", 403, "You cannot invite someone to a role with permissions you don't have."
            )
        email = _normalize_email(email)
        member = db.execute(
            select(OrganizationMembership.id)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(OrganizationMembership.organization_id == organization_id, func.lower(User.email) == email)
        ).first()
        if member is not None:
            raise InvitationError("already_member", 409, "This person already has a membership in this organization.")
        self._expire_stale(db, organization_id=organization_id, email=email)
        code = _new_code()
        grant = IdentityLinkGrant(
            kind=GRANT_KIND_INVITATION,
            token_sha256=hash_code(code),
            organization_id=organization_id,
            role=role.value,
            invited_email=email,
            created_by_user_id=actor_user_id,
            expires_at=utcnow() + _ttl(expires_in_hours),
            status=STATUS_PENDING,
        )
        db.add(grant)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise InvitationError(
                "open_invitation_exists", 409, "An open invitation for this email already exists. Resend it instead."
            ) from None
        self._audit(db, AuditAction.INVITATION_CREATED, grant, actor_user_id, {"role": grant.role})
        db.commit()
        return CreatedGrant(grant=grant, code=code)

    def list(self, db: Session, *, organization_id: uuid.UUID, status: str | None = None) -> list[IdentityLinkGrant]:
        rows = (
            db.execute(
                select(IdentityLinkGrant)
                .where(
                    IdentityLinkGrant.kind == GRANT_KIND_INVITATION,
                    IdentityLinkGrant.organization_id == organization_id,
                )
                .order_by(IdentityLinkGrant.created_at.desc())
            )
            .scalars()
            .all()
        )
        if status is not None:
            rows = [r for r in rows if effective_status(r) == status]
        return rows

    def get(self, db: Session, *, organization_id: uuid.UUID, invitation_id: uuid.UUID) -> IdentityLinkGrant:
        grant = db.execute(
            select(IdentityLinkGrant).where(
                IdentityLinkGrant.id == invitation_id,
                IdentityLinkGrant.organization_id == organization_id,  # tenant isolation
                IdentityLinkGrant.kind == GRANT_KIND_INVITATION,
            )
        ).scalar_one_or_none()
        if grant is None:
            raise InvitationError("invitation_not_found", 404, "Invitation not found.")
        return grant

    def resend(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        expires_in_hours: int | None = None,
    ) -> CreatedGrant:
        """A new code and expiry. The old link stops working at once."""
        grant = self._get_for_update(db, organization_id=organization_id, invitation_id=invitation_id)
        state = effective_status(grant)
        if state in (STATUS_ACCEPTED, STATUS_REVOKED):
            raise InvitationError(f"invitation_{state.lower()}", 409, f"This invitation is {state.lower()}.")
        # A newer invitation for this email that has itself expired must not
        # keep the open slot and block reopening this one.
        self._expire_stale(
            db, organization_id=grant.organization_id, email=grant.invited_email, exclude_id=grant.id
        )
        code = _new_code()
        grant.token_sha256 = hash_code(code)
        grant.expires_at = utcnow() + _ttl(expires_in_hours)
        grant.status = STATUS_PENDING
        grant.registration_started_at = None
        grant.verified_at = None
        grant.failed_attempts = 0
        grant.issue_count = (grant.issue_count or 1) + 1
        db.add(grant)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise InvitationError(
                "open_invitation_exists", 409, "Another open invitation exists for this email."
            ) from None
        self._audit(db, AuditAction.INVITATION_RESENT, grant, actor_user_id, {"issue_count": grant.issue_count})
        db.commit()
        return CreatedGrant(grant=grant, code=code)

    def revoke(
        self, db: Session, *, organization_id: uuid.UUID, invitation_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> IdentityLinkGrant:
        grant = self._get_for_update(db, organization_id=organization_id, invitation_id=invitation_id)
        if grant.status == STATUS_ACCEPTED:
            raise InvitationError("invitation_accepted", 409, "An accepted invitation cannot be revoked.")
        if grant.status != STATUS_REVOKED:
            grant.status = STATUS_REVOKED
            grant.revoked_at = utcnow()
            grant.revoked_by_user_id = actor_user_id
            db.add(grant)
            self._audit(db, AuditAction.INVITATION_REVOKED, grant, actor_user_id, {"reason": "administrator"})
        db.commit()
        return grant

    # --- Public (code holder, not signed in) -------------------------------------------

    def inspect(self, db: Session, *, code: str) -> InvitationView:
        grant = self._by_code(db, code)
        return self._view(db, grant)

    def start(self, db: Session, *, code: str, method: str) -> InvitationView:
        grant = self._by_code(db, code, for_update=True)
        if effective_status(grant) == STATUS_PENDING:
            grant.status = STATUS_REGISTRATION_STARTED
            grant.registration_started_at = utcnow()
            db.add(grant)
            self._audit(db, AuditAction.INVITATION_REGISTRATION_STARTED, grant, None, {"method": method})
            db.commit()
        else:
            db.rollback()
        return self._view(db, grant)

    # --- Acceptance (signed in with the identity provider) ------------------------------

    def accept(
        self,
        db: Session,
        *,
        claims: ExternalIdentityClaims,
        verified: VerifiedEmail,
        code: str,
        full_name: str | None = None,
    ) -> AcceptedInvitation:
        grant = self._by_code(db, code, for_update=True, claims=claims)
        grant_id, org_id = grant.id, grant.organization_id
        state = effective_status(grant)
        if state == STATUS_ACCEPTED:
            self._refuse(
                db, claims, grant_id, org_id, "invitation_already_used", 410, "This invitation has already been used."
            )
        if state == STATUS_REVOKED:
            self._refuse(db, claims, grant_id, org_id, "invitation_revoked", 410, "This invitation has been revoked.")
        if state == STATUS_EXPIRED:
            self._refuse(
                db,
                claims,
                grant_id,
                org_id,
                "invitation_expired",
                410,
                "This invitation has expired.",
                after=lambda g: setattr(g, "status", STATUS_EXPIRED),
                expected_hash=grant.token_sha256,
            )

        identity = db.execute(
            select(Identity)
            .where(Identity.issuer == claims.issuer, Identity.subject == claims.subject)
            .with_for_update()
        ).scalar_one_or_none()

        try:
            if identity is not None and identity.user_id is not None:
                user = self._existing_account(db, claims, verified, grant, identity)
                outcome = "existing_account"
            elif identity is not None:
                self._refuse(
                    db,
                    claims,
                    grant_id,
                    org_id,
                    "orphaned_identity_requires_account_link",
                    409,
                    "This sign-in needs an account-link code from an administrator.",
                )
            else:
                user, identity = self._new_account(db, claims, verified, grant, full_name)
                outcome = "account_created"

            existing_membership = db.execute(
                select(OrganizationMembership.id).where(
                    OrganizationMembership.user_id == user.id, OrganizationMembership.organization_id == org_id
                )
            ).first()
            if existing_membership is not None:
                self._refuse(
                    db,
                    claims,
                    grant_id,
                    org_id,
                    "membership_exists",
                    409,
                    "You already have a membership in this organization. Ask its administrator.",
                )

            now = utcnow()
            grant.status = STATUS_VERIFIED
            grant.verified_at = now
            membership = OrganizationMembership(
                organization_id=org_id, user_id=user.id, role=grant.role, status=MembershipStatus.ACTIVE
            )
            db.add(membership)
            db.flush()
            grant.status = STATUS_ACCEPTED
            grant.redeemed_at = now
            grant.target_user_id = user.id
            grant.redeemed_identity_id = identity.id
            grant.accepted_membership_id = membership.id
            db.add(grant)
            fingerprint = subject_fingerprint(claims.issuer, claims.subject)
            if outcome == "account_created":
                audit_service.log(
                    db,
                    action=AuditAction.IDENTITY_LINKED,
                    resource_type="Identity",
                    resource_id=identity.id,
                    organization_id=org_id,
                    user_id=user.id,
                    metadata={
                        "issuer": claims.issuer,
                        "provider": claims.provider,
                        "method": "invitation",
                        "grant_id": str(grant_id),
                        "subject_fingerprint": fingerprint,
                        "email_source": verified.source,
                    },
                    commit=False,
                )
            audit_service.log(
                db,
                action=AuditAction.MEMBER_ADDED,
                resource_type="OrganizationMembership",
                resource_id=membership.id,
                organization_id=org_id,
                user_id=grant.created_by_user_id,
                metadata={"member_user_id": str(user.id), "role": grant.role, "via": "invitation"},
                commit=False,
            )
            self._audit(
                db,
                AuditAction.INVITATION_ACCEPTED,
                grant,
                user.id,
                {"outcome": outcome, "role": grant.role, "member_user_id": str(user.id)},
            )
            db.commit()
        except IntegrityError:
            self._refuse(
                db,
                claims,
                grant_id,
                org_id,
                "concurrent_conflict",
                409,
                "This invitation or account changed during a concurrent request. Try again.",
            )
        return AcceptedInvitation(user=user, organization_id=org_id, role=grant.role, outcome=outcome)

    def _existing_account(
        self,
        db: Session,
        claims: ExternalIdentityClaims,
        verified: VerifiedEmail,
        grant: IdentityLinkGrant,
        identity: Identity,
    ) -> User:
        user = db.execute(
            select(User).where(User.id == identity.user_id).with_for_update().execution_options(populate_existing=True)
        ).scalar_one()
        if user.status != "active":
            self._refuse(
                db,
                claims,
                grant.id,
                grant.organization_id,
                "account_inactive",
                403,
                "Your SIE account is not active.",
                user_id=user.id,
            )
        if user.email.strip().lower() != grant.invited_email:
            self._refuse_mismatch(db, claims, grant, user_id=user.id)
        self._require_verified_invited_email(db, claims, verified, grant, user_id=user.id)
        return user

    def _require_verified_invited_email(
        self,
        db: Session,
        claims: ExternalIdentityClaims,
        verified: VerifiedEmail,
        grant: IdentityLinkGrant,
        *,
        user_id: uuid.UUID | None = None,
    ) -> None:
        """This sign-in must itself prove the invited email: a trusted
        issuer, `email_verified` true, and that exact address. Required on
        both paths, because an existing account's own email may have come
        from an unverified claim (accounts provisioned before #69)."""
        grant_id, org_id = grant.id, grant.organization_id
        mark_started = self._mark_started
        if claims.issuer not in settings.oidc_email_linking_trusted_issuers:
            self._refuse(
                db,
                claims,
                grant_id,
                org_id,
                "issuer_not_trusted_for_email",
                403,
                "This sign-in provider is not trusted to verify email for invitations.",
                user_id=user_id,
                after=mark_started,
                expected_hash=grant.token_sha256,
            )
        if verified.source == SOURCE_USERINFO_UNAVAILABLE:
            # The provider could not be asked. Nothing is verified (fail
            # closed), but this is retryable: no attempt is counted.
            self._refuse(
                db,
                claims,
                grant_id,
                org_id,
                "email_verification_unavailable",
                503,
                "Your email could not be verified with your sign-in provider right now. Try again shortly.",
                user_id=user_id,
            )
        if verified.source in (SOURCE_USERINFO_SUBJECT_MISMATCH, SOURCE_USERINFO_INSECURE):
            self._refuse(
                db,
                claims,
                grant_id,
                org_id,
                "email_verification_failed",
                403,
                "Your email could not be verified with your sign-in provider.",
                user_id=user_id,
            )
        if not verified.email:
            self._refuse(
                db,
                claims,
                grant_id,
                org_id,
                "email_claim_missing",
                403,
                "Your sign-in did not provide an email address.",
                user_id=user_id,
                after=mark_started,
                expected_hash=grant.token_sha256,
            )
        if verified.email_verified is not True:
            self._refuse(
                db,
                claims,
                grant_id,
                org_id,
                "email_not_verified",
                403,
                "Verify your email address with your sign-in provider, then sign in again.",
                user_id=user_id,
                after=mark_started,
                expected_hash=grant.token_sha256,
            )
        if verified.email.strip().lower() != grant.invited_email:
            self._refuse_mismatch(db, claims, grant, user_id=user_id)

    def _new_account(
        self,
        db: Session,
        claims: ExternalIdentityClaims,
        verified: VerifiedEmail,
        grant: IdentityLinkGrant,
        full_name: str | None,
    ) -> tuple[User, Identity]:
        grant_id, org_id = grant.id, grant.organization_id
        self._require_verified_invited_email(db, claims, verified, grant)
        if _email_taken(db, grant.invited_email):
            self._refuse(
                db,
                claims,
                grant_id,
                org_id,
                "existing_account_sign_in_required",
                409,
                "An SIE account with this email already exists. Sign in with that account to accept.",
            )
        name = (full_name or "").strip() or claims.display_name or grant.invited_email
        user = User(email=grant.invited_email, name=name[:255])
        db.add(user)
        db.flush()
        identity = Identity(
            user_id=user.id,
            subject=claims.subject,
            issuer=claims.issuer,
            email=verified.email,
            display_name=claims.display_name[:255] if claims.display_name else None,
            provider=claims.provider,
            last_authenticated_at=utcnow(),
        )
        db.add(identity)
        db.flush()
        return user, identity

    # --- helpers -----------------------------------------------------------------------

    @staticmethod
    def _mark_started(grant: IdentityLinkGrant) -> None:
        if grant.status == STATUS_PENDING:
            grant.status = STATUS_REGISTRATION_STARTED
            grant.registration_started_at = utcnow()

    def _refuse_mismatch(
        self, db: Session, claims: ExternalIdentityClaims, grant: IdentityLinkGrant, *, user_id: uuid.UUID | None = None
    ):
        limit = settings.INVITATION_MAX_FAILED_ATTEMPTS

        def count(g: IdentityLinkGrant) -> None:
            g.failed_attempts = (g.failed_attempts or 0) + 1
            if g.failed_attempts >= limit:
                g.status = STATUS_REVOKED
                g.revoked_at = utcnow()

        self._refuse(
            db,
            claims,
            grant.id,
            grant.organization_id,
            "email_mismatch",
            403,
            "This invitation was sent to a different email address.",
            user_id=user_id,
            after=count,
            expected_hash=grant.token_sha256,
        )

    def _refuse(
        self,
        db: Session,
        claims: ExternalIdentityClaims | None,
        grant_id: uuid.UUID | None,
        organization_id: uuid.UUID | None,
        reason: str,
        status_code: int,
        message: str,
        *,
        user_id: uuid.UUID | None = None,
        after: Callable[[IdentityLinkGrant], None] | None = None,
        expected_hash: str | None = None,
    ):
        """Roll back, apply `after` to the grant (a state change that must
        persist even though the request is refused), audit, raise.

        The rollback releases the row lock, so the grant is re-locked and
        `after` applies only if it still carries the same code
        (`expected_hash`) and is still open. A resend, revoke or acceptance
        that landed in between is never overwritten."""
        db.rollback()
        metadata: dict = {"reason": reason}
        if claims is not None:
            metadata["issuer"] = claims.issuer
            metadata["subject_fingerprint"] = subject_fingerprint(claims.issuer, claims.subject)
        if grant_id is not None and after is not None:
            grant = db.execute(
                select(IdentityLinkGrant)
                .where(
                    IdentityLinkGrant.id == grant_id,
                    IdentityLinkGrant.token_sha256 == expected_hash,
                    IdentityLinkGrant.status.in_(OPEN_STATUSES),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if grant is not None:
                after(grant)
                db.add(grant)
                if grant.status == STATUS_REVOKED:
                    metadata["auto_revoked"] = True
        if grant_id is not None:
            metadata["grant_id"] = str(grant_id)
        audit_service.log(
            db,
            action=AuditAction.INVITATION_REJECTED,
            resource_type="IdentityLinkGrant",
            resource_id=grant_id,
            organization_id=organization_id,
            user_id=user_id,
            metadata=metadata,
        )
        raise InvitationError(reason, status_code, message)

    def _by_code(
        self, db: Session, code: str, *, for_update: bool = False, claims: ExternalIdentityClaims | None = None
    ) -> IdentityLinkGrant:
        stmt = select(IdentityLinkGrant).where(
            IdentityLinkGrant.token_sha256 == hash_code(code), IdentityLinkGrant.kind == GRANT_KIND_INVITATION
        )
        if for_update:
            stmt = stmt.with_for_update()
        grant = db.execute(stmt).scalar_one_or_none()
        if grant is None:
            self._refuse(db, claims, None, None, "invitation_not_found", 404, "This invitation link is not valid.")
        return grant

    def _get_for_update(
        self, db: Session, *, organization_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> IdentityLinkGrant:
        grant = db.execute(
            select(IdentityLinkGrant)
            .where(
                IdentityLinkGrant.id == invitation_id,
                IdentityLinkGrant.organization_id == organization_id,  # tenant isolation
                IdentityLinkGrant.kind == GRANT_KIND_INVITATION,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if grant is None:
            raise InvitationError("invitation_not_found", 404, "Invitation not found.")
        return grant

    def _expire_stale(
        self, db: Session, *, organization_id: uuid.UUID, email: str, exclude_id: uuid.UUID | None = None
    ) -> None:
        """Mark this organization's past-expiry, still-open invitations for
        `email` EXPIRED, so they no longer hold the one-open-invitation
        slot. `exclude_id` is the invitation being reopened, if any."""
        conditions = [
            IdentityLinkGrant.kind == GRANT_KIND_INVITATION,
            IdentityLinkGrant.organization_id == organization_id,
            IdentityLinkGrant.invited_email == email,
            IdentityLinkGrant.status.in_(OPEN_STATUSES),
            IdentityLinkGrant.expires_at <= utcnow(),
        ]
        if exclude_id is not None:
            conditions.append(IdentityLinkGrant.id != exclude_id)
        db.execute(
            update(IdentityLinkGrant)
            .where(*conditions)
            .values(status=STATUS_EXPIRED)
            .execution_options(synchronize_session=False)
        )

    def _view(self, db: Session, grant: IdentityLinkGrant) -> InvitationView:
        org = db.get(Organization, grant.organization_id)
        return InvitationView(
            status=effective_status(grant),
            organization_id=grant.organization_id,
            organization_name=org.name if org is not None else "",
            role=grant.role,
            invited_email=grant.invited_email,
            expires_at=grant.expires_at,
        )

    def _audit(
        self, db: Session, action: str, grant: IdentityLinkGrant, actor_user_id: uuid.UUID | None, extra: dict
    ) -> None:
        audit_service.log(
            db,
            action=action,
            resource_type="IdentityLinkGrant",
            resource_id=grant.id,
            organization_id=grant.organization_id,
            user_id=actor_user_id,
            metadata={"grant_id": str(grant.id), **extra},
            commit=False,
        )


invitation_service = InvitationService()
