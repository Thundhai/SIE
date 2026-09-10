"""Risk-area concept resolution — SIE Milestone 25A: Governed Risk-Area &
Organization-Extensible Risk Taxonomy v0.1.

    RiskAssessmentFinding.risk_area_concept_id
              |
    resolve_risk_area_concept()      (THIS module -- the one place an
              |                       API-supplied concept id is validated)
    OntologyConcept                  (app.services.ontology_governance_service,
                                       unmodified lifecycle/authorization)

`app/api/v1/risk_assessments.py::create_finding()` is the only route that
accepts a client-supplied `risk_area_concept_id` — this is the one
function it (and nothing else) calls to turn that id into a real,
governed, usable concept, or a clear `HTTPException`. System-generated
candidate findings never call this: `app/risk_assessment/
candidate_generation.py` resolves its own, GLOBAL-only, statically-mapped
concepts directly against `ontology_governance_service.get_concept_by_scope()`
at generation time (see that module's own docstring) — a human accepting
a candidate and supplying a rating (`PATCH .../findings/{finding_id}`)
never re-resolves `risk_area_concept_id`; it is immutable after creation
(see `app/schemas/risk_assessment.py::RiskAssessmentFindingUpdate`'s own
docstring for why no risk-area field exists there at all).

**Tenant isolation (item 10).** A concept belonging to a *different*
organization is indistinguishable, from the caller's own perspective,
from a concept that does not exist at all — always `HTTP 404`, mirroring
`app/api/v1/actions.py`'s own "Tenant isolation" precedent and
`app/services/risk_assessment_service.py::validate_site_reference()`'s
identical shape exactly. A GLOBAL concept (`organization_id IS NULL`) is
always accessible, per the existing global-knowledge/ontology access
rules this milestone reuses rather than reinvents (item 10).

**Governance state (item 9).** Only `APPROVED` *and* `is_risk_area_eligible`
concepts may ever be referenced by a new finding — enforced here, at the
service/API boundary, never merely assumed at the frontend (there is no
frontend change in this milestone at all). A `PROPOSED`, `REJECTED`, or
`DEPRECATED` concept, or an `APPROVED` concept that was never flagged
risk-area-eligible, is rejected with `HTTP 422` and an actionable message
naming exactly why.

**Historical integrity (item 7).** This function is called only at
finding *creation* — never again on read. Once a finding stores
`risk_area_concept_id` (an immutable FK, never repointed) and
`risk_area_ontology_version` (a snapshot of `OntologyConcept.ontology_version`
at the moment of assignment), the finding's own answer to "which governed
concept, at what version, did this refer to at the time" never depends on
this function, or on the concept's current, possibly since-changed
`status`, ever being called again. See
`app/models/risk_assessment.py`'s own docstring for the full rationale."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.ontology_concept import OntologyConcept, OntologyConceptStatus


def resolve_risk_area_concept(
    db: Session, *, organization_id: uuid.UUID, concept_id: uuid.UUID
) -> OntologyConcept:
    """Resolves and validates a client-supplied `risk_area_concept_id`
    (item 19: "The service must resolve and validate the concept" —
    never accept an arbitrary string and assume it is valid). Raises
    `HTTPException(404)` if the concept does not exist or belongs to a
    different organization (never distinguished from each other in the
    response — see module docstring), or `HTTPException(422)` if it
    exists and is tenant-accessible but is not currently usable as a risk
    area (not `APPROVED`, or not `is_risk_area_eligible`)."""
    concept = db.get(OntologyConcept, concept_id)
    if concept is None or (concept.organization_id is not None and concept.organization_id != organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk area concept not found or not accessible in this organization.",
        )
    if concept.status != OntologyConceptStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Concept {concept.concept_key!r} is {concept.status}, not APPROVED -- only an APPROVED "
                "ontology concept may be used as a Risk Assessment risk area."
            ),
        )
    if not concept.is_risk_area_eligible:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Concept {concept.concept_key!r} is APPROVED but is not flagged is_risk_area_eligible -- "
                "not every governed concept is a Risk Assessment risk area."
            ),
        )
    return concept


__all__ = ["resolve_risk_area_concept"]
