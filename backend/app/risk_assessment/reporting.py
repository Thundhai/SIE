"""Enterprise Risk Assessment Reporting & Decision Intelligence — SIE
Milestone 28: turns the existing, unmodified
`Intelligence -> Risk Assessment -> Findings -> Actions` chain into a
governed *management decision/reporting layer* — a deterministic,
explainable summary of one already-persisted assessment, never a new
risk-calculation methodology, ontology, or intelligence engine.

**Read-only, by construction.** Every function here takes an
already-loaded `RiskAssessment` (with its `findings` — and each
finding's own `evidence`/`controls`/`risk_area_concept` — already
eager-loaded by the caller, see `app/api/v1/risk_assessments.py::
_get_owned_assessment_or_404()`) plus one additional query for the
finding<->action relationships (SIE Milestone 27). Nothing here ever
calls `db.add()`, `db.flush()`, or `db.commit()` — there is no mutation
path through this module at all.

**Reuses, never recomputes, every existing rating/classification.**
`inherent_risk_score`/`inherent_risk_classification`/
`residual_risk_score`/`residual_risk_classification` are read directly
off each `RiskAssessmentFinding` row — the exact values
`app/risk_assessment/risk_matrix.py::calculate_risk()` already computed
and `app/services/risk_assessment_service.py` already persisted. This
module performs no likelihood x consequence arithmetic of its own, ever.

**Historical integrity (item 7) — free, not engineered.** A finding row
belonging to an `APPROVED`/`SUPERSEDED`/`ARCHIVED` assessment can never
be mutated (`require_editable()`, `app/services/risk_assessment_service.py`
— enforced since Milestone 25) — so simply reading `assessment.findings`
fresh from the database *is* the historical snapshot; no separate
snapshot table or copy-on-approve mechanism is needed. The one place
this module deliberately reads *current*, not historical, state is
`ActionResponseSummary` (SafetyAction status/due_date change freely
after an assessment is approved, by design — see SIE Milestone 27's own
"a completed action never automatically closes a finding") — its own
`computed_at` field exists precisely so a caller can tell the two apart;
see `ActionResponseSummary`'s own docstring.

**Exactly two queries, regardless of finding count (item 10).** The
caller's own `_get_owned_assessment_or_404()` query already eager-loads
every finding's `evidence`/`controls`/`risk_area_concept` in one
round trip; `_load_finding_actions()` below is the one additional query
this module issues, fetching every `RiskAssessmentFindingAction` row (and
its linked `SafetyAction`, eager-loaded) for every finding at once. No
function below issues a query inside a loop over findings — see
`tests/test_risk_assessment_report.py`'s own dedicated query-count
regression tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.risk_assessment import RiskAssessment, RiskAssessmentFinding
from app.models.risk_assessment_enums import ControlEffectiveness, ControlStatus, FindingStatus, RiskCandidateStatus
from app.models.risk_assessment_finding_action import RiskAssessmentFindingAction
from app.models.safety_action import SafetyAction
from app.models.safety_action_enums import ActionStatus
from app.services.risk_assessment_service import is_rated_finding

# The four risk-matrix bands this module ever aggregates over -- the
# exact vocabulary `app/models/risk_assessment_enums.py::RiskAssessmentRiskBand`
# already defines; never a fifth, invented band.
_RISK_BANDS = ("CRITICAL", "HIGH", "MODERATE", "LOW")

# The three RiskEvidenceType groupings item 5 names -- ANOMALY/PATTERN/
# ASSOCIATION are each a *computed* intelligence result (Milestones
# 23/24), grouped here under one "intelligence evidence" umbrella exactly
# as the milestone spec's own §5 names it. EVENT/KNOWLEDGE_DOCUMENT/ACTION
# are each their own named category. OTHER fits none of the four named
# categories (by design -- it is a deliberate catch-all, not a fifth
# governed bucket) but still counts as "has evidence", never "no evidence".
_INTELLIGENCE_EVIDENCE_TYPES = frozenset({"ANOMALY", "PATTERN", "ASSOCIATION"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Dataclasses -----------------------------------------------------------------------------


@dataclass
class RiskBandCounts:
    """One risk-matrix distribution (item 2) -- either inherent or
    residual, never both in one object (the milestone's own "must
    clearly distinguish the two" instruction)."""

    critical: int = 0
    high: int = 0
    moderate: int = 0
    low: int = 0
    #: Ratable findings (see `is_rated_finding()`) with no score yet for
    #: *this* dimension -- e.g. a finding may have an inherent rating but
    #: no residual one; `unrated` on the residual side reflects that
    #: correctly and is expected to usually be larger than the inherent
    #: side's own `unrated` count.
    unrated: int = 0


@dataclass
class RiskDistribution:
    inherent: RiskBandCounts
    residual: RiskBandCounts


@dataclass
class RiskAreaSummary:
    """One row of item 3's per-risk-area table. `concept_key`/`label`/
    `layer`/`parent_domain`/`scope` are read from the finding's own
    `risk_area_concept` relationship -- a governed `OntologyConcept` row
    that is never deleted (only status-transitioned, e.g. to
    `DEPRECATED`), so this stays correctly resolvable for a historical
    report even after the concept is later deprecated (item 7's own
    "deprecated ontology concept... remains correctly represented")."""

    concept_id: uuid.UUID
    concept_key: str
    label: str
    layer: str
    parent_domain: str | None
    scope: str  # "GLOBAL" | "ORGANIZATION"
    finding_count: int = 0
    highest_inherent_risk_score: int | None = None
    highest_inherent_risk_classification: str | None = None
    highest_residual_risk_score: int | None = None
    highest_residual_risk_classification: str | None = None
    open_finding_count: int = 0
    closed_finding_count: int = 0
    #: Distinct `SafetyAction`s linked (SIE Milestone 27) to any finding
    #: in this risk area -- current linkage, not historical (see module
    #: docstring).
    associated_action_count: int = 0


@dataclass
class ActionResponseSummary:
    """Item 4. **Current** action state, deliberately -- a `SafetyAction`
    linked to a finding keeps progressing after the assessment itself is
    `APPROVED` (SIE Milestone 27's own point), so this section is always
    computed as of `computed_at` (effectively "now"), never the
    assessment's own historical `as_of`. A completed action is counted
    here as `completed_response_actions` and nowhere else -- this module
    never infers, derives, or exposes a "therefore the finding is
    resolved" conclusion from that count (SIE Milestone 27's own explicit
    "that would be unsafe" boundary, unchanged)."""

    findings_with_no_response_action: int = 0
    findings_with_one_response_action: int = 0
    findings_with_multiple_response_actions: int = 0
    total_response_actions: int = 0
    completed_response_actions: int = 0
    cancelled_response_actions: int = 0
    outstanding_response_actions: int = 0
    overdue_response_actions: int = 0
    computed_at: datetime = field(default_factory=utcnow)


@dataclass
class EvidenceCoverage:
    """Item 5. Deterministic counts only -- no confidence score, no
    weighting, no judgment about whether the evidence is *good*, only
    whether each finding has at least one row of each named type."""

    total_findings: int = 0
    findings_with_event_evidence: int = 0
    findings_with_knowledge_evidence: int = 0
    findings_with_action_evidence: int = 0
    findings_with_intelligence_evidence: int = 0
    findings_with_multiple_evidence_types: int = 0
    findings_with_no_evidence: int = 0


@dataclass
class ControlEffectivenessSummary:
    """SIE Milestone 29: Enterprise Risk Assessment Evidence & Control
    Effectiveness Foundation v0.1. Deterministic counts only over
    `RiskAssessmentControl` rows already eager-loaded on each finding
    (via `finding.controls`) -- no new query, no invented "control
    effectiveness score." Entirely historical, unlike
    `ActionResponseSummary` above: a control (and its evidence links)
    are subject to the identical `require_editable()` immutability every
    finding already has, so this section carries no `computed_at` -- it
    is part of the same historical snapshot as everything else in
    `RiskAssessmentReport` besides `action_response_summary`.

    `implementation_status_counts`/`effectiveness_rating_counts` are
    keyed by the exact `ControlStatus`/`ControlEffectiveness` enum
    values (never a fifth, invented bucket). `assessed_controls_with_evidence`/
    `assessed_controls_without_evidence` count only controls whose
    `effectiveness != NOT_ASSESSED` -- an unassessed control's evidence
    coverage is not yet a meaningful question (its effectiveness
    conclusion doesn't exist yet to be "supported")."""

    total_controls: int = 0
    implementation_status_counts: dict[str, int] = field(default_factory=dict)
    effectiveness_rating_counts: dict[str, int] = field(default_factory=dict)
    findings_with_no_controls: int = 0
    findings_with_controls_but_no_effectiveness_assessment: int = 0
    findings_with_ineffective_or_partially_effective_controls: int = 0
    assessed_controls_with_evidence: int = 0
    assessed_controls_without_evidence: int = 0


@dataclass
class AssessmentReadiness:
    """Item 6. A *readiness indicator*, never an approval recommendation
    -- `status` is exactly `"READY"`/`"NOT_READY"`, `reasons` is a list of
    plain, factual statements (e.g. `"3 findings remain unrated."`), and
    nothing here ever says what a human should do about it."""

    status: str  # "READY" | "NOT_READY"
    reasons: list[str] = field(default_factory=list)
    unrated_finding_count: int = 0
    pending_candidate_review_count: int = 0
    findings_without_evidence_count: int = 0
    unresolved_high_risk_finding_count: int = 0
    high_risk_findings_without_action_count: int = 0
    has_no_findings: bool = False


@dataclass
class AssessmentSummary:
    """Item 1's own per-assessment counts. Identity fields (id/reference/
    title/organization/site/dates/methodology_version/status/...) are
    assembled by the API layer directly from the `RiskAssessment` row
    itself (`app/api/v1/risk_assessments.py::_assessment_fields()`) --
    this dataclass carries only the *computed* counts item 1 additionally
    asks for, several of which are simply references into
    `RiskDistribution`/`ActionResponseSummary` below (computed once,
    never twice)."""

    finding_count: int = 0
    findings_by_status: dict[str, int] = field(default_factory=dict)
    findings_by_candidate_status: dict[str, int] = field(default_factory=dict)
    unrated_finding_count: int = 0
    linked_action_count: int = 0
    action_status_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class RiskAssessmentReport:
    assessment_summary: AssessmentSummary
    risk_distribution: RiskDistribution
    risk_areas: list[RiskAreaSummary]
    action_response_summary: ActionResponseSummary
    evidence_coverage: EvidenceCoverage
    control_effectiveness: ControlEffectivenessSummary
    readiness: AssessmentReadiness
    generated_at: datetime = field(default_factory=utcnow)


# --- Query --------------------------------------------------------------------------------


def _load_finding_actions(db: Session, *, finding_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[SafetyAction]]:
    """The one additional query this module issues (see module
    docstring) -- every `RiskAssessmentFindingAction` relationship row
    for every finding in this assessment, at once, with its linked
    `SafetyAction` eager-loaded in the same round trip. Empty (and
    query-free) for an assessment with no findings at all."""
    if not finding_ids:
        return {}
    rows = db.execute(
        select(RiskAssessmentFindingAction)
        .options(joinedload(RiskAssessmentFindingAction.action))
        .where(RiskAssessmentFindingAction.finding_id.in_(finding_ids))
    ).scalars().all()
    by_finding: dict[uuid.UUID, list[SafetyAction]] = {finding_id: [] for finding_id in finding_ids}
    for row in rows:
        by_finding[row.finding_id].append(row.action)
    return by_finding


# --- Pure aggregation helpers (no queries) -------------------------------------------------


def _band_key(classification: str | None) -> str | None:
    if classification is None:
        return None
    return classification if classification in _RISK_BANDS else None


def _action_state(action: SafetyAction, *, now: datetime) -> str:
    """`"COMPLETED"` / `"CANCELLED"` / `"OVERDUE"` / `"OUTSTANDING"` --
    current state only, mirrors (but does not reuse -- there is no
    historical `as_of` question here, see `ActionResponseSummary`'s own
    docstring) the exact overdue definition
    `app/intelligence/enterprise_intelligence_service.py::_actions_context()`
    already established: a `due_date` in the past on a still-open action,
    never a status-only guess."""
    if action.status == ActionStatus.COMPLETED:
        return "COMPLETED"
    if action.status == ActionStatus.CANCELLED:
        return "CANCELLED"
    due_date = action.due_date
    if due_date is not None:
        due = due_date if due_date.tzinfo is not None else due_date.replace(tzinfo=timezone.utc)
        if due < now:
            return "OVERDUE"
    return "OUTSTANDING"


def _evidence_categories(finding: RiskAssessmentFinding) -> set[str]:
    categories: set[str] = set()
    for ev in finding.evidence:
        evidence_type = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else ev.evidence_type
        if evidence_type == "EVENT":
            categories.add("EVENT")
        elif evidence_type == "KNOWLEDGE_DOCUMENT":
            categories.add("KNOWLEDGE_DOCUMENT")
        elif evidence_type == "ACTION":
            categories.add("ACTION")
        elif evidence_type in _INTELLIGENCE_EVIDENCE_TYPES:
            categories.add("INTELLIGENCE")
        else:
            categories.add("OTHER")
    return categories


def _risk_area_display(finding: RiskAssessmentFinding) -> tuple[uuid.UUID, str, str, str, str | None, str]:
    concept = finding.risk_area_concept
    label = concept.concept_key.replace("_", " ").title()
    scope = "GLOBAL" if concept.organization_id is None else "ORGANIZATION"
    return concept.id, concept.concept_key, label, concept.layer, concept.parent_domain, scope


# --- Assembly ------------------------------------------------------------------------------


def compute_risk_assessment_report(db: Session, assessment: RiskAssessment) -> RiskAssessmentReport:
    """The one place a full report is assembled -- single pass over
    `assessment.findings` (already loaded by the caller) plus the one
    finding<->action query above, never re-querying per finding."""
    findings = list(assessment.findings)
    finding_ids = [f.id for f in findings]
    actions_by_finding = _load_finding_actions(db, finding_ids=finding_ids)
    now = utcnow()

    findings_by_status: dict[str, int] = {s.value: 0 for s in FindingStatus}
    findings_by_candidate_status: dict[str, int] = {s.value: 0 for s in RiskCandidateStatus}
    findings_by_candidate_status["MANUAL"] = 0  # candidate_status IS NULL -- directly human-authored

    inherent = RiskBandCounts()
    residual = RiskBandCounts()

    risk_area_groups: dict[uuid.UUID, RiskAreaSummary] = {}
    risk_area_actions: dict[uuid.UUID, set[uuid.UUID]] = {}

    evidence = EvidenceCoverage(total_findings=len(findings))

    unrated_count = 0
    pending_candidate_review_count = 0
    findings_without_evidence_count = 0
    unresolved_high_risk_count = 0
    high_risk_without_action_count = 0

    no_response_count = 0
    one_response_count = 0
    multiple_response_count = 0
    all_linked_action_ids: set[uuid.UUID] = set()
    action_state_counts: dict[str, int] = {"COMPLETED": 0, "CANCELLED": 0, "OUTSTANDING": 0, "OVERDUE": 0}

    # --- Control effectiveness (SIE Milestone 29) ---------------------------------------------
    total_controls = 0
    implementation_status_counts: dict[str, int] = {s.value: 0 for s in ControlStatus}
    effectiveness_rating_counts: dict[str, int] = {e.value: 0 for e in ControlEffectiveness}
    findings_with_no_controls = 0
    findings_with_controls_but_no_effectiveness_assessment = 0
    findings_with_ineffective_or_partially_effective_controls = 0
    assessed_controls_with_evidence = 0
    assessed_controls_without_evidence = 0

    for finding in findings:
        findings_by_status[finding.status.value] = findings_by_status.get(finding.status.value, 0) + 1
        candidate_key = finding.candidate_status.value if finding.candidate_status is not None else "MANUAL"
        findings_by_candidate_status[candidate_key] = findings_by_candidate_status.get(candidate_key, 0) + 1
        if finding.candidate_status in (RiskCandidateStatus.IDENTIFIED, RiskCandidateStatus.UNDER_REVIEW):
            pending_candidate_review_count += 1

        ratable = is_rated_finding(finding)
        if ratable and finding.likelihood is None:
            unrated_count += 1
        inherent_band = _band_key(finding.inherent_risk_classification)
        if inherent_band is not None:
            setattr(inherent, inherent_band.lower(), getattr(inherent, inherent_band.lower()) + 1)
        elif ratable:
            inherent.unrated += 1
        residual_band = _band_key(finding.residual_risk_classification)
        if residual_band is not None:
            setattr(residual, residual_band.lower(), getattr(residual, residual_band.lower()) + 1)
        elif ratable:
            residual.unrated += 1

        # Item 6: "unresolved critical/high findings" -- the *effective*
        # rating (residual once supplied, since that is the risk view
        # after controls; inherent otherwise), on a not-yet-CLOSED finding.
        effective_band = residual_band or inherent_band
        is_unresolved_high_risk = (
            effective_band in ("CRITICAL", "HIGH") and finding.status != FindingStatus.CLOSED
        )
        if is_unresolved_high_risk:
            unresolved_high_risk_count += 1

        # --- Risk area aggregation (item 3) -------------------------------------------------
        concept_id, concept_key, label, layer, parent_domain, scope = _risk_area_display(finding)
        group = risk_area_groups.get(concept_id)
        if group is None:
            group = RiskAreaSummary(
                concept_id=concept_id, concept_key=concept_key, label=label, layer=layer,
                parent_domain=parent_domain, scope=scope,
            )
            risk_area_groups[concept_id] = group
            risk_area_actions[concept_id] = set()
        group.finding_count += 1
        if finding.inherent_risk_score is not None and (
            group.highest_inherent_risk_score is None or finding.inherent_risk_score > group.highest_inherent_risk_score
        ):
            group.highest_inherent_risk_score = finding.inherent_risk_score
            group.highest_inherent_risk_classification = finding.inherent_risk_classification
        if finding.residual_risk_score is not None and (
            group.highest_residual_risk_score is None or finding.residual_risk_score > group.highest_residual_risk_score
        ):
            group.highest_residual_risk_score = finding.residual_risk_score
            group.highest_residual_risk_classification = finding.residual_risk_classification
        if finding.status == FindingStatus.OPEN:
            group.open_finding_count += 1
        elif finding.status == FindingStatus.CLOSED:
            group.closed_finding_count += 1

        # --- Evidence coverage (item 5) -----------------------------------------------------
        categories = _evidence_categories(finding)
        if not categories:
            findings_without_evidence_count += 1
            evidence.findings_with_no_evidence += 1
        else:
            if "EVENT" in categories:
                evidence.findings_with_event_evidence += 1
            if "KNOWLEDGE_DOCUMENT" in categories:
                evidence.findings_with_knowledge_evidence += 1
            if "ACTION" in categories:
                evidence.findings_with_action_evidence += 1
            if "INTELLIGENCE" in categories:
                evidence.findings_with_intelligence_evidence += 1
            if len(categories) > 1:
                evidence.findings_with_multiple_evidence_types += 1

        # --- Control effectiveness (SIE Milestone 29) ----------------------------------------
        controls = finding.controls
        if not controls:
            findings_with_no_controls += 1
        else:
            has_assessed_control = False
            has_weak_control = False
            for control in controls:
                total_controls += 1
                implementation_status_counts[control.status.value] = (
                    implementation_status_counts.get(control.status.value, 0) + 1
                )
                effectiveness_rating_counts[control.effectiveness.value] = (
                    effectiveness_rating_counts.get(control.effectiveness.value, 0) + 1
                )
                if control.effectiveness != ControlEffectiveness.NOT_ASSESSED:
                    has_assessed_control = True
                    if control.control_evidence:
                        assessed_controls_with_evidence += 1
                    else:
                        assessed_controls_without_evidence += 1
                if control.effectiveness in (
                    ControlEffectiveness.INEFFECTIVE, ControlEffectiveness.PARTIALLY_EFFECTIVE,
                ):
                    has_weak_control = True
            if not has_assessed_control:
                findings_with_controls_but_no_effectiveness_assessment += 1
            if has_weak_control:
                findings_with_ineffective_or_partially_effective_controls += 1

        # --- Action response summary (item 4) -----------------------------------------------
        linked_actions = actions_by_finding.get(finding.id, [])
        action_count = len(linked_actions)
        if action_count == 0:
            no_response_count += 1
            if is_unresolved_high_risk:
                high_risk_without_action_count += 1
        elif action_count == 1:
            one_response_count += 1
        else:
            multiple_response_count += 1
        for action in linked_actions:
            all_linked_action_ids.add(action.id)
            risk_area_actions[concept_id].add(action.id)
            action_state_counts[_action_state(action, now=now)] += 1

    for concept_id, group in risk_area_groups.items():
        group.associated_action_count = len(risk_area_actions[concept_id])

    action_summary = ActionResponseSummary(
        findings_with_no_response_action=no_response_count,
        findings_with_one_response_action=one_response_count,
        findings_with_multiple_response_actions=multiple_response_count,
        total_response_actions=len(all_linked_action_ids),
        completed_response_actions=action_state_counts["COMPLETED"],
        cancelled_response_actions=action_state_counts["CANCELLED"],
        outstanding_response_actions=action_state_counts["OUTSTANDING"],
        overdue_response_actions=action_state_counts["OVERDUE"],
        computed_at=now,
    )

    readiness_reasons: list[str] = []
    has_no_findings = len(findings) == 0
    if has_no_findings:
        readiness_reasons.append("Assessment has no findings.")
    if unrated_count:
        readiness_reasons.append(f"{unrated_count} finding(s) remain unrated.")
    if pending_candidate_review_count:
        readiness_reasons.append(f"{pending_candidate_review_count} candidate finding(s) await human review.")
    if findings_without_evidence_count:
        readiness_reasons.append(f"{findings_without_evidence_count} finding(s) have no supporting evidence.")
    if unresolved_high_risk_count:
        readiness_reasons.append(f"{unresolved_high_risk_count} high/critical finding(s) remain unresolved.")
    if high_risk_without_action_count:
        readiness_reasons.append(
            f"{high_risk_without_action_count} high/critical finding(s) have no response action."
        )
    readiness = AssessmentReadiness(
        status="READY" if not readiness_reasons else "NOT_READY",
        reasons=readiness_reasons,
        unrated_finding_count=unrated_count,
        pending_candidate_review_count=pending_candidate_review_count,
        findings_without_evidence_count=findings_without_evidence_count,
        unresolved_high_risk_finding_count=unresolved_high_risk_count,
        high_risk_findings_without_action_count=high_risk_without_action_count,
        has_no_findings=has_no_findings,
    )

    control_effectiveness = ControlEffectivenessSummary(
        total_controls=total_controls,
        implementation_status_counts=implementation_status_counts,
        effectiveness_rating_counts=effectiveness_rating_counts,
        findings_with_no_controls=findings_with_no_controls,
        findings_with_controls_but_no_effectiveness_assessment=findings_with_controls_but_no_effectiveness_assessment,
        findings_with_ineffective_or_partially_effective_controls=findings_with_ineffective_or_partially_effective_controls,
        assessed_controls_with_evidence=assessed_controls_with_evidence,
        assessed_controls_without_evidence=assessed_controls_without_evidence,
    )

    summary = AssessmentSummary(
        finding_count=len(findings),
        findings_by_status=findings_by_status,
        findings_by_candidate_status=findings_by_candidate_status,
        unrated_finding_count=unrated_count,
        linked_action_count=len(all_linked_action_ids),
        action_status_counts=dict(action_state_counts),
    )

    return RiskAssessmentReport(
        assessment_summary=summary,
        risk_distribution=RiskDistribution(inherent=inherent, residual=residual),
        risk_areas=sorted(risk_area_groups.values(), key=lambda g: g.concept_key),
        action_response_summary=action_summary,
        evidence_coverage=evidence,
        control_effectiveness=control_effectiveness,
        readiness=readiness,
        generated_at=now,
    )


__all__ = [
    "ActionResponseSummary",
    "AssessmentReadiness",
    "AssessmentSummary",
    "ControlEffectivenessSummary",
    "EvidenceCoverage",
    "RiskAreaSummary",
    "RiskAssessmentReport",
    "RiskBandCounts",
    "RiskDistribution",
    "compute_risk_assessment_report",
]
