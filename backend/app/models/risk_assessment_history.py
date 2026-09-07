"""RiskAssessmentHistory — SIE Milestone 26: Formal Enterprise Risk
Assessment Engine v0.2 (item 8-9). An immutable, append-only audit trail
scoped to one `RiskAssessment` (and, where relevant, one of its own
`RiskAssessmentFinding` rows) — distinct from, and complementary to,
`AuditLog` (see `app/models/safety_action_history.py`'s own docstring
for the identical "two sinks, two questions" rationale this table
mirrors verbatim, applied to the Risk Assessment domain: this table is
the domain history a client would render on one assessment's own detail
view -- "what happened to this assessment and its findings" -- while
`AuditLog` remains the platform-wide security/administrative log every
other milestone already writes to. Both are written in the same call,
from the same data, by `app/services/risk_assessment_service.py::
record_history()` and `audit_assessment_event()`, inside the identical
single transaction boundary (`assessment_mutation_transaction()`) --
never a second, competing audit implementation.

**Immutable by convention, not by a database trigger.** No route in
`app/api/v1/risk_assessments.py` ever issues an `UPDATE` or `DELETE`
against this table — every row is written once, by `record_history()`,
and never touched again, the same "one write path" guarantee
`SafetyActionHistory` already established.

**Tenant-scoped, `ON DELETE CASCADE`** (`OrganizationScopedMixin`) — a
history row has no meaning independent of the assessment and
organization it belongs to, identical reasoning to
`SafetyActionHistory`'s own.

**One table for both assessment- and finding-level events.** `finding_id`
is nullable: `NULL` for an assessment-level event (created/submitted/
approved/archived), set for a finding-level event (created/updated/risk
rated/residual rated/action created/linked/unlinked/closed -- SIE
Milestone 27 adds the last two kinds) -- always queryable by
`assessment_id` alone (a client rendering "history for this assessment"
needs both kinds together, in one chronological list), and by
`(assessment_id, finding_id)` for one finding's own history."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow


class RiskAssessmentHistoryChangeType:
    """Known `change_type` values — a typo-guard convenience, not an
    enforced enum, mirroring `ActionHistoryChangeType`'s own reasoning
    (`app/models/safety_action_history.py`) and
    `app.services.audit_service.AuditAction`'s own: kept open in case a
    future milestone adds a new kind of change worth recording."""

    ASSESSMENT_CREATED = "ASSESSMENT_CREATED"
    ASSESSMENT_UPDATED = "ASSESSMENT_UPDATED"
    ASSESSMENT_SUBMITTED = "ASSESSMENT_SUBMITTED"
    ASSESSMENT_APPROVED = "ASSESSMENT_APPROVED"
    ASSESSMENT_SUPERSEDED = "ASSESSMENT_SUPERSEDED"
    ASSESSMENT_ARCHIVED = "ASSESSMENT_ARCHIVED"
    FINDING_CREATED = "FINDING_CREATED"
    FINDING_UPDATED = "FINDING_UPDATED"
    FINDING_RISK_RATED = "FINDING_RISK_RATED"
    FINDING_RESIDUAL_RATED = "FINDING_RESIDUAL_RATED"
    FINDING_ACTION_LINKED = "FINDING_ACTION_LINKED"
    FINDING_ACTION_UNLINKED = "FINDING_ACTION_UNLINKED"
    # SIE Milestone 27: Risk Assessment & Action Management Integration v0.1.
    # FINDING_ACTION_CREATED is distinct from FINDING_ACTION_LINKED -- the
    # latter is reused, unchanged, for linking an *existing* SafetyAction
    # (whether via the legacy linked_action_id field or the new dedicated
    # relationship endpoint); this one specifically records that a *new*
    # SafetyAction was created, from this finding, in the same operation.
    FINDING_ACTION_CREATED = "FINDING_ACTION_CREATED"
    # The one, governed path to FindingStatus.CLOSED -- see FindingStatus's
    # own docstring (app/models/risk_assessment_enums.py) and
    # require_finding_closable() (app/services/risk_assessment_service.py).
    FINDING_CLOSED = "FINDING_CLOSED"


class RiskAssessmentHistory(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "risk_assessment_history"
    __table_args__ = (
        Index("ix_risk_assessment_history_assessment", "assessment_id"),
        Index("ix_risk_assessment_history_finding", "finding_id"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False
    )
    # NULL = an assessment-level event; set = a finding-level event --
    # see module docstring.
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessment_findings.id", ondelete="CASCADE"), nullable=True
    )

    # A plain string, not a native enum -- see RiskAssessmentHistoryChangeType's own docstring.
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Stored as plain strings (a status value literally as it was at the
    # time), not a native enum type -- a history row stays a faithful
    # record of what the status/rating literally was, independent of
    # whether that value is still considered valid by the current enum
    # definition. Reused for whichever status dimension `change_type`
    # concerns (assessment status, finding status, or candidate_status).
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Exactly one of these is set, mirroring SafetyActionHistory's own
    # convention.
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    # The originating HTTP request's id -- mirrors AuditLog.request_id /
    # SafetyActionHistory.request_id exactly.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    assessment: Mapped["RiskAssessment"] = relationship()  # noqa: F821
    finding: Mapped["RiskAssessmentFinding | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RiskAssessmentHistory id={self.id!s} assessment_id={self.assessment_id!s} "
            f"finding_id={self.finding_id!s} change_type={self.change_type!r}>"
        )


__all__ = ["RiskAssessmentHistory", "RiskAssessmentHistoryChangeType"]
