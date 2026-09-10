"""RiskAssessmentFindingAction — SIE Milestone 27: Risk Assessment &
Action Management Integration v0.1. The relationship table that lets a
finding require *multiple* `SafetyAction` responses, replacing the
single `RiskAssessmentFinding.linked_action_id` pointer (SIE Milestone
26) as the canonical "which actions are the response to this finding"
record.

**Why a new table rather than redesigning `linked_action_id` in place.**
Milestone 27's own instruction: inspect the M26 field and the
`SafetyAction` domain first, then choose the smallest backward-
compatible architecture — never blindly replace a field a previous
milestone shipped. `linked_action_id` is kept exactly as it was
(column, migration, PATCH behavior, and every Milestone 26 test all
unchanged) so nothing that already depends on "one action per finding"
breaks. This table *supplements* it: `app/api/v1/risk_assessments.py::
update_finding()`'s existing `linked_action_id` branch now also
writes/removes the matching row here (see that function's own
docstring), so a finding linked only through the legacy field and one
linked through the new dedicated endpoints are both visible through the
one same query — there is exactly one underlying source of truth for
"which actions does this finding currently have," `linked_action_id` is
simply a legacy pointer into it. Migration 0019 backfills one row per
pre-existing non-NULL `linked_action_id` so this is true immediately
upon upgrade too, not just for rows created afterward.

**Response, not evidence (SIE Milestone 26's own distinction,
unchanged).** This table answers "what was raised to address this
finding" — architecturally distinct from an `ACTION`-type
`RiskAssessmentFindingEvidence` row, which answers "why does this
finding exist." The two are never conflated: a `SafetyAction` may
appear in both places for the same finding (cited as evidence *and*
raised as the response), independently.

**Tenant-scoped, `ON DELETE CASCADE`** (`OrganizationScopedMixin`) —
mirrors `RiskAssessmentControl`/`RiskAssessmentFindingEvidence`'s own
"child row has no meaning independent of the finding and organization it
belongs to" precedent. `action_id` also cascades: `SafetyAction` rows
are never deleted by any route in this codebase today (only
transitioned to a terminal `status`), so this is a defensive schema
choice, not a live deletion path — mirrors `linked_action_id`'s own
`ON DELETE SET NULL` reasoning, just expressed as "the relationship row
goes away" instead of "a column on the finding is cleared" (there is no
finding column here to clear).

**Unlink is a hard delete, not a soft one.** `RiskAssessmentHistory`
(via `record_history()`) already permanently records every link/unlink
event, independent of whether this row still exists — exactly the same
"the row's own existence answers 'is this true right now'; the history
table answers 'what happened, and when'" split every other mutation in
this domain already makes. A `(finding_id, action_id)` pair is
therefore unique: linking the same action to the same finding twice is
a no-op (idempotent by construction — item 10's own "safely retryable"
requirement), never a duplicate row.
"""

import uuid

from sqlalchemy import ForeignKey, Index, Uuid
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RiskAssessmentFindingAction(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "risk_assessment_finding_actions"
    __table_args__ = (
        UniqueConstraint("finding_id", "action_id", name="uq_risk_assessment_finding_actions_finding_action"),
        Index("ix_risk_assessment_finding_actions_finding", "finding_id"),
        Index("ix_risk_assessment_finding_actions_action", "action_id"),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessment_findings.id", ondelete="CASCADE"), nullable=False
    )
    action_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("safety_actions.id", ondelete="CASCADE"), nullable=False
    )

    # Exactly one of these is set, mirroring RiskAssessmentHistory's own
    # convention.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    finding: Mapped["RiskAssessmentFinding"] = relationship()  # noqa: F821
    action: Mapped["SafetyAction"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RiskAssessmentFindingAction id={self.id!s} finding_id={self.finding_id!s} "
            f"action_id={self.action_id!s}>"
        )


__all__ = ["RiskAssessmentFindingAction"]
