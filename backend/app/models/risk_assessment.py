"""RiskAssessment and its children — SIE Milestone 25: Enterprise Risk
Assessment Foundation v0.1.

    Organization
       |
       +-- Location   (scope=LOCATION -- see RiskAssessmentScope's own
       |                docstring: not a first-class entity yet)
       |
       +-- Site
              |
              +-- RiskAssessment
                     |
                     +-- RiskAssessmentFinding
                     |       +-- RiskAssessmentControl
                     |       +-- RiskAssessmentFindingEvidence
                     |
                     +-- version lineage (lineage_id/version/supersedes_id,
                                           below)

**Core architectural rule (item 1) — this is a layer *above*
`enterprise-risk-v1`, never a replacement.** Nothing in this module
imports, modifies, or recomputes `app/intelligence/risk_score.py`.
`RiskAssessmentFinding.inherent_risk_score`/`residual_risk_score` come
exclusively from `app/risk_assessment/risk_matrix.py`'s own
likelihood x consequence calculation — a human/governed judgment, never
`enterprise-risk-v1`'s 0-100 event-volume score (see that module's own
docstring for the full "why these are different questions" rationale).

**"Candidate ≠ approved risk" (items 14-15, 27) — enforced at the data
model, not merely by convention.** A system-generated finding
(`candidate_status` starts `IDENTIFIED`) has `likelihood`/`consequence`
`NULL` until a human accepts it (`candidate_status -> ACCEPTED`) *and*
separately supplies a rating — nothing in this codebase computes a
likelihood/consequence value from an anomaly's z-score, a pattern's
count, or an association's correlation coefficient. See
`app/risk_assessment/candidate_generation.py`'s own docstring for the
generation side of this boundary.

**System evidence vs. human assessment (item 7) — distinct columns, not
one blob.** `description` (system evidence, e.g. "12 vehicle incidents
recorded over six periods") and `system_analysis_summary` (the
originating intelligence engine's own factual statement, e.g. "strong
positive association with overall incident activity") are both
machine-written and never edited by a human once set; `assessor_notes`
is the one column a human writes their own judgment into. No code path
in this codebase ever copies `assessor_notes` into `description` or
represents one as the other — see `app/services/risk_assessment_service.py`
for the one write path for each.

**Immutability after approval (items 4, 23-24).** No route ever issues
an `UPDATE` against a `RiskAssessment`/`RiskAssessmentFinding`/
`RiskAssessmentControl` row whose parent assessment's `status` is
`APPROVED` or `SUPERSEDED` — enforced in
`app/services/risk_assessment_service.py`/`app/api/v1/risk_assessments.py`,
mirroring `app/api/v1/actions.py`'s own "narrow mutation surface,
enforced in the service layer" precedent. A substantive change to an
approved assessment creates a new version instead (`lineage_id`/
`version`/`supersedes_id` below) -- the approved row itself is never
edited in place.

**Versioning / lineage (item 18).** `lineage_id` groups every version of
"the same assessment" together (defaults to the first version's own
`id`); `version` increments per lineage; `supersedes_id` points
backward to the version this one replaces. Approving a new version
automatically (and only then) transitions the previous `APPROVED`
version in the same lineage to `SUPERSEDED` — see
`app/services/risk_assessment_service.py::open_new_version()`. A
`SUPERSEDED` row is never deleted or edited -- "what did we assess the
risk to be at that time" (item 18's own question) stays answerable by
simply reading that historical row and its own `as_of`.

**Point-in-time integrity (item 19).** `as_of` is the one timestamp
every event/action/intelligence-context lookup for this assessment is
bound to — `app/services/risk_assessment_service.py` and
`app/risk_assessment/candidate_generation.py` both thread it through
`events_as_of()` exactly like every Milestone 22-24 computation already
does; no second temporal implementation exists here.

**Tenant scoping.** `RiskAssessment` uses `OrganizationScopedMixin`
directly. Its children (`RiskAssessmentFinding`/`RiskAssessmentControl`/
`RiskAssessmentFindingEvidence`) each carry their own `organization_id`
too (set explicitly, at creation, to the parent's own
`organization_id` — never independently assignable), mirroring
`SafetyActionHistory`'s own established "tenant-scoped child of a
tenant-scoped parent, `ON DELETE CASCADE`" precedent exactly: a
finding/control/evidence row has no meaning independent of the
assessment and organization it belongs to.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.risk_assessment_enums import (
    ControlEffectiveness,
    ControlStatus,
    ControlType,
    FindingSource,
    FindingStatus,
    RiskArea,
    RiskAssessmentScope,
    RiskAssessmentStatus,
    RiskCandidateStatus,
    RiskEvidenceType,
)


class RiskAssessment(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        Index("ix_risk_assessments_org_status", "organization_id", "status"),
        Index("ix_risk_assessments_org_site", "organization_id", "site_id"),
        Index("ix_risk_assessments_lineage", "lineage_id"),
    )

    scope: Mapped[RiskAssessmentScope] = mapped_column(
        SAEnum(RiskAssessmentScope, name="risk_assessment_scope", native_enum=True), nullable=False
    )
    # Required (validated at the service layer) when scope=SITE; always
    # NULL for ORGANIZATION/LOCATION scope -- see RiskAssessmentScope's
    # own docstring for why LOCATION has no dedicated reference yet.
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RiskAssessmentStatus] = mapped_column(
        SAEnum(RiskAssessmentStatus, name="risk_assessment_status", native_enum=True),
        nullable=False,
        default=RiskAssessmentStatus.DRAFT,
        index=True,
    )

    # --- Versioning / lineage (item 18) -------------------------------------------------
    lineage_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True
    )

    # --- Temporal (item 19) --------------------------------------------------------------
    assessment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)

    assessor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    methodology_version: Mapped[str] = mapped_column(String(50), nullable=False)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    organization: Mapped["Organization"] = relationship()  # noqa: F821
    site: Mapped["Site | None"] = relationship()  # noqa: F821
    findings: Mapped[list["RiskAssessmentFinding"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", order_by="RiskAssessmentFinding.created_at"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RiskAssessment id={self.id!s} organization_id={self.organization_id!s} "
            f"scope={self.scope!s} status={self.status!s} version={self.version}>"
        )


class RiskAssessmentFinding(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "risk_assessment_findings"
    __table_args__ = (
        Index("ix_risk_assessment_findings_assessment", "assessment_id"),
        Index("ix_risk_assessment_findings_org_risk_area", "organization_id", "risk_area"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False
    )
    risk_area: Mapped[RiskArea] = mapped_column(SAEnum(RiskArea, name="risk_area", native_enum=True), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # System evidence -- factual, machine-written (item 7).
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The originating intelligence engine's own analytical statement --
    # also machine-written, distinct from `description` (raw evidence)
    # and from `assessor_notes` (human judgment) below.
    system_analysis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The one column a human's own judgment is ever written into -- see
    # module docstring's "system evidence vs. human assessment" section.
    # SIE never represents this as system-derived fact (item 7's own
    # instruction).
    assessor_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[FindingSource] = mapped_column(
        SAEnum(FindingSource, name="risk_finding_source", native_enum=True), nullable=False
    )
    # Verbatim calculation version from the originating intelligence
    # computation (item 26) -- e.g. "anomaly-v1", "enterprise-recurrence-v1".
    # NULL for MANUAL/INSPECTION findings, which have no calculation version.
    originating_calculation_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    occurrence_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurrence_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[FindingStatus] = mapped_column(
        SAEnum(FindingStatus, name="risk_finding_status", native_enum=True),
        nullable=False,
        default=FindingStatus.OPEN,
    )

    # --- Candidate lifecycle (items 14-15, 27) --------------------------------------------
    # NULL means "not system-generated -- authored directly by a human,
    # never subject to candidate review" (see RiskCandidateStatus's own
    # docstring). Only a NULL or ACCEPTED finding may ever carry a
    # likelihood/consequence rating -- enforced in
    # app/services/risk_assessment_service.py, never merely by convention.
    candidate_status: Mapped[RiskCandidateStatus | None] = mapped_column(
        SAEnum(RiskCandidateStatus, name="risk_candidate_status", native_enum=True), nullable=True
    )
    candidate_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Inherent risk (item 10) -- NOT enterprise-risk-v1 --------------------------------
    likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inherent_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inherent_risk_classification: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # --- Residual risk (item 13) -- an independent assessment, never a
    # mathematically-derived percentage reduction from control
    # effectiveness (see app/risk_assessment/risk_matrix.py's own
    # docstring). NULL until a human explicitly supplies a residual
    # likelihood/consequence pair.
    residual_likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_consequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_risk_classification: Mapped[str | None] = mapped_column(String(20), nullable=True)

    assessment: Mapped["RiskAssessment"] = relationship(back_populates="findings")
    controls: Mapped[list["RiskAssessmentControl"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", order_by="RiskAssessmentControl.created_at"
    )
    evidence: Mapped[list["RiskAssessmentFindingEvidence"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", order_by="RiskAssessmentFindingEvidence.created_at"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RiskAssessmentFinding id={self.id!s} assessment_id={self.assessment_id!s} "
            f"risk_area={self.risk_area!s} candidate_status={self.candidate_status!s}>"
        )


class RiskAssessmentControl(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "risk_assessment_controls"
    __table_args__ = (Index("ix_risk_assessment_controls_finding", "finding_id"),)

    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessment_findings.id", ondelete="CASCADE"), nullable=False
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)
    control_type: Mapped[ControlType] = mapped_column(
        SAEnum(ControlType, name="risk_control_type", native_enum=True), nullable=False
    )
    status: Mapped[ControlStatus] = mapped_column(
        SAEnum(ControlStatus, name="risk_control_status", native_enum=True),
        nullable=False,
        default=ControlStatus.PROPOSED,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NOT_ASSESSED (default) means "no control-effectiveness information
    # was provided" -- a genuinely different state from INEFFECTIVE (item
    # 12's own instruction; never conflated anywhere in this codebase).
    effectiveness: Mapped[ControlEffectiveness] = mapped_column(
        SAEnum(ControlEffectiveness, name="risk_control_effectiveness", native_enum=True),
        nullable=False,
        default=ControlEffectiveness.NOT_ASSESSED,
    )

    finding: Mapped["RiskAssessmentFinding"] = relationship(back_populates="controls")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RiskAssessmentControl id={self.id!s} finding_id={self.finding_id!s} "
            f"control_type={self.control_type!s} effectiveness={self.effectiveness!s}>"
        )


class RiskAssessmentFindingEvidence(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    """Item 8. Always a *reference*, never a copy of the source
    narrative -- see module docstring and
    `app/models/risk_assessment_enums.py::RiskEvidenceType`'s own
    docstring for exactly what `reference_id`/`reference_label` mean per
    evidence type."""

    __tablename__ = "risk_assessment_finding_evidence"
    __table_args__ = (Index("ix_risk_assessment_finding_evidence_finding", "finding_id"),)

    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risk_assessment_findings.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[RiskEvidenceType] = mapped_column(
        SAEnum(RiskEvidenceType, name="risk_evidence_type", native_enum=True), nullable=False
    )
    # Populated (and, at write time, tenant-validated) only for
    # EVENT/ACTION/KNOWLEDGE_DOCUMENT -- NULL for ANOMALY/PATTERN/
    # ASSOCIATION/OTHER, which reference a computed, non-persisted result
    # instead (see RiskEvidenceType's own docstring).
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reference_label: Mapped[str | None] = mapped_column(String(500), nullable=True)

    finding: Mapped["RiskAssessmentFinding"] = relationship(back_populates="evidence")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RiskAssessmentFindingEvidence id={self.id!s} finding_id={self.finding_id!s} "
            f"evidence_type={self.evidence_type!s}>"
        )
