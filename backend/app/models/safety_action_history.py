"""SafetyActionHistory — SIE Milestone 17: Actions & Intervention
Foundation v0.1 (§12). An immutable, append-only audit trail for one
`SafetyAction`'s own lifecycle — distinct from, and complementary to,
`AuditLog` (see `app/services/safety_action_service.py`'s own docstring
for why both exist: this table is the *domain* history a client renders
as "what happened to this action" scoped to one action id; `AuditLog` is
the platform-wide security/administrative log every other milestone
already writes to).

**Immutable by convention, not by a database trigger.** No route in
`app/api/v1/actions.py` ever issues an `UPDATE` or `DELETE` against this
table — every row is written once, by
`app/services/safety_action_service.py::record_history()`, and never
touched again. This is the same "one write path, no route accepts it as
editable input" guarantee `AuditLog` already relies on (see that model's
own docstring), applied to a second table.

**Tenant-scoped, like every other organization-owned table**
(`OrganizationScopedMixin`) — a history row is never returned across an
organization boundary; see `app/api/v1/actions.py`'s tenant-isolation
tests. `ON DELETE CASCADE` on `organization_id` (unlike `AuditLog`,
which intentionally outlives its organization): a `SafetyActionHistory`
row has no meaning independent of the action and organization it
belongs to, the same reasoning `Site`/`DataSource`/every other
genuinely tenant-owned resource in this schema already follows.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow


class ActionHistoryChangeType:
    """Known `change_type` values — a typo-guard convenience, not an
    enforced enum, mirroring `app.services.audit_service.AuditAction`'s
    own reasoning exactly (the milestone's own §12 list, kept open in
    case a future milestone adds a new kind of change worth recording)."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    ASSIGNED = "ASSIGNED"
    STATUS_CHANGED = "STATUS_CHANGED"


class SafetyActionHistory(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "safety_action_history"

    # `index=True` below already creates `ix_safety_action_history_action_id`
    # -- no separate `__table_args__` Index() for it (that would collide
    # under the same auto-generated name).
    action_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("safety_actions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # A plain string, not a native enum -- see ActionHistoryChangeType's
    # own docstring.
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Stored as plain strings (an ActionStatus value, or NULL), not the
    # native safety_action_status enum type: a history row is meant to
    # remain a faithful record of what the status literally was at the
    # time, independent of whether that value is still considered valid
    # by the current enum definition.
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Exactly one of these is set, mirroring SafetyAction.created_by_*
    # -- see that model's own docstring.
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    # The originating HTTP request's id -- mirrors AuditLog.request_id
    # exactly (app/core/request_id.py); nullable for the same reason
    # (a direct service/test call outside an HTTP request has none).
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    action: Mapped["SafetyAction"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SafetyActionHistory id={self.id!s} action_id={self.action_id!s} "
            f"change_type={self.change_type!r}>"
        )
