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
    AssessmentType,
    ControlEffectiveness,
    ControlStatus,
    ControlType,
    FindingSource,
    FindingStatus,
    RiskAssessmentScope,
    RiskAssessmentStatus,
    RiskCandidateStatus,
    RiskEvidenceType,
)
from app.models.safety_action_enums import ActionPriority, ActionType
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
    """The one control-read shape, used everywhere a control appears --
    embedded in a finding (`RiskAssessmentFindingRead.controls`) and by
    every SIE Milestone 29 dedicated control endpoint alike (never a
    second, competing read schema). `effectiveness_rationale`/
    `assessed_at`/`assessed_by_user_id` (Milestone 29) are `None` until
    `POST .../controls/{control_id}/assess-effectiveness` -- the one
    dedicated, audited path -- has been called at least once; `evidence`
    (Milestone 29) lists the `RiskAssessmentFindingEvidence` rows this
    control's effectiveness assessment currently cites, always built
    explicitly by `app/api/v1/risk_assessments.py::_to_control_read()`
    rather than `model_validate()` alone, since the underlying ORM
    relationship (`control_evidence`, link rows) doesn't share this
    field's name or shape."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_id: uuid.UUID
    description: str
    control_type: ControlType
    status: ControlStatus
    owner_user_id: uuid.UUID | None
    reference: str | None
    effectiveness: ControlEffectiveness
    effectiveness_rationale: str | None = None
    assessed_at: datetime | None = None
    assessed_by_user_id: uuid.UUID | None = None
    evidence: list[RiskEvidenceRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# --- SIE Milestone 29: Enterprise Risk Assessment Evidence & Control
# Effectiveness Foundation v0.1 -- dedicated control management API
# schemas. `RiskControlCreate` above stays exactly as it was (still used
# by the pre-existing Milestone 25 embedded-at-finding-creation and
# bulk-replace-via-finding-PATCH paths, both untouched by this
# milestone); the three below are new, additive, and used only by the
# new dedicated `.../controls` routes.


class RiskAssessmentControlCreate(BaseModel):
    """`POST .../findings/{finding_id}/controls` body. Deliberately has
    no `effectiveness` field at all -- unlike `RiskControlCreate` above
    -- so a control created through this dedicated route can never
    acquire an effectiveness rating without an explicit, attributable
    `POST .../assess-effectiveness` call; it is created `NOT_ASSESSED`
    (the model's own default), full stop."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., min_length=1, max_length=_DESCRIPTION_MAX_LENGTH)
    control_type: ControlType
    status: ControlStatus = ControlStatus.PROPOSED
    owner_user_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=_REFERENCE_MAX_LENGTH)


class RiskAssessmentControlUpdate(BaseModel):
    """`PATCH .../controls/{control_id}` body -- non-effectiveness
    metadata only. There is no `effectiveness`/`effectiveness_rationale`/
    `assessed_at`/`assessed_by_user_id` field on this schema at all (not
    merely ignored if sent -- `extra="forbid"` rejects it outright with a
    `422`): the spec's own "do not allow an effectiveness rating to be
    changed silently through generic PATCH" is enforced by this schema
    simply being unable to carry one. Use
    `POST .../controls/{control_id}/assess-effectiveness` instead."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, min_length=1, max_length=_DESCRIPTION_MAX_LENGTH)
    control_type: ControlType | None = None
    status: ControlStatus | None = None
    owner_user_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=_REFERENCE_MAX_LENGTH)


class RiskAssessmentControlEffectivenessAssess(BaseModel):
    """`POST .../controls/{control_id}/assess-effectiveness` body -- the
    one path that may ever set `effectiveness`/`effectiveness_rationale`/
    `assessed_at`/`assessed_by_user_id` together. `effectiveness_rating`
    may not be `NOT_ASSESSED`: that value means "no assessment was
    performed," so an actual assessment call can never conclude it --
    "NOT_ASSESSED must not masquerade as an assessed conclusion" (an
    unassessed control simply never calls this route). `rationale` must
    be non-blank after stripping whitespace, mirroring
    `RiskAssessmentFindingClose.closure_reason`'s own established
    validator. `assessed_at` is optional -- if omitted, the server's own
    current time is used (see that route's own docstring for why a
    server-set default, not a blind trust of a client-supplied
    timestamp, is the safer choice)."""

    model_config = ConfigDict(extra="forbid")

    effectiveness_rating: ControlEffectiveness
    effectiveness_rationale: str = Field(..., min_length=1, max_length=_DESCRIPTION_MAX_LENGTH)
    assessed_at: datetime | None = None

    @field_validator("effectiveness_rationale")
    @classmethod
    def _rationale_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("effectiveness_rationale must not be blank.")
        return value

    @field_validator("effectiveness_rating")
    @classmethod
    def _rating_not_not_assessed(cls, value: ControlEffectiveness) -> ControlEffectiveness:
        if value == ControlEffectiveness.NOT_ASSESSED:
            raise ValueError(
                "effectiveness_rating may not be NOT_ASSESSED -- that is the absence of an assessment, "
                "never itself an assessed conclusion."
            )
        return value


class RiskAssessmentControlEvidenceLinkRead(BaseModel):
    """`POST`/response shape for
    `.../controls/{control_id}/evidence/{evidence_id}` -- the link row
    itself plus the linked evidence's own current data (never a second,
    competing copy of it), mirroring `RiskAssessmentLinkedActionRead`'s
    own "relationship + denormalized read-only context" shape."""

    id: uuid.UUID
    control_id: uuid.UUID
    finding_evidence_id: uuid.UUID
    evidence: RiskEvidenceRead
    created_at: datetime


# --- Findings ------------------------------------------------------------------------------


class RiskAssessmentFindingCreate(BaseModel):
    """`POST /risk-assessments/{assessment_id}/findings` body — a
    directly human-authored finding (`source` defaults to `MANUAL`,
    `candidate_status` stays `NULL`). System-generated candidates are
    never created through this endpoint -- they come only from
    `app/risk_assessment/candidate_generation.py`, automatically, at
    assessment creation (item 15's own "candidate ≠ approved risk"
    boundary: a human authoring a finding directly here is making an
    assessment, not proposing a candidate for later review).

    `risk_area_concept_id` (SIE Milestone 25A) is the id of a governed
    `OntologyConcept` -- never an arbitrary string assumed valid; see
    `app/risk_assessment/risk_area_resolution.py::resolve_risk_area_concept()`,
    the one place `app/api/v1/risk_assessments.py::create_finding()`
    resolves and validates it (must be `APPROVED`, `is_risk_area_eligible`,
    and either GLOBAL or belonging to this same organization)."""

    model_config = ConfigDict(extra="forbid")

    risk_area_concept_id: uuid.UUID
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
    # SIE Milestone 26, item 2: the response to this finding. Settable to
    # link, or explicitly `null` to unlink -- distinguished from "not
    # supplied at all" via `model_fields_set`, the same pattern already
    # used for every other field here (see
    # `app/api/v1/risk_assessments.py::update_finding()`).
    linked_action_id: uuid.UUID | None = None

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


class RiskAreaConceptRead(BaseModel):
    """SIE Milestone 25A, item 18. Not built via `from_attributes` --
    `OntologyConcept` has no `label`/`scope` attribute of its own (see
    `app/api/v1/risk_assessments.py::_to_risk_area_concept_read()`, the
    one place this is assembled from a finding's own `risk_area_concept`
    relationship plus its own `risk_area_ontology_version` snapshot).
    `label` is a deterministic, derived display string (title-cased
    `concept_key`) -- not a second, persisted, hand-maintained field on
    `OntologyConcept` (no existing SIE ontology response convention
    defines one)."""

    concept_id: uuid.UUID
    concept_key: str
    label: str
    layer: str
    parent_domain: str | None
    ontology_version: int
    scope: str  # "GLOBAL" | "ORGANIZATION" -- see OntologyConcept.is_global


class RiskAssessmentFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    risk_area: RiskAreaConceptRead
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
    inherent_risk_methodology_version: str | None
    residual_risk_methodology_version: str | None
    linked_action_id: uuid.UUID | None
    controls: list[RiskControlRead]
    evidence: list[RiskEvidenceRead]
    created_at: datetime
    updated_at: datetime


# --- Finding <-> Action relationship (SIE Milestone 27) -------------------------------------


class RiskAssessmentActionLinkCreate(BaseModel):
    """`POST .../findings/{finding_id}/actions/link` body -- links an
    *already-existing* `SafetyAction` as this finding's response.
    Distinct from `RiskAssessmentFindingActionCreate` below, which
    creates a brand-new one instead."""

    model_config = ConfigDict(extra="forbid")

    action_id: uuid.UUID


class RiskAssessmentFindingActionCreate(BaseModel):
    """`POST .../findings/{finding_id}/actions` body -- creates a new
    `SafetyAction` *from* this finding (item 1's own "Create an action
    from a finding") and links it in the same operation. Mirrors
    `app/schemas/actions.py::SafetyActionCreate`'s own field set, minus
    `site_id`/`source_event_id`/`attributes` (this finding, not a
    site/event/free-form payload, is this action's own origin -- see
    `app/api/v1/risk_assessments.py::create_finding_action()`'s own
    docstring for exactly how that origin is recorded)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=_TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)
    action_type: ActionType
    priority: ActionPriority = ActionPriority.MEDIUM
    owner_user_id: uuid.UUID | None = None
    due_date: datetime | None = None
    external_reference: str | None = Field(default=None, max_length=255)


class RiskAssessmentLinkedActionRead(BaseModel):
    """One row of `GET .../findings/{finding_id}/actions` -- the
    relationship itself, plus a denormalized `action_title`/
    `action_status` read straight from the linked `SafetyAction` (so a
    client can render "3 actions, 1 still OPEN" without a second round
    trip to `GET /actions`) -- never a second, competing copy of the
    action's own data (nothing here is writable)."""

    id: uuid.UUID
    finding_id: uuid.UUID
    action_id: uuid.UUID
    action_title: str
    action_status: str
    created_at: datetime
    created_by_user_id: uuid.UUID | None
    created_by_api_client_id: uuid.UUID | None


class RiskAssessmentLinkedActionListRead(BaseModel):
    items: list[RiskAssessmentLinkedActionRead]
    total: int


class RiskAssessmentFindingClose(BaseModel):
    """`POST .../findings/{finding_id}/close` body -- item 6's own
    "human-controlled and explicitly recorded" finding-closure
    requirement. `closure_reason` is mandatory and may not be blank
    (checked here *and* defensively in
    `app/services/risk_assessment_service.py::require_finding_closable()`,
    the same belt-and-suspenders pattern `RiskAssessmentUpdate.title`
    already uses) -- there is no such thing as an inferred or default
    closure reason."""

    model_config = ConfigDict(extra="forbid")

    closure_reason: str = Field(..., min_length=1, max_length=_NOTES_MAX_LENGTH)

    @field_validator("closure_reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("closure_reason must not be blank.")
        return value


class RiskAssessmentActionOriginFindingRead(BaseModel):
    """One entry of `GET /risk-assessments/actions/{action_id}/findings`
    -- item 1's own "View the originating finding from an action" /
    "action -> finding navigation" requirement. A lean summary, not the
    full `RiskAssessmentFindingRead` shape -- a client already looking
    at one action rarely needs that finding's own controls/evidence/
    intelligence context, only enough to navigate to it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    title: str
    status: FindingStatus


class RiskAssessmentActionFindingsRead(BaseModel):
    action_id: uuid.UUID
    findings: list[RiskAssessmentActionOriginFindingRead]


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
    reference: str | None = Field(default=None, max_length=100)
    assessment_type: AssessmentType
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
    reference: str | None = Field(default=None, max_length=100)
    assessment_type: AssessmentType | None = None
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
    reference: str | None
    assessment_type: AssessmentType
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
