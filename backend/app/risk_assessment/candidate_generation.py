"""Deterministic candidate-finding generation — SIE Milestone 25:
Enterprise Risk Assessment Foundation v0.1, items 14-15, 26-27.

    ANOMALY / PATTERN                    (already-computed, Milestone 23/24)
        -> CANDIDATE FINDING              (this module -- IDENTIFIED, no rating)
            -> HUMAN REVIEW               (app/services/risk_assessment_service.py)
                -> RISK ASSESSMENT        (a human/governed likelihood+consequence)

**This module never produces a likelihood, a consequence, or a risk
classification.** Every `CandidateFindingDraft` it returns has no rating
at all — that is the entire point (item 27's own architectural boundary:
"SIE should not automatically convert statistical intelligence into a
human risk rating"). A candidate is evidence plus a suggested risk area,
nothing more; `app/services/risk_assessment_service.py` persists it with
`candidate_status=IDENTIFIED` and `likelihood=consequence=NULL`, and no
code path anywhere in this codebase ever fills those two columns in
without an explicit, separate human/governed action.

**Reuses `compute_enterprise_intelligence()` unchanged — never a second
computation.** This module issues no query of its own beyond what that
one orchestrator (Milestones 22-24) already runs; `intelligence_context`
(the read-only structured summary a risk assessment also exposes) and
candidate generation both come from the exact same call, with its
calculation versions preserved verbatim (item 26) rather than recomputed
or mutated.

**Deliberately narrow v0.1 source coverage.** Only `ANOMALOUS` anomalies
and `RECURRING`/`HIGH_RECURRENCE` patterns become candidates — the two
clearest, most directly evidenced signals. Associations, concentrations,
indicators, and trend are still fully exposed via `intelligence_context`
(nothing is hidden), but do not yet auto-draft a candidate finding in
this milestone — documented as a deliberate, narrower initial scope
(mirrors item 22's own "keep the milestone focused on the foundational
lifecycle, do not blindly implement every endpoint" instruction, applied
here to candidate-source coverage instead of API surface). A future
milestone may widen this list; doing so requires no schema change, only
a new mapping table below.

**Closed, governed risk-area mapping (item 6) — never a fabricated risk
area.** A metric/pattern with no unambiguous `RiskArea` mapping (e.g.
`observation_count`/`unsafe_observation_count`, whose subtype could be
any number of risk areas) is simply skipped, never assigned an arbitrary
or guessed category.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.intelligence.enterprise_intelligence_service import compute_enterprise_intelligence
from app.models.risk_assessment_enums import FindingSource, RiskArea, RiskEvidenceType

_MAX_EVENT_EVIDENCE_PER_CANDIDATE = 20

# item 14: "elevated deterministic risk, anomalies, recurring patterns,
# strong associations, concentrations, indicators, trends" -- only the
# metrics/subtypes below have one unambiguous RiskArea; everything else
# is deliberately omitted rather than guessed (item 6).
_ANOMALY_METRIC_RISK_AREA: dict[str, RiskArea] = {
    "vehicle_incident_count": RiskArea.VEHICLE_SAFETY,
    "incident_count": RiskArea.INCIDENT_SAFETY,
    "near_miss_count": RiskArea.INCIDENT_SAFETY,
    "injury_event_count": RiskArea.INCIDENT_SAFETY,
    "property_damage_event_count": RiskArea.INCIDENT_SAFETY,
}

_PATTERN_SUBTYPE_RISK_AREA: dict[str, RiskArea] = {
    "VEHICLE_INCIDENT": RiskArea.VEHICLE_SAFETY,
    "FIRE": RiskArea.FIRE_SAFETY,
}
_PATTERN_EVENT_TYPE_RISK_AREA: dict[str, RiskArea] = {
    "INCIDENT": RiskArea.INCIDENT_SAFETY,
    "NEAR_MISS": RiskArea.INCIDENT_SAFETY,
}

_NOTABLE_RECURRENCE_CLASSIFICATIONS = ("RECURRING", "HIGH_RECURRENCE")


@dataclass
class CandidateEvidenceDraft:
    evidence_type: str  # RiskEvidenceType value
    reference_id: uuid.UUID | None
    reference_label: str | None


@dataclass
class CandidateFindingDraft:
    risk_area: str  # RiskArea value
    title: str
    description: str  # system evidence -- factual, machine-written (item 7)
    system_analysis_summary: str | None
    source: str  # FindingSource value
    originating_calculation_version: str
    occurrence_period_start: datetime | None
    occurrence_period_end: datetime | None
    evidence: list[CandidateEvidenceDraft] = field(default_factory=list)


def _anomaly_candidate(anomaly) -> CandidateFindingDraft | None:
    risk_area = _ANOMALY_METRIC_RISK_AREA.get(anomaly.metric)
    if risk_area is None:
        return None
    if anomaly.z_score is not None:
        description = (
            f"{anomaly.label} was {anomaly.current_value:g} this period versus a historical baseline mean of "
            f"{anomaly.baseline_mean:g} (z={anomaly.z_score:g})."
        )
    else:
        description = (
            f"{anomaly.label} was {anomaly.current_value:g} this period versus a constant historical baseline of "
            f"{anomaly.baseline_mean:g}."
        )
    evidence = [
        CandidateEvidenceDraft(
            evidence_type=RiskEvidenceType.ANOMALY.value, reference_id=None, reference_label=f"anomaly:{anomaly.metric}"
        )
    ]
    evidence.extend(
        CandidateEvidenceDraft(evidence_type=RiskEvidenceType.EVENT.value, reference_id=event_id, reference_label=None)
        for event_id in anomaly.supporting_event_ids[:_MAX_EVENT_EVIDENCE_PER_CANDIDATE]
    )
    return CandidateFindingDraft(
        risk_area=risk_area.value,
        title=f"Anomalous {anomaly.label.lower()} ({anomaly.direction.replace('_', ' ').lower()})",
        description=description,
        system_analysis_summary=(
            f"Classified {anomaly.status}/{anomaly.direction} by calculation_version={anomaly.calculation_version}."
        ),
        source=FindingSource.INTELLIGENCE_ANOMALY.value,
        originating_calculation_version=anomaly.calculation_version,
        occurrence_period_start=anomaly.current_period_start,
        occurrence_period_end=anomaly.current_period_end,
        evidence=evidence,
    )


def _pattern_candidate(pattern) -> CandidateFindingDraft | None:
    risk_area = None
    if pattern.event_subtype is not None:
        risk_area = _PATTERN_SUBTYPE_RISK_AREA.get(pattern.event_subtype)
    if risk_area is None:
        risk_area = _PATTERN_EVENT_TYPE_RISK_AREA.get(pattern.event_type)
    if risk_area is None:
        return None
    subject = pattern.event_subtype or pattern.event_type
    description = (
        f"{subject} recurred {pattern.count} times at {pattern.site_label} between "
        f"{pattern.first_seen.date().isoformat()} and {pattern.last_seen.date().isoformat()} "
        f"({pattern.classification})."
    )
    evidence = [
        CandidateEvidenceDraft(evidence_type=RiskEvidenceType.PATTERN.value, reference_id=None, reference_label=pattern.pattern_key)
    ]
    evidence.extend(
        CandidateEvidenceDraft(evidence_type=RiskEvidenceType.EVENT.value, reference_id=event_id, reference_label=None)
        for event_id in pattern.supporting_event_ids[:_MAX_EVENT_EVIDENCE_PER_CANDIDATE]
    )
    return CandidateFindingDraft(
        risk_area=risk_area.value,
        title=f"Recurring {subject.lower()} pattern at {pattern.site_label}",
        description=description,
        system_analysis_summary=None,
        source=FindingSource.INTELLIGENCE_PATTERN.value,
        originating_calculation_version=pattern.calculation_version,
        occurrence_period_start=pattern.first_seen,
        occurrence_period_end=pattern.last_seen,
        evidence=evidence,
    )


def generate_candidate_findings(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: str,  # "organization" | "site" -- see compute_enterprise_intelligence()
    site_id: uuid.UUID | None,
    as_of: datetime,
    window_days: int,
) -> list[CandidateFindingDraft]:
    """Deterministic given identical inputs (same `as_of`, same
    already-point-in-time-correct event data) -- calling this twice for
    the same assessment produces the identical candidate set, the same
    reproducibility guarantee every Milestone 22-24 computation already
    provides."""
    result = compute_enterprise_intelligence(
        db, organization_id=organization_id, scope=scope, site_id=site_id, as_of=as_of, window_days=window_days
    )
    drafts: list[CandidateFindingDraft] = []
    for anomaly in result.anomalies:
        if anomaly.status != "ANOMALOUS":
            continue
        draft = _anomaly_candidate(anomaly)
        if draft is not None:
            drafts.append(draft)
    for pattern in result.patterns:
        if pattern.classification not in _NOTABLE_RECURRENCE_CLASSIFICATIONS:
            continue
        draft = _pattern_candidate(pattern)
        if draft is not None:
            drafts.append(draft)
    return drafts


__all__ = ["CandidateEvidenceDraft", "CandidateFindingDraft", "generate_candidate_findings"]
