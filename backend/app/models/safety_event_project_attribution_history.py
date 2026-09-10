"""SafetyEventProjectAttributionHistory — SIE Milestone 35B: Project
Attribution Temporal Integrity. An immutable, append-only audit trail
of every change to one `SafetyEvent`'s project attribution — mirrors
`RiskAssessmentHistory`/`SafetyActionHistory`'s own established
"domain history, distinct from `AuditLog`" shape almost exactly (see
those models' own docstrings for the identical "two sinks, two
questions" rationale this table follows: `AuditLog` remains the
platform-wide security/administrative log; this table is the domain
history a client would render as "this event's own project-attribution
timeline," and — critically here, unlike either of those two tables —
the mechanism `events_as_of()` itself reads to answer "what was this
event's project attribution *as of* a given instant."

**Why this table exists (SIE Milestone 35A's own gap).** M35A gave
`SafetyEvent.attributed_project_id` — a single current-state column —
and filtered `events_as_of(project_id=...)` on that column directly.
That is correct for "as of right now" but silently wrong for any
historical `as_of`: reassigning an event from Project Alpha (June 20)
to Project Beta (June 25) then asking "Alpha's intelligence as of
June 23" would incorrectly exclude the event (the column now reads
Beta), even though the event genuinely was Alpha's as of that instant.
`SafetyEvent.attributed_project_id` is unchanged and still the fast,
current-state answer every non-temporal read (event detail, `GET
/projects/{id}/events`, the `DELETE` target-match check) uses; this
table is the one place point-in-time reconstruction happens, and it is
the only one required for that — no other table in this codebase grew a
history table this milestone.

**Reconstructing "was event E attributed to project P as of instant T"
(see `app/intelligence/temporal.py::events_as_of()`'s own
implementation).** Find this event's own most recent row with
`created_at <= T` (a plain `created_at`, not a distinct `effective_at` —
see "Why `created_at`, not a separate `effective_at` column" below); if
that row's `action` is `ATTRIBUTED` and its `project_id` is `P`, the
event was P's at instant T. If the most recent qualifying row is
`CLEARED`, or belongs to a different project, or no qualifying row
exists at all (the event has never been attributed, or not yet as of
T), the event is not P's at instant T. `project_id` is never `NULL` on
either kind of row — a `CLEARED` row still names *which* project's
attribution was cleared (useful for an audit trail render, and avoids
overloading `NULL` with two meanings); only `action` distinguishes the
two states.

**Why `created_at`, not a separate `effective_at` column.** Neither
`RiskAssessmentHistory` nor `SafetyActionHistory` — the two existing
precedents inspected before building this table (per this milestone's
own instruction to inspect the existing history architecture first) —
carries a business-time column distinct from row-creation time
anywhere in this codebase; both rely on `created_at` alone as the
instant the recorded change took effect, because every write path that
creates a history row does so synchronously, in the same transaction,
at the moment the change is applied — there is no backdating mechanism
and this milestone does not introduce one speculatively. `created_at`
therefore already *is* this row's effective-time boundary; inventing a
second, always-identical column here would diverge from established
convention without a concrete need. If a future milestone needs
genuine backdated/corrected attribution (an operator asserting "this
was actually true as of an earlier instant"), it can add that column
then, with its own justification.

**No dedicated ordering/sequence tiebreaker column.** `created_at`
(microsecond-resolution, timezone-aware) is the only ordering signal --
identical to `RiskAssessmentHistory`/`SafetyActionHistory`, neither of
which carries one either. Two writes to the *same* event's attribution
landing in the same microsecond is not resolved deterministically here
(a documented, narrow, accepted limitation, not a silent gap; see
`docs/OPERATIONAL_SCOPE_FOUNDATION_V0_1.md` §10 for the full account) --
in practice this requires two concurrent mutating requests against the
same event, already an inherently racy scenario the write path (a
single `UPDATE ... SET attributed_project_id` under the row's own
implicit lock) does not otherwise guard against either. Introducing a
new autoincrement/sequence column (no precedent anywhere in this
schema — every table uses a UUID primary key) to resolve a scenario
this narrow was judged unjustified machinery for this milestone.

**Immutable by convention, not a database trigger** — the same
guarantee `RiskAssessmentHistory`/`SafetyActionHistory` already rely
on: no route ever issues `UPDATE`/`DELETE` against this table; every
row is written once, by
`app/services/safety_event_project_service.py::attribute_event_to_project()`
/ `clear_event_project_attribution()`, in the same transaction as the
`SafetyEvent.attributed_project_id` column write, and never touched
again. A history row is written only on an actual state transition —
re-attributing an event to the project it is already attributed to, or
clearing an already-unattributed event, is a true no-op: no redundant
row, mirroring `ProjectSite`'s own "linking an already-linked pair is a
no-op" idempotency precedent.

**Tenant-scoped, `ON DELETE CASCADE` on both `event_id` and
`project_id`** (`OrganizationScopedMixin`) — a history row has no
meaning independent of the event, project, and organization it
concerns, identical reasoning to `RiskAssessmentHistory.assessment_id`'s
own. Neither `SafetyEvent` nor `Project` has a delete route anywhere in
this codebase today, so this is a defensive default, not a path this
milestone's own tests exercise.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow


class SafetyEventProjectAttributionAction:
    """Known `action` values — a typo-guard convenience, not an enforced
    enum, mirroring `RiskAssessmentHistoryChangeType`/
    `ActionHistoryChangeType`'s own established reasoning exactly."""

    ATTRIBUTED = "ATTRIBUTED"
    CLEARED = "CLEARED"


class SafetyEventProjectAttributionHistory(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "safety_event_project_attribution_history"
    __table_args__ = (
        # The one index the point-in-time reconstruction query in
        # events_as_of() actually needs: "this event's rows, ordered by
        # when they took effect."
        Index("ix_safety_event_project_attribution_history_event_created", "event_id", "created_at"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("safety_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Never NULL on either action -- see module docstring's
    # "Reconstructing..." section for why a CLEARED row still names the
    # project whose attribution was cleared.
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # A plain string, not a native enum -- see
    # SafetyEventProjectAttributionAction's own docstring.
    action: Mapped[str] = mapped_column(String(20), nullable=False)

    # Exactly one of these is set, mirroring RiskAssessmentHistory's own
    # changed_by_user_id/changed_by_api_client_id convention.
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    # The originating HTTP request's id -- mirrors AuditLog.request_id /
    # RiskAssessmentHistory.request_id exactly.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # This row's own effective-time boundary -- see module docstring's
    # "Why created_at, not a separate effective_at column" section.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    event: Mapped["SafetyEvent"] = relationship()  # noqa: F821
    project: Mapped["Project"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SafetyEventProjectAttributionHistory id={self.id!s} event_id={self.event_id!s} "
            f"project_id={self.project_id!s} action={self.action!r} created_at={self.created_at!s}>"
        )


__all__ = ["SafetyEventProjectAttributionHistory", "SafetyEventProjectAttributionAction"]
