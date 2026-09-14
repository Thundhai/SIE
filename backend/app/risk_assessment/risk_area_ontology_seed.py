"""Governed risk-area seed data — SIE Milestone 25A: Governed Risk-Area &
Organization-Extensible Risk Taxonomy v0.1.

Milestone 25 introduced 11 risk areas as a closed Python enum
(`RiskArea`, now removed — see `app/models/risk_assessment_enums.py`'s
own history). Milestone 25A replaces that closed enum with the existing,
governed `OntologyConcept` architecture (`app/models/ontology_concept.py`,
`app/services/ontology_governance_service.py`) as the one authoritative
risk-area taxonomy — SIE's *initial* risk areas are seeded concepts, not
the limits of what an organization may use (see this module's own
`RISK_AREA_SEED_CONCEPTS` below).

**Why a seed list at all, rather than relying solely on
`config/enterprise_ontology_concepts_v1.json`.** Nine of the eleven
original `RiskArea` values are already governed there
(`WORKING_AT_HEIGHT`, `PPE_COMPLIANCE`, `ELECTRICAL_SAFETY`,
`LIFTING_OPERATIONS`, `ENVIRONMENTAL`, `EQUIPMENT_SAFETY`,
`PROCEDURE_VIOLATION`, `FIRE_SAFETY`, `EMERGENCY_PREPAREDNESS`) — but
applying that artifact is a separate, explicit, auditable operation
(`app/services/ontology_concept_artifact_service.py`) that a fresh
database is not guaranteed to have run, and it never sets
`is_risk_area_eligible` (a Milestone 25A concept the artifact predates).
The remaining two (`INCIDENT_SAFETY`, `VEHICLE_SAFETY`) were never
governed `OntologyConcept` rows at all — Milestone 25's own
`risk_assessment_enums.py` docstring is explicit that they were
"grounded in the pre-existing, canonical `SafetyEventType`/`event_subtype`
vocabulary... one that predates the `OntologyConcept` table" (item 22 of
the Milestone 25A specification: "If any current value has no valid
corresponding governed concept, stop and report the mismatch rather than
silently inventing one" — this module is that explicit, documented
report, and the smallest governed extension needed: two new, additive
`OntologyConcept` rows for pre-existing canonical vocabulary that was
simply never represented as a governed concept before). Migration 0017
is the ONE place this list is applied, so `alembic upgrade head` alone
(never a separate manual artifact-application step) guarantees all 11
original risk areas remain usable on a completely fresh database — see
that migration's own docstring.

**Never a duplicate taxonomy.** This is not a second concept registry —
it is a plain, declarative list of `(layer, parent_domain, concept_key)`
scope keys the migration inserts (or updates in place) through the
unmodified `ontology_concepts` table, exactly as a human platform
administrator would via `ontology_governance_service.propose_concept()`/
`approve_concept()` — mirrors `ontology_concept_artifact_service.py`'s
own established pattern for the identical reason. `legacy_risk_area` is
documentation only (which now-removed `RiskArea` enum member this entry
replaces) — never read by any runtime code path.

**Ontology layer, per concept (item 5) — never assumed to be
`observation_topic`.** `INCIDENT_SAFETY` sits at the `event_type` layer
(the top-level `SafetyEventType.INCIDENT` itself); `VEHICLE_SAFETY` sits
at `event_subtype` (the existing `VEHICLE_INCIDENT` subtype, under
`parent_domain="INCIDENT"`); the remaining nine sit at `observation_topic`
or (`PROCEDURE_VIOLATION`) `event_subtype` — see each entry's own
`definition` for the specific rationale, identical to the rationale
`config/enterprise_ontology_concepts_v1.json` and Milestone 25's own
`risk_assessment_enums.py` already documented.

All eleven entries are GLOBAL (`organization_id=None`) — SIE's own
seeded, platform-wide risk areas. An organization's own extension of the
taxonomy (e.g. `DROPPED_OBJECTS`) is proposed/approved separately, through
the same unmodified governance service, with its own `organization_id` —
never added to this list (this list is SIE's fixed *initial* seed, not a
growing registry an organization would ever be expected to edit)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskAreaSeedConcept:
    legacy_risk_area: str  # documentation only -- the removed RiskArea enum member this replaces
    layer: str
    parent_domain: str | None
    concept_key: str
    definition: str
    justification: str


RISK_AREA_SEED_CONCEPTS: tuple[RiskAreaSeedConcept, ...] = (
    RiskAreaSeedConcept(
        legacy_risk_area="INCIDENT_SAFETY",
        layer="event_type",
        parent_domain=None,
        concept_key="INCIDENT",
        definition=(
            "The top-level SafetyEventType.INCIDENT vocabulary -- an event representing an actual "
            "safety incident (as opposed to a near miss, observation, or any other event type). "
            "Governed here as a Risk Assessment risk area so a Risk Assessment finding evidencing "
            "recurring/anomalous incident activity can reference a real, governed ontology concept "
            "rather than a closed enum member."
        ),
        justification=(
            "Backfills the pre-existing canonical SafetyEventType top-level INCIDENT vocabulary, which "
            "predates the OntologyConcept table entirely (Milestone 15) and so was never represented as "
            "a governed concept -- SIE Milestone 25A, item 22's own 'stop and report the mismatch' "
            "instruction, resolved as the smallest additive governed extension: one new global concept "
            "row for vocabulary that already existed and was already authoritative, never a redefinition."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="VEHICLE_SAFETY",
        layer="event_subtype",
        parent_domain="INCIDENT",
        concept_key="VEHICLE_INCIDENT",
        definition=(
            "An INCIDENT-domain event whose subtype is VEHICLE_INCIDENT -- already relied on throughout "
            "app/intelligence/enterprise_indicators.py since Milestone 22. Governed here as a Risk "
            "Assessment risk area for the identical reason as INCIDENT above."
        ),
        justification=(
            "Backfills the pre-existing canonical VEHICLE_INCIDENT event_subtype vocabulary, which also "
            "predates the OntologyConcept table -- same rationale as INCIDENT above."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="WORKING_AT_HEIGHT",
        layer="observation_topic",
        parent_domain="OBSERVATION",
        concept_key="WORKING_AT_HEIGHT",
        definition=(
            "The safety topic/activity category of an Observation record concerning work performed at "
            "height (falls, fall-protection equipment, edge protection, etc.) -- a subject-matter tag on "
            "an OBSERVATION, never itself a finding/condition type."
        ),
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json (SIE Enterprise Ontology & "
            "Data Model Expansion v0.1) -- flagged risk-area-eligible here rather than redefined; see "
            "that artifact's own 'Working At Height' entry for the full evidence and rationale."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="PPE_COMPLIANCE",
        layer="observation_topic",
        parent_domain="OBSERVATION",
        concept_key="PPE_COMPLIANCE",
        definition=(
            "The safety topic/activity category of an Observation record concerning personal protective "
            "equipment generally (both compliant and non-compliant instances) -- a subject-matter tag, "
            "distinct from the existing event_subtype value PPE_ISSUE (a specific negative finding)."
        ),
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json -- flagged risk-area-eligible "
            "here; see that artifact's own 'PPE Compliance' entry."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="ELECTRICAL_SAFETY",
        layer="observation_topic",
        parent_domain="OBSERVATION",
        concept_key="ELECTRICAL_SAFETY",
        definition="The safety topic/activity category of an Observation record concerning electrical hazards or electrical-work safety practices.",
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json -- flagged risk-area-eligible "
            "here; see that artifact's own 'Electrical Safety' entry."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="LIFTING_OPERATIONS",
        layer="observation_topic",
        parent_domain="OBSERVATION",
        concept_key="LIFTING_OPERATIONS",
        definition="The safety topic/activity category of an Observation record concerning crane, hoist, or other lifting-equipment operations.",
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json -- flagged risk-area-eligible "
            "here; see that artifact's own 'Lifting Operations' entry."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="ENVIRONMENTAL",
        layer="observation_topic",
        parent_domain="OBSERVATION",
        concept_key="ENVIRONMENTAL",
        definition=(
            "The safety topic/activity category of an Observation record concerning environmental hazards "
            "or environmental-management practices -- namespaced from, and never confused with, the "
            "top-level ENVIRONMENTAL SafetyEventType or the INCIDENT subtype ENVIRONMENTAL_EVENT."
        ),
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json -- flagged risk-area-eligible "
            "here; see that artifact's own 'Environmental' entry."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="EQUIPMENT_SAFETY",
        layer="observation_topic",
        parent_domain="OBSERVATION",
        concept_key="EQUIPMENT_SAFETY",
        definition=(
            "The safety topic/activity category of an Observation record concerning equipment-related "
            "hazards or equipment-safety practices (distinct from the top-level EQUIPMENT event_type, "
            "which classifies equipment maintenance/status events)."
        ),
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json -- flagged risk-area-eligible "
            "here; see that artifact's own 'Equipment Safety' entry."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="PROCEDURE_VIOLATION",
        layer="event_subtype",
        parent_domain="OBSERVATION",
        concept_key="PROCEDURE_VIOLATION",
        definition=(
            "An Observation-domain finding/condition type: a documented instance of non-compliance with a "
            "defined operating procedure or work instruction -- a finding-type concept (like the existing "
            "UNSAFE_ACT/UNSAFE_CONDITION), never a topic/category."
        ),
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json -- flagged risk-area-eligible "
            "here; see that artifact's own 'Procedure Violation' entry."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="FIRE_SAFETY",
        layer="observation_topic",
        parent_domain="OBSERVATION",
        concept_key="FIRE_SAFETY",
        definition=(
            "The safety topic/activity category of an Observation record concerning fire-safety practices, "
            "fire-prevention measures, or fire-protection equipment (distinct from the event_subtype "
            "concept FIRE, which classifies an actual fire INCIDENT that occurred, not an observation's topic)."
        ),
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json -- flagged risk-area-eligible "
            "here; see that artifact's own 'Fire Safety' entry."
        ),
    ),
    RiskAreaSeedConcept(
        legacy_risk_area="EMERGENCY_PREPAREDNESS",
        layer="observation_topic",
        parent_domain="OBSERVATION",
        concept_key="EMERGENCY_PREPAREDNESS",
        definition="The safety topic/activity category of an Observation record concerning emergency-response planning, drills, or preparedness measures.",
        justification=(
            "Already governed by config/enterprise_ontology_concepts_v1.json -- flagged risk-area-eligible "
            "here; see that artifact's own 'Emergency Preparedness' entry."
        ),
    ),
)

#: `ontology_version` recorded for every seeded concept -- matches
#: `config/enterprise_ontology_concepts_v1.json`'s own top-level
#: `ontology_version: 1` for the nine entries it already governs, and is
#: the natural starting version for the two newly backfilled ones.
RISK_AREA_SEED_ONTOLOGY_VERSION = 1

__all__ = ["RISK_AREA_SEED_CONCEPTS", "RISK_AREA_SEED_ONTOLOGY_VERSION", "RiskAreaSeedConcept"]
