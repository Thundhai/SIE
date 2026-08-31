"""User model — a platform-level identity for a person using SIE.

This is a SIE-internal identity record (not a Safelytic or other
external-application account, and not a machine client — see
app/services/identity_service.py and the "human vs. machine callers"
note in the README). It does not store a password or any credential: SIE
does not implement authentication itself, only the identity, membership,
and authorization model that a real OIDC/OAuth2 identity provider's
verified claims resolve into (app/services/identity_service.py).

Design note — why this changed from Foundation v0.1
-----------------------------------------------------
The original User model carried a required `organization_id` (via
`OrganizationScopedMixin`) and a single `role` string, i.e. one user
belonged to exactly one organization with exactly one role. That no
longer matches the milestone's requirement that a user belong to
*multiple* organizations, each with its own role — that per-organization
relationship is now `OrganizationMembership`, the authoritative source of
truth for "does this user have access to this organization, and with what
role" (see app/models/organization_membership.py and
app/services/tenant_context.py). Concretely:

* `organization_id` is kept, but is now nullable and reinterpreted as a
  convenience "default/home organization" (e.g. what to pre-select in a
  UI) — it is never read by the authorization path. This was a deliberate
  choice to preserve the column (and Organization.users, unchanged) rather
  than dropping it outright, since it remains useful as a default and
  removing it is not required to fix the multi-organization limitation.
* `role` is removed. A single per-user role string can't represent "ORG_ADMIN
  in Organization A, VIEWER in Organization B" — that's exactly what
  `OrganizationMembership.role` now holds, per membership.
* `platform_role` is added: the one kind of role that genuinely is global
  to a user rather than scoped to an organization
  (`app.services.permissions.PLATFORM_ADMIN` — see
  app/services/authorization_service.py). Nullable string rather than an
  enum with one member, for the same "don't hard-code a closed set
  prematurely" reasoning as everywhere else in this codebase.
* `email` was previously unique per-organization (a user could
  legitimately be a distinct row in two organizations, same email, before
  multi-org membership existed). It is now unique platform-wide: one User
  row is one platform identity, and `OrganizationMembership` is how that
  one identity relates to many organizations.

See the migration (`migrations/versions/0003_identity_and_access_foundation.py`)
and the README's "Compatibility concerns" notes for the schema-change
details.
"""

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    # Convenience default organization only — never consulted for
    # authorization. See module docstring.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # PLATFORM_ADMIN or NULL today — see app/services/permissions.py.
    platform_role: Mapped[str | None] = mapped_column(String(50), nullable=True)

    organization: Mapped["Organization | None"] = relationship(back_populates="users")  # noqa: F821
    memberships: Mapped[list["OrganizationMembership"]] = relationship(  # noqa: F821
        back_populates="user",
        cascade="all, delete-orphan",
    )
    identities: Mapped[list["Identity"]] = relationship(  # noqa: F821
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def is_platform_admin(self) -> bool:
        from app.services.permissions import PLATFORM_ADMIN

        return self.platform_role == PLATFORM_ADMIN

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id!s} email={self.email!r}>"
