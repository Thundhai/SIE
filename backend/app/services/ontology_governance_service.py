"""Ontology governance — SIE Enterprise Ontology & Data Model Expansion
v0.1: the one read/write path for `OntologyConcept` rows (see that
model's own docstring for the full lifecycle, scoping, and versioning
rationale).

    PROPOSED CANONICAL CONCEPT   (propose_concept() -- explicit, human
       |                          input; never auto-generated from a
       |                          source term, never LLM-generated)
       |
    ONTOLOGY GOVERNANCE          (approve_concept() / reject_concept())
       |
    APPROVED CANONICAL CONCEPT   -> DEPRECATED (deprecate_concept(),
                                     a later, separate, explicit step)

**Authorization: platform-admin-only, not merely `GOVERNANCE_MANAGE`.**
Every mutating function below calls `authorization_service.require(...,
Permission.GOVERNANCE_MANAGE, organization_id=None)`. Passing
`organization_id=None` is the deliberate mechanism here, not an
oversight: `AuthorizationService.can()` grants a non-platform-admin
caller nothing at all once `organization_id` is `None` (there is no
membership to check permissions against), and grants a genuine
`PLATFORM_ADMIN` every permission regardless of the `organization_id`
argument. The net effect -- reusing 100% existing authorization code,
zero new permission, zero backdoor -- is that **only a human
`PLATFORM_ADMIN` may govern the ontology**, exactly the same rule
`app/api/v1/knowledge.py` already enforces for writing GLOBAL knowledge
("only a human PLATFORM_ADMIN may write GLOBAL knowledge... a machine
client can never write GLOBAL knowledge at all" -- see that router's own
docstring). An org's own `GOVERNANCE_MANAGE` holder (an `ORG_ADMIN`)
cannot govern the ontology through this service, by design: the
ontology is platform-wide, so no single organization's administrator
should be able to change what every other tenant's data can be
classified as.

**Never a backdoor around `terminology_calibration_service.py`.** This
module creates and decides `OntologyConcept` rows only -- it never
creates, proposes, approves, or rejects a `TerminologyMappingDecision`,
never calls `reprocess_quarantined_records()`, and never touches a
`SafetyEvent`. Approving a concept here makes it *exist* in the
ontology and become a legitimate future target for a *separate*,
still-fully-governed terminology-mapping decision -- it does not, by
itself, resolve or reclassify a single real-dataset term (see
`is_valid_concept()`'s own docstring for exactly how a future
terminology-mapping validation would consult this).

**Naming discipline.** `concept_key` must match `^[A-Z][A-Z0-9_]*$` --
the same deterministic, all-caps-with-underscores convention every
existing canonical value in `app/intelligence/enums.py` and
`app/intelligence/terminology_mapping.py` already uses. This is
mechanically enforced; "not customer-specific, not source-system-
specific, one defined semantic meaning" is enforced by the
platform-admin review this whole module gates, not by a regex --
exactly like a `TerminologyMappingDecision.rationale` string's own
quality is never algorithmically checked, only gated by authorization.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.enums import SafetyEventType
from app.models.ontology_concept import (
    ELIGIBLE_STATUSES,
    LAYERS,
    OntologyConcept,
    OntologyConceptStatus,
)
from app.services.audit_service import AuditAction, audit_service
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

_GOVERNANCE_PERMISSION = Permission.GOVERNANCE_MANAGE

#: `^[A-Z][A-Z0-9_]*$` -- deterministic, stable, unambiguous; matches
#: every existing canonical value's own naming convention (e.g.
#: `NEAR_MISS`, `PROPERTY_DAMAGE`, `PPE_ISSUE`).
_CONCEPT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class OntologyConceptNotFoundError(ValueError):
    """Raised when `concept_id` does not exist."""


class OntologyConceptStateError(ValueError):
    """Raised when an operation is attempted against a row in the wrong
    lifecycle state -- e.g. approving an already-`APPROVED` concept, or
    deprecating one that was never `APPROVED` in the first place."""


class OntologyConceptConflictError(ValueError):
    """Raised when a proposed `(layer, parent_domain, concept_key)`
    scope key already has a row -- whatever its status. Never silently
    reuses, overwrites, or reinterprets an existing concept; a genuinely
    different definition needs a genuinely different `concept_key`."""


class InvalidOntologyConceptError(ValueError):
    """Raised for a structurally invalid concept: a malformed
    `concept_key`, an unrecognized `layer`, or a `parent_domain` that
    does not belong to the existing SIE ontology."""


def _validate_concept_key(concept_key: str) -> None:
    if not _CONCEPT_KEY_PATTERN.match(concept_key):
        raise InvalidOntologyConceptError(
            f"{concept_key!r} is not a valid concept_key -- must match {_CONCEPT_KEY_PATTERN.pattern} "
            "(all-caps, starting with a letter, digits/underscores only -- the same convention every "
            "existing SIE canonical value already uses)."
        )


def _validate_layer_and_parent_domain(layer: str, parent_domain: str | None, concept_key: str) -> None:
    """Enforces exactly the ontology boundary rule this milestone exists
    to guarantee: a subtype/topic concept must belong to a defined
    parent `event_type`, and cross-domain combinations (`INCIDENT` +
    `OBSERVATION`, `INCIDENT` + `PERMIT`, ...) can never even be
    *proposed*, let alone approved -- `parent_domain`, when required,
    must itself be one of the existing, real `SafetyEventType` values,
    nothing invented.

    For `layer='event_subtype'` specifically, `concept_key` must also
    never be a *different* top-level `SafetyEventType` name -- the exact
    corrective-commit blocker-2 bug, reintroduced one layer up, that
    this check exists to rule out here (see
    `terminology_calibration_service._valid_compound_subtype_for()`'s
    own docstring for the identical guarantee at the mapping layer; the
    two mechanisms are deliberately independent and neither widens the
    other). This restriction does NOT apply to `layer='observation_topic'`:
    that is a genuinely separate namespace/dimension from `event_subtype`
    (never read by the same code, never written to
    `SafetyEvent.event_subtype`), so an observation_topic concept_key
    like `ENVIRONMENTAL` reusing an existing top-level type's name is
    deliberate and safe -- `(layer, parent_domain, concept_key)` together
    is the real scope key, not `concept_key` alone (see
    `docs/SIE_ENTERPRISE_ONTOLOGY_V0_1.md`'s own "Observation semantic
    model" section for the worked example)."""
    if layer not in LAYERS:
        raise InvalidOntologyConceptError(f"{layer!r} is not a recognized ontology layer (expected one of {LAYERS}).")

    valid_event_types = frozenset(t.value for t in SafetyEventType)

    if layer == "event_type":
        if parent_domain is not None:
            raise InvalidOntologyConceptError(
                "layer='event_type' concepts are top-level and must not declare a parent_domain."
            )
        return

    # event_subtype / observation_topic: always scoped under a real,
    # existing top-level event_type -- never None, never invented.
    if parent_domain is None or parent_domain not in valid_event_types:
        raise InvalidOntologyConceptError(
            f"layer={layer!r} concepts must declare parent_domain as one of the existing SafetyEventType "
            f"values {sorted(valid_event_types)}; got {parent_domain!r}. Cross-domain combinations "
            "(e.g. INCIDENT+OBSERVATION) are never valid regardless of layer."
        )
    if layer == "event_subtype" and concept_key in valid_event_types:
        raise InvalidOntologyConceptError(
            f"concept_key={concept_key!r} is itself an existing top-level SafetyEventType value -- an "
            f"event_subtype concept under parent_domain={parent_domain!r} can never reuse a different "
            "top-level type's own name (e.g. INCIDENT+OBSERVATION is never valid merely because "
            "OBSERVATION exists elsewhere in the ontology)."
        )


def _require_concept(db: Session, *, concept_id: uuid.UUID) -> OntologyConcept:
    concept = db.get(OntologyConcept, concept_id)
    if concept is None:
        raise OntologyConceptNotFoundError(f"No ontology concept {concept_id}.")
    return concept


def _require_platform_admin(db: Session, *, acting_user_id: uuid.UUID) -> None:
    """Platform-wide governance -- see this module's own docstring for
    exactly why `organization_id=None` is the mechanism, not a bug."""
    authorization_service.require(db, user_id=acting_user_id, permission=_GOVERNANCE_PERMISSION, organization_id=None)


def propose_concept(
    db: Session,
    *,
    layer: str,
    parent_domain: str | None,
    concept_key: str,
    definition: str,
    justification: str,
    acting_user_id: uuid.UUID,
) -> OntologyConcept:
    """Creates a new `PROPOSED` concept. Requires platform-admin
    (`GOVERNANCE_MANAGE`, `organization_id=None`) -- proposing is
    already a deliberate administrative act here, never automatic and
    never reachable from an ordinary ingestion request (contrast
    `TerminologyMappingDecision`'s own `REVIEW_CANDIDATE`, which *is*
    surfaced automatically by ingestion-time terminology review; an
    ontology *concept* has no such automatic surfacing path at all --
    see this module's own docstring)."""
    _require_platform_admin(db, acting_user_id=acting_user_id)
    _validate_concept_key(concept_key)
    _validate_layer_and_parent_domain(layer, parent_domain, concept_key)

    existing = db.execute(
        select(OntologyConcept).where(
            OntologyConcept.layer == layer,
            OntologyConcept.parent_domain == parent_domain,
            OntologyConcept.concept_key == concept_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise OntologyConceptConflictError(
            f"A concept already exists at layer={layer!r} parent_domain={parent_domain!r} "
            f"concept_key={concept_key!r} (id={existing.id}, status={existing.status}). "
            "Never silently reused or reinterpreted -- a genuinely different definition needs a new concept_key."
        )

    concept = OntologyConcept(
        layer=layer, parent_domain=parent_domain, concept_key=concept_key,
        definition=definition, justification=justification,
        status=OntologyConceptStatus.PROPOSED,
        proposed_by_user_id=acting_user_id, proposed_at=datetime.now(timezone.utc),
    )
    db.add(concept)
    db.commit()
    db.refresh(concept)

    audit_service.log(
        db, action=AuditAction.ONTOLOGY_CONCEPT_PROPOSED, resource_type="OntologyConcept",
        resource_id=concept.id, organization_id=None, user_id=acting_user_id,
        metadata={"layer": layer, "parent_domain": parent_domain, "concept_key": concept_key},
    )
    return concept


def approve_concept(
    db: Session, *, concept_id: uuid.UUID, acting_user_id: uuid.UUID, ontology_version: int, notes: str | None = None,
) -> OntologyConcept:
    """The one operation that makes a concept eligible for a future
    terminology-mapping decision to target (see `is_valid_concept()`).
    Requires platform-admin. `ontology_version` must be explicit and
    caller-supplied (never silently incremented) -- see
    `docs/SIE_ENTERPRISE_ONTOLOGY_V0_1.md`'s own "Versioning" section."""
    _require_platform_admin(db, acting_user_id=acting_user_id)

    concept = _require_concept(db, concept_id=concept_id)
    if concept.status != OntologyConceptStatus.PROPOSED:
        raise OntologyConceptStateError(
            f"Concept {concept_id} is {concept.status}, not PROPOSED -- only a proposed concept can be approved."
        )

    concept.status = OntologyConceptStatus.APPROVED
    concept.ontology_version = ontology_version
    concept.reviewer_user_id = acting_user_id
    concept.decided_at = datetime.now(timezone.utc)
    if notes:
        concept.justification = f"{concept.justification}\n[APPROVED] {notes}".strip()
    db.commit()
    db.refresh(concept)

    audit_service.log(
        db, action=AuditAction.ONTOLOGY_CONCEPT_APPROVED, resource_type="OntologyConcept",
        resource_id=concept.id, organization_id=None, user_id=acting_user_id,
        metadata={
            "layer": concept.layer, "parent_domain": concept.parent_domain, "concept_key": concept.concept_key,
            "ontology_version": ontology_version,
        },
    )
    return concept


def reject_concept(db: Session, *, concept_id: uuid.UUID, acting_user_id: uuid.UUID, reason: str) -> OntologyConcept:
    """Rejects a `PROPOSED` concept -- it remains permanently
    not-part-of-the-ontology (never deleted, never silently reused for a
    different concept later). Requires platform-admin."""
    _require_platform_admin(db, acting_user_id=acting_user_id)

    concept = _require_concept(db, concept_id=concept_id)
    if concept.status != OntologyConceptStatus.PROPOSED:
        raise OntologyConceptStateError(
            f"Concept {concept_id} is {concept.status}, not PROPOSED -- only a proposed concept can be rejected."
        )

    concept.status = OntologyConceptStatus.REJECTED
    concept.reviewer_user_id = acting_user_id
    concept.decided_at = datetime.now(timezone.utc)
    concept.justification = f"{concept.justification}\n[REJECTED] {reason}".strip()
    db.commit()
    db.refresh(concept)

    audit_service.log(
        db, action=AuditAction.ONTOLOGY_CONCEPT_REJECTED, resource_type="OntologyConcept",
        resource_id=concept.id, organization_id=None, user_id=acting_user_id,
        metadata={"layer": concept.layer, "parent_domain": concept.parent_domain, "concept_key": concept.concept_key, "reason": reason},
    )
    return concept


def deprecate_concept(db: Session, *, concept_id: uuid.UUID, acting_user_id: uuid.UUID, reason: str) -> OntologyConcept:
    """Marks a previously-`APPROVED` concept `DEPRECATED` -- a one-way
    lifecycle step (never un-deprecated; a reconsidered concept gets a
    new `concept_key`, exactly like `TerminologyMappingDecision`'s own
    versioning discipline). A `DEPRECATED` concept is no longer eligible
    for a *new* terminology-mapping decision to target
    (`is_valid_concept()` excludes it) but nothing here retroactively
    touches any decision or event that already used it. Requires
    platform-admin."""
    _require_platform_admin(db, acting_user_id=acting_user_id)

    concept = _require_concept(db, concept_id=concept_id)
    if concept.status != OntologyConceptStatus.APPROVED:
        raise OntologyConceptStateError(
            f"Concept {concept_id} is {concept.status}, not APPROVED -- only an approved concept can be deprecated."
        )

    concept.status = OntologyConceptStatus.DEPRECATED
    concept.justification = f"{concept.justification}\n[DEPRECATED] {reason}".strip()
    db.commit()
    db.refresh(concept)

    audit_service.log(
        db, action=AuditAction.ONTOLOGY_CONCEPT_DEPRECATED, resource_type="OntologyConcept",
        resource_id=concept.id, organization_id=None, user_id=acting_user_id,
        metadata={"layer": concept.layer, "parent_domain": concept.parent_domain, "concept_key": concept.concept_key, "reason": reason},
    )
    return concept


def get_concept_by_scope(db: Session, *, layer: str, parent_domain: str | None, concept_key: str) -> OntologyConcept | None:
    """Returns the concept at `(layer, parent_domain, concept_key)`,
    whatever its status -- unlike `is_valid_concept()`, which only
    answers whether an `APPROVED` concept exists there. Used by
    `ontology_concept_artifact_service.py` to distinguish "same scope
    key, same semantic meaning" (an existing `APPROVED` concept whose
    definition/version genuinely matches the durable artifact) from
    "same scope key, conflicting meaning" (an existing row of ANY status
    whose content does not) -- a same scope key alone is never
    sufficient to treat a re-application of the artifact as a no-op."""
    return db.execute(
        select(OntologyConcept).where(
            OntologyConcept.layer == layer,
            OntologyConcept.parent_domain == parent_domain,
            OntologyConcept.concept_key == concept_key,
        )
    ).scalar_one_or_none()


def is_valid_concept(db: Session, *, layer: str, parent_domain: str | None, concept_key: str) -> bool:
    """Whether `(layer, parent_domain, concept_key)` is currently an
    `APPROVED` ontology concept -- the one boolean a *future*
    terminology-mapping validation (extending
    `terminology_calibration_service._canonical_terms_for()`/
    `_valid_compound_subtype_for()`) would need to check before letting
    a human reviewer target this concept with a real
    `TerminologyMappingDecision`. Deliberately not wired into that
    validation by this milestone -- see
    `docs/SIE_ENTERPRISE_ONTOLOGY_V0_1.md`'s own "Terminology mapping
    relationship" section: remapping specific rejected enterprise terms
    against these newly-approved concepts is explicitly the *next*
    milestone's decision, not automatic here."""
    concept = db.execute(
        select(OntologyConcept).where(
            OntologyConcept.layer == layer,
            OntologyConcept.parent_domain == parent_domain,
            OntologyConcept.concept_key == concept_key,
        )
    ).scalar_one_or_none()
    return concept is not None and concept.status in ELIGIBLE_STATUSES


def list_concepts(
    db: Session, *, layer: str | None = None, parent_domain: str | None = None, status: str | None = None,
) -> list[OntologyConcept]:
    query = select(OntologyConcept)
    if layer is not None:
        query = query.where(OntologyConcept.layer == layer)
    if parent_domain is not None:
        query = query.where(OntologyConcept.parent_domain == parent_domain)
    if status is not None:
        query = query.where(OntologyConcept.status == status)
    query = query.order_by(OntologyConcept.created_at)
    return list(db.execute(query).scalars().all())


__all__ = [
    "InvalidOntologyConceptError",
    "OntologyConceptConflictError",
    "OntologyConceptNotFoundError",
    "OntologyConceptStateError",
    "approve_concept",
    "deprecate_concept",
    "get_concept_by_scope",
    "is_valid_concept",
    "list_concepts",
    "propose_concept",
    "reject_concept",
]
