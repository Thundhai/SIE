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

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

GRANT_KIND_INVITATION = "INVITATION"
GRANT_KIND_ACCOUNT_LINK = "ACCOUNT_LINK"


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
    # The new user's email. Admin-entered, never compared with a token's claim.
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

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IdentityLinkGrant id={self.id!s} kind={self.kind!r}>"
