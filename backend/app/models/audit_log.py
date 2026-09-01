"""AuditLog — a minimal, append-only record of administrative and
security-relevant actions.

Deliberately not an event-streaming system: one table, written to
synchronously by `app/services/audit_service.py` in the same request as
the action it records. That is the right amount of structure for this
milestone; a real event bus, retries, or async delivery are not part of
it.

`organization_id` and `user_id` are both nullable and both
`ON DELETE SET NULL` (not CASCADE, unlike most FKs in this codebase): an
audit row is a historical record and should outlive the organization or
user it refers to, rather than disappearing when they're deleted — the
opposite tradeoff from, say, a Site or KnowledgeDocument, which really are
owned by their organization and should go with it.

Per the security requirements for this milestone, nothing about
authentication credentials is ever recorded here: `metadata` must never
contain a password, token, or secret. There is no code path in this
codebase that would put one there today (SIE stores none of those), but
future callers of `AuditService.log()` must keep it that way.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, utcnow

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Free-form, e.g. "MEMBER_ADDED", "KNOWLEDGE_SOURCE_CREATED" — see
    # app/services/audit_service.py::AuditAction for the known values in
    # use today. Not a native DB enum: new action types are expected to be
    # added routinely as more of the system is wired up to audit logging.
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # The originating HTTP request's id (Intelligence Platform Integration
    # v0.1, item 11: "associated with audit events"). Nullable -- audit
    # rows written outside an HTTP request (a direct service/script call,
    # as most of this codebase's own tests exercise) simply have none;
    # this is traceability, never a join key anything depends on.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Structured context for the action (e.g. {"role": "ORG_ADMIN"} for a
    # MEMBER_ADDED event). Never a credential — see module docstring.
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", _JSONType, nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AuditLog id={self.id!s} action={self.action!r} "
            f"resource_type={self.resource_type!r} resource_id={self.resource_id!s}>"
        )
