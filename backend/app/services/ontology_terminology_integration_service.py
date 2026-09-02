"""Governed ontology-to-terminology integration — SIE Milestone 16
("Governed Ontology-to-Terminology Integration & Controlled Remapping
Foundation v0.1"): the one deterministic contract that answers

    "Is this proposed canonical mapping target valid against the
     currently APPROVED SIE ontology?"

    SOURCE SYSTEM TERMINOLOGY
           |
    TERMINOLOGY MAPPING          (TerminologyMappingDecision -- unchanged,
           |                      app/services/terminology_calibration_service.py)
    GOVERNED SIE ONTOLOGY        (OntologyConcept -- Milestone 15, unchanged,
           |                      app/services/ontology_governance_service.py)
    ENTERPRISE SAFETY DATA

Milestone 15 built the governed `OntologyConcept` registry but
deliberately left it unwired: `ontology_governance_service.is_valid_concept()`
answers only a bare boolean ("does an APPROVED concept exist at this
exact scope?"), which is too coarse for a governance-relevant validation
message — a reviewer refused a target needs to know *why* (does the
concept not exist at all? does it exist but isn't approved yet? does it
exist, but at a different layer or parent domain than they specified?).
This module answers that richer question, and nothing else:

  * it never mutates an `OntologyConcept` or a `TerminologyMappingDecision`;
  * it never creates a terminology decision, proposes one, approves one,
    or rejects one -- `terminology_calibration_service.py` still owns
    that whole lifecycle exclusively (this module's own
    `validate_canonical_target()` is *called by* that service's
    `approve_mapping()`, never the reverse);
  * it never touches a `SafetyEvent`;
  * it never loads the real enterprise workbook, calls
    `reprocess_quarantined_records()`, or remaps any of the 15 real
    terms that remain `REJECTED` in
    `backend/config/real_enterprise_terminology_decisions_v1.json` --
    this module makes remapping *possible in principle* for a term a
    human later, separately, proposes; it performs none itself;
  * it never uses an LLM, fuzzy/similarity matching, embeddings, or any
    form of semantic inference -- every answer is an exact-match lookup
    against governed `OntologyConcept` rows, deterministic and
    reproducible, exactly like `terminology_mapping.py`'s own alias
    table is never "probably this one."

**The contract.** `validate_canonical_target(db, layer=..., parent_domain=...,
concept_key=...)` returns an `OntologyValidationResult` whose `outcome`
is exactly one of:

    VALID                 An APPROVED OntologyConcept exists at this
                           EXACT (layer, parent_domain, concept_key)
                           scope. The only outcome a caller should ever
                           treat as "safe to use as a mapping target."
    NOT_APPROVED           A concept exists at this exact scope, but its
                           status is PROPOSED, REJECTED, or DEPRECATED --
                           governance has not (or no longer) approved
                           it. `result.concept` carries the row so a
                           caller can report its actual status.
    NOT_FOUND              No concept exists anywhere with this
                           `concept_key`, under any layer or parent
                           domain. This is the ordinary, expected
                           outcome for a concept_key that predates the
                           governed ontology (Milestone 15) entirely --
                           e.g. `NEAR_MISS`, `UNSAFE_ACT` -- and is NOT
                           itself proof the term is invalid; a caller
                           validating a *terminology decision* falls back
                           to the pre-existing static canonical
                           vocabulary for exactly this outcome (see
                           `terminology_calibration_service.approve_mapping()`).
    WRONG_LAYER            A concept with this `concept_key` exists, but
                           under a different `layer` than requested (no
                           concept shares the requested `layer` for this
                           key). `result.concept` carries one such row
                           for diagnostic purposes. The canonical
                           example this milestone documents: requesting
                           `layer='event_subtype', parent_domain='OBSERVATION',
                           concept_key='PPE_COMPLIANCE'` is WRONG_LAYER --
                           `PPE_COMPLIANCE` is governed under
                           `layer='observation_topic'`, not
                           `event_subtype`.
    WRONG_PARENT_DOMAIN    A concept with this `concept_key` exists under
                           the requested `layer`, but under a different
                           `parent_domain`. `result.concept` carries one
                           such row. Example: `FIRE` is governed under
                           `event_subtype`/`INCIDENT`; requesting
                           `event_subtype`/`OBSERVATION`/`FIRE` is
                           WRONG_PARENT_DOMAIN.
    INVALID                The request itself is structurally malformed
                           (an unrecognized `layer`, or an empty
                           `concept_key`) -- distinct from every outcome
                           above, all of which presuppose a
                           well-formed request.

Only `VALID` means "safe to use." Every other outcome means "do not
approve this as a canonical mapping target" -- the distinction between
them exists purely to produce an actionable, honest message for a human
reviewer, never to change that refusal.

**Namespace discipline (critical).** `(layer, parent_domain,
concept_key)` together is the real scope key -- never `concept_key`
alone. `find_concepts_by_key()` (used to distinguish `WRONG_LAYER`/
`WRONG_PARENT_DOMAIN` from a genuine `NOT_FOUND`) is diagnostic only:
this module's own caller,
`terminology_calibration_service.approve_mapping()`, treats the ontology
as authoritative for a proposed canonical term ONLY when an EXACT
`(layer, parent_domain, concept_key)` match exists (`VALID` or
`NOT_APPROVED`) -- never merely because *some* row somewhere shares the
same `concept_key`. This is deliberate: the top-level `SafetyEventType`
value `ENVIRONMENTAL` and the governed `observation_topic`/`OBSERVATION`
concept `ENVIRONMENTAL` are two completely different things sharing one
name (see `app/models/ontology_concept.py`'s own docstring and
`docs/SIE_ENTERPRISE_ONTOLOGY_V0_1.md`'s "Observation semantic model"
section) -- an `event_type`-domain terminology decision proposing
`ENVIRONMENTAL` must keep resolving against the pre-existing static
`SafetyEventType` vocabulary exactly as it always has, never against the
unrelated `observation_topic` concept that happens to share the string.
If `WRONG_LAYER`/`WRONG_PARENT_DOMAIN` cross-scope lookups were treated
as authoritative here, that pre-existing, perfectly valid term would be
silently, incorrectly refused -- exactly the backward-compatibility
break this milestone exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.ontology_concept import LAYERS, OntologyConcept, OntologyConceptStatus
from app.services import ontology_governance_service as ogs


class OntologyValidationOutcome:
    """See this module's own docstring for the full meaning of each
    outcome. Deliberately a plain class of string constants -- the same
    convention `OntologyConceptStatus`/`OntologyConceptLayer` already
    use, not a second, differently-shaped enum type."""

    VALID = "VALID"
    NOT_APPROVED = "NOT_APPROVED"
    NOT_FOUND = "NOT_FOUND"
    WRONG_LAYER = "WRONG_LAYER"
    WRONG_PARENT_DOMAIN = "WRONG_PARENT_DOMAIN"
    INVALID = "INVALID"


OUTCOMES = (
    OntologyValidationOutcome.VALID,
    OntologyValidationOutcome.NOT_APPROVED,
    OntologyValidationOutcome.NOT_FOUND,
    OntologyValidationOutcome.WRONG_LAYER,
    OntologyValidationOutcome.WRONG_PARENT_DOMAIN,
    OntologyValidationOutcome.INVALID,
)

#: Outcomes that presuppose an EXACT `(layer, parent_domain,
#: concept_key)` match was found -- i.e. `result.concept` is that exact
#: row, not merely a same-`concept_key` row found elsewhere. A caller
#: deciding whether the ontology is authoritative for a given scope
#: (rather than merely informative) should treat exactly these two
#: outcomes, and no others, as "governed at this scope" -- see
#: `terminology_calibration_service.approve_mapping()`'s own usage.
EXACT_SCOPE_OUTCOMES = (OntologyValidationOutcome.VALID, OntologyValidationOutcome.NOT_APPROVED)


@dataclass(frozen=True)
class OntologyValidationResult:
    outcome: str
    layer: str
    parent_domain: str | None
    concept_key: str
    #: The relevant `OntologyConcept` row, when one is relevant to the
    #: outcome: the exact match for `VALID`/`NOT_APPROVED`, or one
    #: same-`concept_key` row (for diagnostic purposes only -- never
    #: itself a valid target) for `WRONG_LAYER`/`WRONG_PARENT_DOMAIN`.
    #: `None` for `NOT_FOUND`/`INVALID`.
    concept: OntologyConcept | None = None
    #: A short, human-readable explanation -- never a full row dump,
    #: never PII.
    detail: str = ""

    @property
    def is_valid(self) -> bool:
        return self.outcome == OntologyValidationOutcome.VALID

    @property
    def is_exact_scope_match(self) -> bool:
        """Whether `concept` (if any) sits at the EXACT scope requested
        -- true for `VALID`/`NOT_APPROVED`, false for
        `WRONG_LAYER`/`WRONG_PARENT_DOMAIN`/`NOT_FOUND`/`INVALID`. See
        `EXACT_SCOPE_OUTCOMES`."""
        return self.outcome in EXACT_SCOPE_OUTCOMES


def validate_canonical_target(
    db: Session, *, layer: str, parent_domain: str | None, concept_key: str,
) -> OntologyValidationResult:
    """The one deterministic answer to "is this proposed canonical
    mapping target valid against the currently APPROVED SIE ontology?"
    -- see this module's own docstring for the full outcome contract.
    Read-only: never creates, mutates, approves, or rejects anything."""
    if layer not in LAYERS:
        return OntologyValidationResult(
            outcome=OntologyValidationOutcome.INVALID, layer=layer, parent_domain=parent_domain,
            concept_key=concept_key, detail=f"{layer!r} is not a recognized ontology layer (expected one of {LAYERS}).",
        )
    if not concept_key:
        return OntologyValidationResult(
            outcome=OntologyValidationOutcome.INVALID, layer=layer, parent_domain=parent_domain,
            concept_key=concept_key, detail="concept_key must be a non-empty string.",
        )

    exact = ogs.get_concept_by_scope(db, layer=layer, parent_domain=parent_domain, concept_key=concept_key)
    if exact is not None:
        if exact.status == OntologyConceptStatus.APPROVED:
            return OntologyValidationResult(
                outcome=OntologyValidationOutcome.VALID, layer=layer, parent_domain=parent_domain,
                concept_key=concept_key, concept=exact, detail="Governed and APPROVED.",
            )
        return OntologyValidationResult(
            outcome=OntologyValidationOutcome.NOT_APPROVED, layer=layer, parent_domain=parent_domain,
            concept_key=concept_key, concept=exact,
            detail=f"A concept exists at this exact scope, but its status is {exact.status}, not APPROVED.",
        )

    # No exact scope match -- look for the same concept_key ANYWHERE
    # else, purely to produce an informative diagnostic (never to widen
    # what counts as "governed at this scope" -- see this module's own
    # "Namespace discipline" docstring section).
    candidates = ogs.find_concepts_by_key(db, concept_key=concept_key)
    if not candidates:
        return OntologyValidationResult(
            outcome=OntologyValidationOutcome.NOT_FOUND, layer=layer, parent_domain=parent_domain,
            concept_key=concept_key, detail="No ontology concept exists with this concept_key, under any layer or parent domain.",
        )

    same_layer = [c for c in candidates if c.layer == layer]
    if same_layer:
        other = same_layer[0]
        return OntologyValidationResult(
            outcome=OntologyValidationOutcome.WRONG_PARENT_DOMAIN, layer=layer, parent_domain=parent_domain,
            concept_key=concept_key, concept=other,
            detail=f"{concept_key!r} is governed under layer={layer!r}, but parent_domain={other.parent_domain!r}, not {parent_domain!r}.",
        )

    other = candidates[0]
    return OntologyValidationResult(
        outcome=OntologyValidationOutcome.WRONG_LAYER, layer=layer, parent_domain=parent_domain,
        concept_key=concept_key, concept=other,
        detail=f"{concept_key!r} is governed under layer={other.layer!r} (parent_domain={other.parent_domain!r}), not layer={layer!r}.",
    )


__all__ = [
    "EXACT_SCOPE_OUTCOMES",
    "OUTCOMES",
    "OntologyValidationOutcome",
    "OntologyValidationResult",
    "validate_canonical_target",
]
