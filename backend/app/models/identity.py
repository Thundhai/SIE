"""Identity — a link from one external, provider-issued identity to (at
most) one SIE User.

This is the "External Identity" half of:

    External Identity -> Identity Resolver -> SIE User -> Organization
    Membership -> Tenant Context

An `Identity` row is created by `app/services/identity_service.py`'s
resolver once it has (already-verified) claims from an identity provider —
this table does not verify anything itself, it only records the result of
a verification that happened elsewhere. See that module for the
`TokenVerifier` interface boundary future real OIDC verification plugs
into.

`(issuer, subject)` is the standard OIDC identity key: a `subject` (the
"sub" claim) is only guaranteed unique *within* one `issuer` (the "iss"
claim) — the same subject value from two different issuers are unrelated
identities. `provider` is a separate, human-facing label (e.g. "google",
"azuread", "dev") for display/filtering; `issuer` is the actual trust
boundary.

`user_id` is nullable to leave room for a future flow where an Identity
is recorded before a User decision is finalized (e.g. an
invite-pending state); the resolver in this milestone always links a
User synchronously, so it is never actually null in current code paths.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Identity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_identities_issuer_subject"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # e.g. "google", "azuread", "dev" — a free-form label, not a fixed set
    # of supported providers (SIE has no hard dependency on any one IdP).
    provider: Mapped[str] = mapped_column(String(100), nullable=False)

    last_authenticated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User | None"] = relationship(back_populates="identities")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Identity id={self.id!s} provider={self.provider!r} "
            f"issuer={self.issuer!r} subject={self.subject!r}>"
        )
