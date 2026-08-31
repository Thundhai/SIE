"""Shared model base and mixins.

`Base` is re-exported from `app.core.database` so there is a single
declarative base for the whole application. Mixins here standardize the
conventions every SIE model follows:

  * UUID primary keys (generated in Python, not by a DB-specific default,
    so it works identically across PostgreSQL and the SQLite engine used
    in tests).
  * UTC created_at / updated_at timestamps.
  * Explicit `organization_id` scoping for every tenant-owned table, via
    `OrganizationScopedMixin`, so ownership is visible on the model itself
    and can never be forgotten when adding a new resource type.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "OrganizationScopedMixin",
    "utcnow",
]


def utcnow() -> datetime:
    """Current UTC time. Shared by every model that needs a raw timestamp
    default outside of `TimestampMixin` (e.g. version rows, which have
    `created_at` but no `updated_at`)."""
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key column named `id`."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Adds UTC `created_at` / `updated_at` columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class OrganizationScopedMixin:
    """Adds a required, indexed, foreign-keyed `organization_id` column.

    Every table that stores organization-owned data must include this
    mixin. It is the schema-level half of SIE's tenant isolation guarantee
    (see app/services/base.py for the query-level half).
    """

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
