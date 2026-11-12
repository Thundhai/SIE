"""Administrator-added users: the way a person joins an organization
without an invitation link.

An administrator (`users:manage` in the organization) enters an email,
an optional name and a role. Then:

1. **SIE already knows the person**, meaning an SIE user has that email, or
   the Auth0 account for that email is already bound to an SIE user (an
   older account whose stored email is a placeholder, say). Only a
   membership is added. Before reusing a bound account, Auth0 must confirm
   it has this email and either verified it or was created by SIE.
2. **Auth0 has a verified account for that email** but SIE doesn't. It is
   bound to a new SIE user. The person signs in with their existing password.
3. **Auth0 has no account for that email.** SIE creates one, with a random
   password nobody is told and `app_metadata.sie_provisioned`, binds it to
   a new SIE user, and asks Auth0 to email a set-password link.

Refusals, all audited as `USER_ADD_REJECTED` with a fixed reason code and
never the email:

* An unverified Auth0 account that SIE didn't create is refused
  (`auth0_account_unverified`). Anyone can sign up with someone else's
  address, so an unverified account proves nothing. Switching off public
  sign-up in Auth0 closes this too.
* Platform-administrator accounts are never touched.
* The role's permissions must be a subset of the administrator's.
* An existing membership is never changed.

Why binding is safe: SIE binds `(OIDC_ISSUER, auth0 user_id)` only to an
Auth0 account that Auth0 says belongs to that email and is either verified
or was created by SIE. A created account starts with a password nobody
knows, so only whoever controls the mailbox can set one and sign in.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.auth0_management import (
    Auth0ManagementClient,
    Auth0ManagementError,
    Auth0User,
)
from app.models.enums import MembershipStatus
from app.models.identity import Identity
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services.audit_service import AuditAction, audit_service
from app.services.identity_service import bounded_display_name, subject_fingerprint
from app.services.permissions import ROLE_PERMISSIONS, OrganizationRole, Permission

logger = logging.getLogger(__name__)

OUTCOME_ACCOUNT_CREATED = "account_created"
OUTCOME_EXISTING_SIGN_IN = "existing_sign_in"
OUTCOME_EXISTING_SIE_ACCOUNT = "existing_sie_account"


class ProvisioningError(Exception):
    def __init__(self, reason: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class AddedUser:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    outcome: str
    # Whether Auth0 accepted the request to email a set-password link. False
    # when no email was needed (an existing sign-in) or sending failed.
    email_sent: bool
    email_failed: bool


def _unavailable() -> ProvisioningError:
    return ProvisioningError(
        "auth0_unavailable", 503, "The sign-in provider could not be reached. Nothing was changed; try again shortly."
    )


class UserProvisioningService:
    def add_user(
        self,
        db: Session,
        client: Auth0ManagementClient | None,
        *,
        organization_id: uuid.UUID,
        email: str,
        name: str | None,
        role: OrganizationRole,
        actor_user_id: uuid.UUID,
        actor_permissions: frozenset[Permission],
    ) -> AddedUser:
        if client is None or not settings.OIDC_ISSUER:
            raise ProvisioningError("not_configured", 501, "Adding users isn't set up on this deployment yet.")
        if db.get(Organization, organization_id) is None:
            raise ProvisioningError("organization_not_found", 404, "Organization not found.")
        if not ROLE_PERMISSIONS[role] <= actor_permissions:
            raise ProvisioningError(
                "role_exceeds_authority", 403, "You cannot add someone with a role that has permissions you don't have."
            )
        email = email.strip().lower()
        name = (name or "").strip() or None
        issuer = settings.OIDC_ISSUER

        matches = db.execute(select(User).where(func.lower(User.email) == email)).scalars().all()
        if len(matches) > 1:
            raise ProvisioningError("ambiguous_email", 409, "More than one SIE account has this email.")
        if matches:
            user = matches[0]
            # Normally one; a second sign-in from the same issuer must not 500.
            identity = db.execute(
                select(Identity)
                .where(Identity.user_id == user.id, Identity.issuer == issuer)
                .order_by(Identity.created_at)
            ).scalars().first()
            if identity is None:
                raise ProvisioningError(
                    "existing_account_unlinked",
                    409,
                    "An SIE account with this email exists but has no sign-in. Ask a platform administrator to link it.",
                )
            auth0_user = self._auth0_get(client, identity.subject)
            if (
                auth0_user is None
                or auth0_user.email != email
                or not (auth0_user.email_verified or auth0_user.sie_provisioned)
            ):
                raise ProvisioningError(
                    "existing_account_unverified",
                    409,
                    "The existing account's email isn't verified with the sign-in provider.",
                )
            return self._add_membership(
                db, user, organization_id=organization_id, role=role, actor_user_id=actor_user_id, issuer=issuer
            )

        auth0_user = self._auth0_find(client, email)
        created = False
        if auth0_user is None:
            auth0_user = self._auth0_create(client, email, name)
            created = True
        elif not auth0_user.email_verified and not auth0_user.sie_provisioned:
            raise ProvisioningError(
                "auth0_account_unverified",
                409,
                "Someone already signed up with this email but never verified it. Ask them to verify it, or delete "
                "that account in Auth0, then try again.",
            )

        bound = db.execute(
            select(Identity).where(Identity.issuer == issuer, Identity.subject == auth0_user.user_id)
        ).scalar_one_or_none()
        if bound is not None:
            if bound.user is None:
                raise ProvisioningError(
                    "orphaned_identity", 409, "This sign-in needs to be relinked. Ask a platform administrator."
                )
            # A known person whose SIE account email differs (e.g. a placeholder).
            return self._add_membership(
                db, bound.user, organization_id=organization_id, role=role, actor_user_id=actor_user_id, issuer=issuer
            )

        user = User(email=email, name=(name or email)[:255])
        db.add(user)
        try:
            db.flush()
            identity = Identity(
                user_id=user.id,
                subject=auth0_user.user_id,
                issuer=issuer,
                email=email,
                display_name=bounded_display_name(name),
                provider=settings.OIDC_PROVIDER_LABEL,
            )
            membership = OrganizationMembership(
                organization_id=organization_id, user_id=user.id, role=role.value, status=MembershipStatus.ACTIVE
            )
            db.add_all([identity, membership])
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ProvisioningError(
                "concurrent_conflict", 409, "This person was added by a concurrent request. Refresh and check."
            ) from None
        needs_password = created or (auth0_user.sie_provisioned and not auth0_user.email_verified)
        outcome = OUTCOME_ACCOUNT_CREATED if needs_password else OUTCOME_EXISTING_SIGN_IN
        audit_service.log(
            db,
            action=AuditAction.IDENTITY_LINKED,
            resource_type="Identity",
            resource_id=identity.id,
            organization_id=organization_id,
            user_id=user.id,
            metadata={
                "issuer": issuer,
                "method": "admin_added",
                "subject_fingerprint": subject_fingerprint(issuer, auth0_user.user_id),
                "auth0_account_created": created,
            },
            commit=False,
        )
        self._audit_added(db, membership, actor_user_id=actor_user_id, outcome=outcome)
        db.commit()

        email_sent = email_failed = False
        if needs_password:
            email_sent = self._send_password_email(client, email)
            email_failed = not email_sent
        return AddedUser(
            user_id=user.id,
            organization_id=organization_id,
            role=role.value,
            outcome=outcome,
            email_sent=email_sent,
            email_failed=email_failed,
        )

    def resend_password_email(
        self,
        db: Session,
        client: Auth0ManagementClient | None,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> None:
        """Ask Auth0 again to email a set-password link, for a member whose
        account SIE created. Raises `ProvisioningError`."""
        if client is None or not settings.OIDC_ISSUER:
            raise ProvisioningError("not_configured", 501, "Adding users isn't set up on this deployment yet.")
        membership = db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,  # tenant isolation
                OrganizationMembership.user_id == user_id,
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ProvisioningError("member_not_found", 404, "This person is not a member of this organization.")
        identity = db.execute(
            select(Identity)
            .where(Identity.user_id == user_id, Identity.issuer == settings.OIDC_ISSUER)
            .order_by(Identity.created_at)
        ).scalars().first()
        auth0_user = self._auth0_get(client, identity.subject) if identity is not None else None
        if auth0_user is None or not auth0_user.sie_provisioned or not auth0_user.email:
            raise ProvisioningError(
                "not_sie_created",
                409,
                "This person's sign-in wasn't created by SIE, so SIE can't send them a set-password email.",
            )
        if not self._send_password_email(client, auth0_user.email):
            raise _unavailable()
        audit_service.log(
            db,
            action=AuditAction.USER_PASSWORD_EMAIL_SENT,
            resource_type="User",
            resource_id=user_id,
            organization_id=organization_id,
            user_id=actor_user_id,
            metadata={"member_user_id": str(user_id)},
        )

    # --- helpers -----------------------------------------------------------------------

    def _add_membership(
        self,
        db: Session,
        user: User,
        *,
        organization_id: uuid.UUID,
        role: OrganizationRole,
        actor_user_id: uuid.UUID,
        issuer: str,
    ) -> AddedUser:
        if user.platform_role is not None:
            raise ProvisioningError(
                "platform_admin_account", 403, "A platform administrator's account can't be added this way."
            )
        if user.status != "active":
            raise ProvisioningError("account_inactive", 409, "This person's SIE account is not active.")
        existing = db.execute(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user.id,
            )
        ).first()
        if existing is not None:
            raise ProvisioningError("already_member", 409, "This person already has a membership in this organization.")
        membership = OrganizationMembership(
            organization_id=organization_id, user_id=user.id, role=role.value, status=MembershipStatus.ACTIVE
        )
        db.add(membership)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ProvisioningError(
                "concurrent_conflict", 409, "This person was added by a concurrent request. Refresh and check."
            ) from None
        self._audit_added(db, membership, actor_user_id=actor_user_id, outcome=OUTCOME_EXISTING_SIE_ACCOUNT)
        db.commit()
        return AddedUser(
            user_id=user.id,
            organization_id=organization_id,
            role=role.value,
            outcome=OUTCOME_EXISTING_SIE_ACCOUNT,
            email_sent=False,
            email_failed=False,
        )

    @staticmethod
    def _audit_added(db: Session, membership: OrganizationMembership, *, actor_user_id: uuid.UUID, outcome: str) -> None:
        audit_service.log(
            db,
            action=AuditAction.MEMBER_ADDED,
            resource_type="OrganizationMembership",
            resource_id=membership.id,
            organization_id=membership.organization_id,
            user_id=actor_user_id,
            metadata={
                "member_user_id": str(membership.user_id),
                "role": membership.role,
                "via": "admin_added",
                "outcome": outcome,
            },
            commit=False,
        )

    @staticmethod
    def _auth0_find(client: Auth0ManagementClient, email: str) -> Auth0User | None:
        try:
            return client.find_user_by_email(email)
        except Auth0ManagementError as exc:
            logger.warning("user_provisioning.auth0_lookup_failed: %s", exc)
            raise _unavailable() from None

    @staticmethod
    def _auth0_get(client: Auth0ManagementClient, user_id: str) -> Auth0User | None:
        try:
            return client.get_user(user_id)
        except Auth0ManagementError as exc:
            logger.warning("user_provisioning.auth0_get_failed: %s", exc)
            raise _unavailable() from None

    @staticmethod
    def _auth0_create(client: Auth0ManagementClient, email: str, name: str | None) -> Auth0User:
        try:
            return client.create_user(email, name)
        except Auth0ManagementError as exc:
            logger.warning("user_provisioning.auth0_create_failed: %s", exc)
            raise _unavailable() from None

    @staticmethod
    def _send_password_email(client: Auth0ManagementClient, email: str) -> bool:
        try:
            client.send_set_password_email(email)
            return True
        except Auth0ManagementError as exc:
            logger.warning("user_provisioning.password_email_failed: %s", exc)
            return False


user_provisioning_service = UserProvisioningService()
