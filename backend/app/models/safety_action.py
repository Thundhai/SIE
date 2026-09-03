"""SafetyAction — SIE Milestone 17: Actions & Intervention Foundation
v0.1. The first persisted record of a governed safety action: something
an organization has decided to *do* (a corrective action, a preventive
measure, a follow-up), as distinct from `SafetyEvent` (what *happened*).

    SafetyEvent (optional) -> SafetyAction -> SafetyActionHistory
                                            -> AuditLog

**Governed vocabularies, unlike SafetyEvent.** `status`/`priority`/
`action_type` are native PostgreSQL enums (see
`app/models/safety_action_enums.py`'s own docstring for why this is safe
here, unlike the free-text choice `SafetyEvent.event_type` deliberately
makes) — the milestone spec is explicit that these need real, enforced
structure (a transition matrix, a closed priority scale), not an
open-ended vocabulary expected to grow via data alone.

**Every action belongs to exactly one organization** (`OrganizationScopedMixin`)
— no second tenant model, no GLOBAL action. `site_id`/`source_event_id`/
`owner_user_id` are all nullable *foreign keys already validated, at
write time, to belong to that same organization* by
`app/services/safety_action_service.py` — the columns themselves don't
enforce that (a plain FK can't express "same organization_id as this
row"), which is exactly why that validation exists as real application
code, not just documented expectation. `ON DELETE SET NULL` for all
three: an action must never be deleted merely because the site/event it
referenced, or the user it was assigned to, was later removed — the
action (and its audit trail) survives; only the reference is cleared.

**`created_by_user_id` vs. `created_by_api_client_id`.** Exactly one of
these is set (the other stays NULL) depending on whether a human or a
machine client created the row — mirrors `RequestContext.kind`
(`app/api/deps_context.py`). Both nullable and `ON DELETE SET NULL`,
matching `AuditLog`'s own precedent: the action is a historical record
that should outlive the user or credential that created it.

**Closure semantics — read this before assuming `COMPLETED` means more
than it does.** `COMPLETED` means "an authorized actor marked this done."
It is not, and must never be treated as, SIE independently verifying
that a hazard was eliminated or that the underlying risk is actually
gone — there is no effectiveness-verification mechanism in this
milestone (see `app/api/v1/actions.py`'s own docstring, §17/§18 of the
milestone spec). `completed_at`/`cancelled_at` are set by the service
layer alone, on a valid transition — never accepted as client input (see
`app/schemas/actions.py::SafetyActionUpdate`, which does not carry
either field).
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.safety_action_enums import ActionPriority, ActionStatus, ActionType

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class SafetyAction(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "safety_actions"
    __table_args__ = (
        # Composite indexes for the milestone's own explicitly-named
        # "common enterprise queries" (§20) -- every one of these mirrors
        # a real GET /actions filter (app/api/v1/actions.py), always
        # anchored on organization_id first since every query is
        # tenant-scoped.
        Index("ix_safety_actions_org_status", "organization_id", "status"),
        Index("ix_safety_actions_org_priority", "organization_id", "priority"),
        Index("ix_safety_actions_org_owner", "organization_id", "owner_user_id"),
        Index("ix_safety_actions_org_site", "organization_id", "site_id"),
        Index("ix_safety_actions_org_source_event", "organization_id", "source_event_id"),
        Index("ix_safety_actions_due_date", "due_date"),
    )

    site_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("safety_events.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    action_type: Mapped[ActionType] = mapped_column(
        SAEnum(ActionType, name="safety_action_type", native_enum=True), nullable=False
    )
    priority: Mapped[ActionPriority] = mapped_column(
        SAEnum(ActionPriority, name="safety_action_priority", native_enum=True),
        nullable=False,
        default=ActionPriority.MEDIUM,
    )
    status: Mapped[ActionStatus] = mapped_column(
        SAEnum(ActionStatus, name="safety_action_status", native_enum=True),
        nullable=False,
        default=ActionStatus.OPEN,
        index=True,
    )

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    # Set only by the status-transition service function, on a valid
    # transition into the matching terminal state -- never client input
    # (see module docstring's "Closure semantics").
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Caller-supplied external system reference (e.g. a CMMS work order
    # id) -- like SafetyEvent.correlation_id, purely a pass-through
    # provenance field, never interpreted or validated by SIE itself.
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Bounded, domain-specific structured data -- see
    # app/schemas/actions.py's own size-limit validator. The same
    # "don't force a migration for every new field" tradeoff
    # SafetyEvent.attributes already documents.
    attributes: Mapped[dict] = mapped_column(_JSONType, nullable=False, default=dict)

    organization: Mapped["Organization"] = relationship()  # noqa: F821
    site: Mapped["Site | None"] = relationship()  # noqa: F821
    source_event: Mapped["SafetyEvent | None"] = relationship()  # noqa: F821
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_user_id])  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SafetyAction id={self.id!s} organization_id={self.organization_id!s} "
            f"status={self.status!s} title={self.title!r}>"
        )
