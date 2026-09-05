"""Deterministic candidate-finding generation — SIE Milestone 25:
Enterprise Risk Assessment Foundation v0.1, items 14-15, 26-27; risk-area
resolution updated by SIE Milestone 25A: Governed Risk-Area &
Organization-Extensible Risk Taxonomy v0.1, item 12.

    ANOMALY / PATTERN                    (already-computed, Milestone 23/24)
        -> CANDIDATE FINDING              (this module -- IDENTIFIED, no rating)
            -> HUMAN REVIEW               (app/services/risk_assessment_service.py)
                -> RISK ASSESSMENT        (a human/governed likelihood+consequence)

**This module never produces a likelihood, a consequence, or a risk
classification.** Every `CandidateFindingDraft` it returns has no rating
at all — that is the entire point (item 27's own architectural boundary:
"SIE should not automatically convert statistical intelligence into a
human risk rating"). A candidate is evidence plus a suggested, governed
risk-area concept, nothing more; `app/api/v1/risk_assessments.py`
persists it with `candidate_status=IDENTIFIED` and
`likelihood=consequence=NULL`, and no code path anywhere in this codebase
ever fills those two columns in without an explicit, separate
human/governed action.

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

**Risk-area resolution is now governed, not a closed enum (Milestone
25A).** The static metric/pattern -> risk-area mapping tables below are
unchanged in shape and unchanged in which metrics/subtypes they cover —
only the *target* changed, from a `RiskArea` enum member to a
`(layer, parent_domain, concept_key)` ontology scope key, resolved at
generation time against a real, GLOBAL, `APPROVED`,
`is_risk_area_eligible` `OntologyConcept` row
(`ontology_governance_service.get_concept_by_scope()` +
`get_eligible_risk_area_concept()`). This is deliberately still a
"known deterministic mapping -> governed concept -> candidate" table
(item 12) — never fuzzy/LLM inference, never an organization-specific
override (candidate generation always resolves the GLOBAL SIE concept
for a given metric/subtype, since the *mapping itself* -- "a vehicle
incident anomaly implies the vehicle-safety risk area" -- is not
organization-specific, only which concept row happens to represent that
meaning could theoretically vary, and today it never does). A
metric/pattern with no unambiguous mapping (e.g. `observation_count`/
`unsafe_observation_count`, whose subtype could be any number of risk
areas), or whose mapped concept somehow does not (yet, or no longer)
exist as a GLOBAL, `APPROVED`, risk-area-eligible concept, is simply
skipped — never assigned an arbitrary or guessed category (item 25:
"Never infer... using fuzzy/LLM guessing")."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.intelligence.enterprise_intelligence_service import compute_enterprise_intelligence
from app.models.risk_assessment_enums import FindingSource, RiskEvidenceType
from app.services import ontology_governance_service as ogs

_MAX_EVENT_EVIDENCE_PER_CANDIDATE = 20

#: `(layer, parent_domain, concept_key)` -- the governed ontology scope
#: key a matched metric/subtype resolves to. See
#: `app/risk_assessment/risk_area_ontology_seed.py` for the full
#: rationale of each of these scope keys (all seeded by migration 0017).
_ScopeKey = tuple[str, str | None, str]

# item 14: "elevated deterministic risk, anomalies, recurring patterns,
# strong associations, concentrations, indicators, trends" -- only the
# metrics/subtypes below have one unambiguous risk-area concept;
# everything else is deliberately omitted rather than guessed (item 6).
_ANOMALY_METRIC_RISK_AREA_SCOPE: dict[str, _ScopeKey] = {
    "vehicle_incident_count": ("event_subtype", "INCIDENT", "VEHICLE_INCIDENT"),
    "incident_count": ("event_type", None, "INCIDENT"),
    "near_miss_count": ("event_type", None, "INCIDENT"),
    "injury_event_count": ("event_type", None, "INCIDENT"),
    "property_damage_event_count": ("event_type", None, "INCIDENT"),
}

_PATTERN_SUBTYPE_RISK_AREA_SCOPE: dict[str, _ScopeKey] = {
    "VEHICLE_INCIDENT": ("event_subtype", "INCIDENT", "VEHICLE_INCIDENT"),
    "FIRE": ("observation_topic", "OBSERVATION", "FIRE_SAFETY"),
}
_PATTERN_EVENT_TYPE_RISK_AREA_SCOPE: dict[str, _ScopeKey] = {
    "INCIDENT": ("event_type", None, "INCIDENT"),
    "NEAR_MISS": ("event_type", None, "INCIDENT"),
}

_NOTABLE_RECURRENCE_CLASSIFICATIONS = ("RECURRING", "HIGH_RECURRENCE")


@dataclass
class CandidateEvidenceDraft:
    evidence_type: str  # RiskEvidenceType value
    reference_id: uuid.UUID | None
    reference_label: str | None


@dataclass
class CandidateFindingDraft:
    risk_area_concept_id: uuid.UUID
    risk_area_ontology_version: int
    title: str
    description: str  # system evidence -- factual, machine-written (item 7)
    system_analysis_summary: str | None
    source: str  # FindingSource value
    originating_calculation_version: str
    occurrence_period_start: datetime | None
    occurrence_period_end: datetime | None
    evidence: list[CandidateEvidenceDraft] = field(default_factory=list)


def _resolve_global_risk_area_concept(db: Session, scope_key: _ScopeKey):
    """The GLOBAL (`organization_id=None`), `APPROVED`,
    `is_risk_area_eligible` concept at this scope key, or `None` if it
    does not (yet, or no longer) exist as one -- never a fabricated
    fallback (item 25)."""
    layer, parent_domain, concept_key = scope_key
    concept = ogs.get_concept_by_scope(db, layer=layer, parent_domain=parent_domain, concept_key=concept_key)
    if concept is None or concept.organization_id is not None:
        return None
    if concept.status != "APPROVED" or not concept.is_risk_area_eligible:
        return None
    return concept


def _anomaly_candidate(db: Session, anomaly) -> CandidateFindingDraft | None:
    scope_key = _ANOMALY_METRIC_RISK_AREA_SCOPE.get(anomaly.metric)
    if scope_key is None:
        return None
    concept = _resolve_global_risk_area_concept(db, scope_key)
    if concept is None:
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
        risk_area_concept_id=concept.id,
        risk_area_ontology_version=concept.ontology_version,
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


def _pattern_candidate(db: Session, pattern) -> CandidateFindingDraft | None:
    scope_key = None
    if pattern.event_subtype is not None:
        scope_key = _PATTERN_SUBTYPE_RISK_AREA_SCOPE.get(pattern.event_subtype)
    if scope_key is None:
        scope_key = _PATTERN_EVENT_TYPE_RISK_AREA_SCOPE.get(pattern.event_type)
    if scope_key is None:
        return None
    concept = _resolve_global_risk_area_concept(db, scope_key)
    if concept is None:
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
        risk_area_concept_id=concept.id,
        risk_area_ontology_version=concept.ontology_version,
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
    already-point-in-time-correct event data, same governed ontology
    state) -- calling this twice for the same assessment produces the
    identical candidate set, the same reproducibility guarantee every
    Milestone 22-24 computation already provides."""
    result = compute_enterprise_intelligence(
        db, organization_id=organization_id, scope=scope, site_id=site_id, as_of=as_of, window_days=window_days
    )
    drafts: list[CandidateFindingDraft] = []
    for anomaly in result.anomalies:
        if anomaly.status != "ANOMALOUS":
            continue
        draft = _anomaly_candidate(db, anomaly)
        if draft is not None:
            drafts.append(draft)
    for pattern in result.patterns:
        if pattern.classification not in _NOTABLE_RECURRENCE_CLASSIFICATIONS:
            continue
        draft = _pattern_candidate(db, pattern)
        if draft is not None:
            drafts.append(draft)
    return drafts


__all__ = ["CandidateEvidenceDraft", "CandidateFindingDraft", "generate_candidate_findings"]
