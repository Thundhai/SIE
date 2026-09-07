"""Risk Assessment Reporting API schemas — SIE Milestone 28: Enterprise
Risk Assessment Reporting & Decision Intelligence v0.1. Built directly
from `app/risk_assessment/reporting.py`'s own dataclasses — no second,
competing representation, mirroring every other schema module in this
codebase. `GET /risk-assessments/{id}/report`/`/readiness` are the only
two routes that use these; nothing here is ever accepted as request
input (this milestone is read-only end to end).

**Export-ready structure (item 9).** Every field below is a plain,
named, typed value — never free text a future PDF/Excel exporter would
need to parse — so that presentation layer can be built later against
this same response shape without touching the computation in
`app/risk_assessment/reporting.py` at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.risk_assessment_enums import AssessmentType, RiskAssessmentStatus


class RiskBandCountsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    critical: int
    high: int
    moderate: int
    low: int
    unrated: int


class RiskDistributionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inherent: RiskBandCountsRead
    residual: RiskBandCountsRead


class RiskAreaSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    concept_id: uuid.UUID
    concept_key: str
    label: str
    layer: str
    parent_domain: str | None
    scope: str
    finding_count: int
    highest_inherent_risk_score: int | None
    highest_inherent_risk_classification: str | None
    highest_residual_risk_score: int | None
    highest_residual_risk_classification: str | None
    open_finding_count: int
    closed_finding_count: int
    associated_action_count: int


class ActionResponseSummaryRead(BaseModel):
    """`computed_at` is when this section's *current* action-state
    counts were computed — deliberately not the assessment's own
    `as_of`; see `app/risk_assessment/reporting.py::ActionResponseSummary`'s
    own docstring for why these two are never the same timestamp."""

    model_config = ConfigDict(from_attributes=True)

    findings_with_no_response_action: int
    findings_with_one_response_action: int
    findings_with_multiple_response_actions: int
    total_response_actions: int
    completed_response_actions: int
    cancelled_response_actions: int
    outstanding_response_actions: int
    overdue_response_actions: int
    computed_at: datetime


class EvidenceCoverageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_findings: int
    findings_with_event_evidence: int
    findings_with_knowledge_evidence: int
    findings_with_action_evidence: int
    findings_with_intelligence_evidence: int
    findings_with_multiple_evidence_types: int
    findings_with_no_evidence: int


class ControlEffectivenessSummaryRead(BaseModel):
    """SIE Milestone 29: Enterprise Risk Assessment Evidence & Control
    Effectiveness Foundation v0.1. Entirely historical (like every
    section here besides `action_response_summary`) -- controls and
    their evidence links are subject to the same `require_editable()`
    immutability as findings, so this carries no `computed_at` of its
    own."""

    model_config = ConfigDict(from_attributes=True)

    total_controls: int
    implementation_status_counts: dict[str, int]
    effectiveness_rating_counts: dict[str, int]
    findings_with_no_controls: int
    findings_with_controls_but_no_effectiveness_assessment: int
    findings_with_ineffective_or_partially_effective_controls: int
    assessed_controls_with_evidence: int
    assessed_controls_without_evidence: int


class AssessmentReadinessRead(BaseModel):
    """A readiness *indicator*, never an approval recommendation --
    `status` is exactly `"READY"`/`"NOT_READY"`; `reasons` are plain
    factual statements, never a suggestion of what to do about them."""

    model_config = ConfigDict(from_attributes=True)

    status: str
    reasons: list[str]
    unrated_finding_count: int
    pending_candidate_review_count: int
    findings_without_evidence_count: int
    unresolved_high_risk_finding_count: int
    high_risk_findings_without_action_count: int
    has_no_findings: bool


class AssessmentSummaryCountsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_count: int
    findings_by_status: dict[str, int]
    findings_by_candidate_status: dict[str, int]
    unrated_finding_count: int
    linked_action_count: int
    action_status_counts: dict[str, int]


class RiskAssessmentReportRead(BaseModel):
    """`GET /risk-assessments/{assessment_id}/report`'s full response.
    The identity fields at the top (id/reference/assessment_type/.../
    status) are read directly off the `RiskAssessment` row itself --
    for an `APPROVED`/`SUPERSEDED`/`ARCHIVED` assessment these, and
    every finding-derived section below, are the historical snapshot
    (item 7) simply because the underlying rows can no longer change;
    only `action_response_summary` reflects *current* state -- see that
    section's own docstring."""

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    reference: str | None
    title: str
    assessment_type: AssessmentType
    assessment_date: datetime
    as_of: datetime
    methodology_version: str
    status: RiskAssessmentStatus
    version: int
    lineage_id: uuid.UUID
    supersedes_id: uuid.UUID | None

    assessment_summary: AssessmentSummaryCountsRead
    risk_distribution: RiskDistributionRead
    risk_areas: list[RiskAreaSummaryRead]
    action_response_summary: ActionResponseSummaryRead
    evidence_coverage: EvidenceCoverageRead
    control_effectiveness: ControlEffectivenessSummaryRead
    readiness: AssessmentReadinessRead
    generated_at: datetime


class AssessmentReadinessResponse(BaseModel):
    """`GET /risk-assessments/{assessment_id}/readiness`'s response --
    the same `readiness` computation `RiskAssessmentReportRead` carries,
    exposed on its own lightweight route for a caller that wants only
    this one signal (no full report query cost difference either way --
    see that route's own docstring)."""

    assessment_id: uuid.UUID
    readiness: AssessmentReadinessRead
    generated_at: datetime


__all__ = [
    "ActionResponseSummaryRead",
    "AssessmentReadinessRead",
    "AssessmentReadinessResponse",
    "AssessmentSummaryCountsRead",
    "ControlEffectivenessSummaryRead",
    "EvidenceCoverageRead",
    "RiskAreaSummaryRead",
    "RiskAssessmentReportRead",
    "RiskBandCountsRead",
    "RiskDistributionRead",
]
