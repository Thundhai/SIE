"""Risk Assessment API schemas — SIE Milestone 25: Enterprise Risk
Assessment Foundation v0.1. Built directly from the real, unmodified
`RiskAssessment`/`RiskAssessmentFinding`/`RiskAssessmentControl`/
`RiskAssessmentFindingEvidence` models — no second, competing
representation, mirroring `app/schemas/actions.py`'s own established
shape. `extra="forbid"` on every write schema: a client may set exactly
the fields named below, nothing else (`organization_id`,
`inherent_risk_score`, `status` via PATCH, `approved_at`, ... are all
absent from every write schema here, not merely ignored if sent).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
from app.schemas.enterprise_intelligence import (
    ConcentrationContributorRead,
    EnterpriseAnomalyRead,
    EnterpriseAssociationRead,
    EnterpriseTrendRead,
    RecurrencePatternRead,
    RiskScoreRead,
)

_TITLE_MAX_LENGTH = 255
_DESCRIPTION_MAX_LENGTH = 5000
_NOTES_MAX_LENGTH = 5000
_REFERENCE_MAX_LENGTH = 2000
_REFERENCE_LABEL_MAX_LENGTH = 500

# References only rows this milestone actually validates at write time
# (item 8) -- ANOMALY/PATTERN/ASSOCIATION/OTHER reference a computed,
# non-persisted result instead (see RiskEvidenceType's own docstring).
_REFERENCE_ID_EVIDENCE_TYPES = frozenset({RiskEvidenceType.EVENT, RiskEvidenceType.ACTION, RiskEvidenceType.KNOWLEDGE_DOCUMENT})


# --- Evidence --------------------------------------------------------------------------


class RiskEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_type: RiskEvidenceType
    reference_id: uuid.UUID | None = None
    reference_label: str | None = Field(default=None, max_length=_REFERENCE_LABEL_MAX_LENGTH)

    @model_validator(mode="after")
    def _validate_reference_shape(self) -> "RiskEvidenceCreate":
        if self.evidence_type in _REFERENCE_ID_EVIDENCE_TYPES:
            if self.reference_id is None:
                raise ValueError(f"reference_id is required for evidence_type={self.evidence_type.value}.")
        else:
            if self.reference_id is not None:
                raise ValueError(
                    f"reference_id is not permitted for evidence_type={self.evidence_type.value} "
                    "(it references a computed, non-persisted intelligence result -- use reference_label instead)."
                )
            if not self.reference_label:
                raise ValueError(f"reference_label is required for evidence_type={self.evidence_type.value}.")
        return self


class RiskEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evidence_type: RiskEvidenceType
    reference_id: uuid.UUID | None
    reference_label: str | None
    created_at: datetime


# --- Controls ----------------------------------------------------------------------------


class RiskControlCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., min_length=1, max_length=_DESCRIPTION_MAX_LENGTH)
    control_type: ControlType
    status: ControlStatus = ControlStatus.PROPOSED
    owner_user_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=_REFERENCE_MAX_LENGTH)
    effectiveness: ControlEffectiveness = ControlEffectiveness.NOT_ASSESSED


class RiskControlRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    control_type: ControlType
    status: ControlStatus
    owner_user_id: uuid.UUID | None
    reference: str | None
    effectiveness: ControlEffectiveness
    created_at: datetime
    updated_at: datetime


# --- Findings ------------------------------------------------------------------------------


class RiskAssessmentFindingCreate(BaseModel):
    """`POST /risk-assessments/{assessment_id}/findings` body — a
    directly human-authored finding (`source` defaults to `MANUAL`,
    `candidate_status` stays `NULL`). System-generated candidates are
    never created through this endpoint -- they come only from
    `app/risk_assessment/candidate_generation.py`, automatically, at
    assessment creation (item 15's own "candidate ≠ approved risk"
    boundary: a human authoring a finding directly here is making an
    assessment, not proposing a candidate for later review)."""

    model_config = ConfigDict(extra="forbid")

    risk_area: RiskArea
    title: str = Field(..., min_length=1, max_length=_TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)
    assessor_notes: str | None = Field(default=None, max_length=_NOTES_MAX_LENGTH)
    source: FindingSource = FindingSource.MANUAL
    occurrence_period_start: datetime | None = None
    occurrence_period_end: datetime | None = None
    likelihood: int | None = Field(default=None, ge=1, le=5)
    consequence: int | None = Field(default=None, ge=1, le=5)
    evidence: list[RiskEvidenceCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _likelihood_and_consequence_together(self) -> "RiskAssessmentFindingCreate":
        if (self.likelihood is None) != (self.consequence is None):
            raise ValueError("likelihood and consequence must be supplied together, or not at all.")
        return self


class RiskAssessmentFindingUpdate(BaseModel):
    """`PATCH /risk-assessments/{assessment_id}/findings/{finding_id}`
    body -- the one place a candidate is reviewed (item 14's own "HUMAN
    REVIEW" step) and/or a rating, controls, or residual assessment is
    supplied. Only permitted while the parent assessment is `DRAFT`/
    `IN_REVIEW` (`app/services/risk_assessment_service.py::
    require_editable()`). `controls`, when supplied (not `None`),
    *replaces* the finding's entire control set atomically -- the
    simplest v0.1 semantics that still fully supports items 11-13
    without a dedicated controls sub-resource (item 22's own "keep the
    milestone focused" instruction)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=_TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)
    assessor_notes: str | None = Field(default=None, max_length=_NOTES_MAX_LENGTH)
    status: FindingStatus | None = None
    candidate_status: RiskCandidateStatus | None = None
    likelihood: int | None = Field(default=None, ge=1, le=5)
    consequence: int | None = Field(default=None, ge=1, le=5)
    residual_likelihood: int | None = Field(default=None, ge=1, le=5)
    residual_consequence: int | None = Field(default=None, ge=1, le=5)
    controls: list[RiskControlCreate] | None = None
    evidence_add: list[RiskEvidenceCreate] | None = None

    @field_validator("candidate_status")
    @classmethod
    def _no_reverting_to_identified(cls, value: RiskCandidateStatus | None) -> RiskCandidateStatus | None:
        if value == RiskCandidateStatus.IDENTIFIED:
            raise ValueError(
                "candidate_status cannot be set back to IDENTIFIED via update -- that is only the initial "
                "state a system-generated candidate starts in."
            )
        return value

    @model_validator(mode="after")
    def _likelihood_and_consequence_together(self) -> "RiskAssessmentFindingUpdate":
        if (self.likelihood is None) != (self.consequence is None):
            raise ValueError("likelihood and consequence must be supplied together, or not at all.")
        if (self.residual_likelihood is None) != (self.residual_consequence is None):
            raise ValueError("residual_likelihood and residual_consequence must be supplied together, or not at all.")
        return self


class RiskAssessmentFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    risk_area: RiskArea
    title: str
    description: str | None
    system_analysis_summary: str | None
    assessor_notes: str | None
    source: FindingSource
    originating_calculation_version: str | None
    occurrence_period_start: datetime | None
    occurrence_period_end: datetime | None
    status: FindingStatus
    candidate_status: RiskCandidateStatus | None
    candidate_generated_at: datetime | None
    likelihood: int | None
    consequence: int | None
    inherent_risk_score: int | None
    inherent_risk_classification: str | None
    residual_likelihood: int | None
    residual_consequence: int | None
    residual_risk_score: int | None
    residual_risk_classification: str | None
    controls: list[RiskControlRead]
    evidence: list[RiskEvidenceRead]
    created_at: datetime
    updated_at: datetime


# --- Assessment ----------------------------------------------------------------------------


class RiskAssessmentCreate(BaseModel):
    """`POST /risk-assessments` body. `organization_id` comes from
    request context, never the body (mirrors
    `app/schemas/actions.py::SafetyActionCreate`'s own documented
    reasoning). `supersedes_assessment_id`, when supplied, opens a new
    version in that assessment's own lineage (item 18) instead of
    starting a brand-new one -- the referenced assessment must already
    be `APPROVED` (`app/services/risk_assessment_service.py::
    open_new_version()`)."""

    model_config = ConfigDict(extra="forbid")

    scope: RiskAssessmentScope
    site_id: uuid.UUID | None = None
    title: str = Field(..., min_length=1, max_length=_TITLE_MAX_LENGTH)
    assessment_date: datetime
    as_of: datetime | None = None
    window_days: int | None = Field(default=None, gt=0)
    assessor_user_id: uuid.UUID | None = None
    supersedes_assessment_id: uuid.UUID | None = None
    generate_candidates: bool = Field(
        default=True,
        description="Whether to auto-generate candidate findings from current intelligence (items 14-15). "
        "Candidates always start IDENTIFIED with no rating -- never an approved risk on their own.",
    )

    @model_validator(mode="after")
    def _site_required_for_site_scope(self) -> "RiskAssessmentCreate":
        if self.scope == RiskAssessmentScope.SITE and self.site_id is None:
            raise ValueError("site_id is required when scope=SITE.")
        if self.scope != RiskAssessmentScope.SITE and self.site_id is not None:
            raise ValueError("site_id is only permitted when scope=SITE.")
        return self


class RiskAssessmentUpdate(BaseModel):
    """`PATCH /risk-assessments/{assessment_id}` body -- only while
    `DRAFT`/`IN_REVIEW` (item 23). `scope`/`site_id` are deliberately not
    patchable at all (a scope change is a different assessment, not an
    edit to this one) -- create a new version instead."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=_TITLE_MAX_LENGTH)
    assessment_date: datetime | None = None
    as_of: datetime | None = None
    window_days: int | None = Field(default=None, gt=0)
    assessor_user_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be blank.")
        return value


class IntelligenceContextRead(BaseModel):
    """Item 26 -- structured, read-only, computed fresh from the
    assessment's own persisted `organization_id`/`site_id`/`as_of` on
    every read, never stored. Every calculation version is preserved
    verbatim from the originating Milestone 22-24 computation."""

    deterministic_risk: RiskScoreRead
    anomalies: list[EnterpriseAnomalyRead]
    patterns: list[RecurrencePatternRead]
    associations: list[EnterpriseAssociationRead]
    trend: EnterpriseTrendRead
    concentrations: list[ConcentrationContributorRead]
    calculation_versions: dict[str, str]


class RiskAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    scope: RiskAssessmentScope
    site_id: uuid.UUID | None
    title: str
    status: RiskAssessmentStatus
    lineage_id: uuid.UUID
    version: int
    supersedes_id: uuid.UUID | None
    assessment_date: datetime
    as_of: datetime
    window_days: int
    assessor_user_id: uuid.UUID | None
    methodology_version: str
    submitted_at: datetime | None
    submitted_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    approved_by_user_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    created_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class RiskAssessmentDetailRead(RiskAssessmentRead):
    """`POST`/`GET .../{id}`/`PATCH`/`.../submit`/`.../approve` response
    -- the full assessment plus its findings and read-only intelligence
    context. `GET /risk-assessments` (the list view) uses the leaner
    `RiskAssessmentRead` instead, mirroring
    `app/schemas/events.py`'s own summary/detail split -- computing every
    assessment's own `intelligence_context` for a paginated list would be
    an unbounded-cost N+1, not a bounded, single-resource read."""

    findings: list[RiskAssessmentFindingRead]
    intelligence_context: IntelligenceContextRead


class RiskAssessmentListRead(BaseModel):
    items: list[RiskAssessmentRead]
    total: int
    page: int
    page_size: int


class RiskAssessmentFindingListRead(BaseModel):
    items: list[RiskAssessmentFindingRead]
    total: int
