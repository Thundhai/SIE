"""RiskAssessmentControlEvidence — SIE Milestone 29: Enterprise Risk
Assessment Evidence & Control Effectiveness Foundation v0.1. The link
table that lets a `RiskAssessmentControl`'s effectiveness assessment
reference specific supporting evidence, without duplicating any evidence
payload.

**Why a link table over an existing finding-evidence row, not a new
evidence-payload table.** The spec's own instruction: "Do not duplicate
evidence payloads unnecessarily," and "prefer reusing the existing
risk-assessment evidence model if it can safely support control-specific
evidence without corrupting current semantics." `RiskAssessmentFindingEvidence`
(SIE Milestone 25) already *is* this codebase's one evidence-payload
shape (`evidence_type` + `reference_id`/`reference_label`, tenant-
validated at write time) — answering "why does this finding exist."
Giving that same table a nullable `control_id` would blur that meaning
(is a row evidence for the finding, or for one of its controls, or
both?) for no benefit. Instead, a control's supporting evidence is
always a specific, already-validated `RiskAssessmentFindingEvidence` row
*belonging to the same finding as the control* — this table only records
"this control's effectiveness is supported by that evidence row," a pure
relationship, mirroring `RiskAssessmentFindingAction`'s own (SIE
Milestone 27) "supplement with a relationship table, never redesign or
duplicate an existing payload" precedent exactly.

**Provenance stays traceable.** Because this table never copies a
payload, the evidence's own original source (a `SafetyEvent`,
`SafetyAction`, `KnowledgeDocument`, or computed intelligence result) is
always reached the same way any `RiskAssessmentFindingEvidence` row's
provenance already is — through that row, unchanged.

**Tenant-scoped, `ON DELETE CASCADE`** (`OrganizationScopedMixin`) —
mirrors `RiskAssessmentFindingAction`'s own "child row has no meaning
independent of the control/evidence and organization it belongs to"
reasoning. Both `control_id` and `finding_evidence_id` cascade: this
link's only reason to exist is that both rows exist.

**Unlink is a hard delete, not a soft one** — exactly
`RiskAssessmentFindingAction`'s own reasoning: `RiskAssessmentHistory`
(via `record_history()`) already permanently records every link/unlink
event independent of whether this row still exists. A
`(control_id, finding_evidence_id)` pair is therefore unique: linking
the same evidence to the same control twice is a no-op (idempotent by
construction), never a duplicate row -- see
`app/services/risk_assessment_service.py::create_control_evidence_link()`.
"""

import uuid

from sqlalchemy import ForeignKey, Index, Uuid
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RiskAssessmentControlEvidence(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "risk_assessment_control_evidence"
    __table_args__ = (
        UniqueConstraint(
            "control_id", "finding_evidence_id", name="uq_risk_assessment_control_evidence_control_evidence"
        ),
        Index("ix_risk_assessment_control_evidence_control", "control_id"),
        Index("ix_risk_assessment_control_evidence_finding_evidence", "finding_evidence_id"),
    )

    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessment_controls.id", ondelete="CASCADE"), nullable=False
    )
    finding_evidence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessment_finding_evidence.id", ondelete="CASCADE"), nullable=False
    )

    # Exactly one of these is set, mirroring RiskAssessmentFindingAction's own convention.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    control: Mapped["RiskAssessmentControl"] = relationship(back_populates="control_evidence")  # noqa: F821
    finding_evidence: Mapped["RiskAssessmentFindingEvidence"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RiskAssessmentControlEvidence id={self.id!s} control_id={self.control_id!s} "
            f"finding_evidence_id={self.finding_evidence_id!s}>"
        )


__all__ = ["RiskAssessmentControlEvidence"]
