"""One-time grants that bind an external identity (issuer, subject) to a
SIE user. The only ways an unknown identity gets in (see
app/services/identity_link_service.py):

* `INVITATION` -- created by an organization admin. Redeeming it creates
  a *new* user with the invited role in that organization. It never
  attaches to an existing user.
* `ACCOUNT_LINK` -- created by a platform administrator, or by the
  operator script for a platform-administrator target. It names one
  existing user, and redeeming it binds the caller's identity to that
  user: migrating existing accounts, and recovering an identity row whose
  user link was lost.

Only a SHA-256 hash of the one-time code is stored. The code itself is
shown once, at creation, and is never logged.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

GRANT_KIND_INVITATION = "INVITATION"
GRANT_KIND_ACCOUNT_LINK = "ACCOUNT_LINK"

# Lifecycle (app/services/invitation_service.py). PENDING ->
# REGISTRATION_STARTED -> VERIFIED -> ACCEPTED, or EXPIRED / REVOKED.
# EXPIRED is also derived on read from `expires_at`, so a stale row that
# still says PENDING is treated as expired everywhere.
STATUS_PENDING = "PENDING"
STATUS_REGISTRATION_STARTED = "REGISTRATION_STARTED"
STATUS_VERIFIED = "VERIFIED"
STATUS_ACCEPTED = "ACCEPTED"
STATUS_EXPIRED = "EXPIRED"
STATUS_REVOKED = "REVOKED"
OPEN_STATUSES = (STATUS_PENDING, STATUS_REGISTRATION_STARTED, STATUS_VERIFIED)
ALL_STATUSES = (*OPEN_STATUSES, STATUS_ACCEPTED, STATUS_EXPIRED, STATUS_REVOKED)
_OPEN_INVITATION_WHERE = "kind = 'INVITATION' AND status IN ('PENDING', 'REGISTRATION_STARTED', 'VERIFIED')"


class IdentityLinkGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "identity_link_grants"
    __table_args__ = (
        CheckConstraint("kind IN ('INVITATION', 'ACCOUNT_LINK')", name="ck_identity_link_grants_kind"),
        CheckConstraint(
            "(kind = 'INVITATION' AND organization_id IS NOT NULL AND role IS NOT NULL "
            "AND invited_email IS NOT NULL) "
            "OR (kind = 'ACCOUNT_LINK' AND target_user_id IS NOT NULL)",
            name="ck_identity_link_grants_shape",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'REGISTRATION_STARTED', 'VERIFIED', 'ACCEPTED', 'EXPIRED', 'REVOKED')",
            name="ck_identity_link_grants_status",
        ),
        # One open invitation per person per organization.
        Index(
            "uq_identity_link_grants_open_invitation",
            "organization_id",
            "invited_email",
            unique=True,
            postgresql_where=text(_OPEN_INVITATION_WHERE),
            sqlite_where=text(_OPEN_INVITATION_WHERE),
        ),
        Index("ix_identity_link_grants_org_status", "organization_id", "status"),
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # ACCOUNT_LINK: the user being linked. INVITATION: set at redemption to
    # the user it created.
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # INVITATION only.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Lower-cased. Acceptance needs a verified identity email equal to it
    # (new user) or an already-linked account with this email (existing user).
    invited_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # True only for a grant the operator script issued for a platform
    # administrator (scripts/create_identity_link_grant.py). The API never
    # sets it, and redemption refuses a platform-administrator target
    # without it.
    allows_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("identities.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=STATUS_PENDING, server_default=STATUS_PENDING
    )
    registration_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organization_memberships.id", ondelete="SET NULL"), nullable=True
    )
    # How many codes this invitation has had (1 + resends); each resend
    # replaces the stored hash, so only the newest code works.
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Refused acceptances with a mismatched email since the last (re)issue.
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IdentityLinkGrant id={self.id!s} kind={self.kind!r}>"
