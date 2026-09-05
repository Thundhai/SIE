"""OntologyConcept — SIE Enterprise Ontology & Data Model Expansion v0.1:
a persisted, versioned, auditable record of *what canonical concepts
legitimately belong to SIE's own ontology*, distinct from, and upstream
of, `TerminologyMappingDecision` (which decides how a real *source
system's own term* maps onto an *already-existing* canonical concept).

    SOURCE TERMINOLOGY
           |
    TERMINOLOGY MAPPING        (TerminologyMappingDecision -- unchanged,
           |                    this milestone touches none of it)
    CANONICAL SIE ONTOLOGY     (OntologyConcept -- THIS model, new)
           |
    ENTERPRISE SAFETY DATA     (SafetyEvent -- unchanged; no row is
           |                    classified against a new concept here,
           |                    that is explicitly the next milestone's job)
    INTELLIGENCE

**Why a new model, not an extension of `TerminologyMappingDecision`.**
`TerminologyMappingDecision` answers "does raw term X, from source
system Y, in organization Z, resolve to canonical concept C?" -- it is
inherently tenant-scoped (`OrganizationScopedMixin`) and always assumes
`C` already exists and is valid. `OntologyConcept` answers a
structurally different, upstream question: "does canonical concept C
exist at all, and is it legitimate?" -- a **platform-wide** question,
answered once for the whole SIE deployment, exactly like
`app/models/knowledge_source.py`'s own GLOBAL (organization_id=None)
rows and `app/api/v1/knowledge.py`'s "only a human PLATFORM_ADMIN may
write GLOBAL content" precedent (see
`app/services/ontology_governance_service.py`'s own docstring for the
full authorization rationale). Conflating the two into one model would
make an org-scoped table try to also hold organization-independent
rows, and would let an org's own `GOVERNANCE_MANAGE` holder influence
every other tenant's ontology -- neither is acceptable.

**Not `OrganizationScopedMixin` -- `organization_id` is nullable instead
(SIE Milestone 25A: Governed Risk-Area & Organization-Extensible Risk
Taxonomy v0.1).** SIE's canonical ontology (like the pre-existing
`SafetyEventType` enum and `terminology_mapping.py`'s own
`_SUBTYPE_ALIASES`) remains, by default, one shared, platform-wide
vocabulary -- `organization_id IS NULL` is exactly that GLOBAL scope,
identical in spirit to `app/models/knowledge_source.py`'s own
`organization_id IS NULL` GLOBAL rows. Milestone 25A adds the ability for
one organization to extend the ontology with its own concept
(`organization_id = <that organization's id>`) -- e.g. a `DROPPED_OBJECTS`
risk area SIE itself never seeded -- without ever touching the Python
enum vocabulary or requiring a migration per new concept. This is
additive and reuses the *same* lifecycle/model/service unchanged in
shape: an organization-scoped concept still goes `PROPOSED -> APPROVED`
through `ontology_governance_service.py`, just authorized against that
organization's own `GOVERNANCE_MANAGE` permission (typically held by its
`ORG_ADMIN`) rather than platform-admin-only -- see that module's own
docstring for the exact authorization rule. A GLOBAL concept
(`organization_id IS NULL`) still requires a true platform administrator,
unchanged from Milestone 15.

**`is_risk_area_eligible` (Milestone 25A).** A second, independent,
additive extension: whether this concept may be used as a Risk Assessment
`RiskAssessmentFinding.risk_area_concept_id` target at all. Not every
governed concept is a risk area (a plain `event_type`/`event_subtype`
concept proposed for an unrelated future purpose should not silently
become selectable as a risk area) -- eligibility is a governed, explicit
flag set at proposal time (`propose_concept(..., is_risk_area_eligible=...)`),
never inferred from `layer` (a risk area may legitimately sit at
`event_type`, `event_subtype`, or `observation_topic` -- see
`app/risk_assessment/risk_area_ontology_seed.py`'s own docstring for the
worked mapping) and never a second, hard-coded list of "which concept_keys
count" living outside this table. See
`app/risk_assessment/risk_area_resolution.py` for the one place this flag
is actually checked before a finding may reference a concept.

**Lifecycle** (mirrors `TerminologyMappingDecision`'s own, deliberately,
for the same governance-discipline reasons -- see that model's own
docstring):

    PROPOSED -> APPROVED
             -> REJECTED
    APPROVED -> DEPRECATED   (a later, separate, explicit operation --
                               never automatic, never silently removes
                               the row; see `deprecate_concept()`)

`PROPOSED` and `REJECTED` are never eligible to validate a
`TerminologyMappingDecision.proposed_canonical_term`/
`provenance["target_event_subtype"]` against -- only `APPROVED` is
(see `ontology_governance_service.is_valid_concept()`). A `REJECTED` or
`DEPRECATED` row is never deleted -- it stays as a permanent, honest
record of "this was considered and is not (or is no longer) part of
the ontology," exactly like a `REJECTED` `TerminologyMappingDecision`
is never deleted either.

**Scope key.** `(layer, parent_domain, concept_key)` is unique --
`layer` is the ontology dimension (`event_type` / `event_subtype` /
`observation_topic`, extensible), `parent_domain` is the enclosing
canonical `event_type` the concept applies under (`None` only for the
`event_type` layer itself, exactly mirroring
`TerminologyMappingDecision.context`'s own convention), and
`concept_key` is the canonical value itself (e.g. `"PPE_COMPLIANCE"`).

**Versioning.** `ontology_version` records which SIE Enterprise
Ontology version first introduced (or, for a later status change, last
touched) this concept -- see
`docs/SIE_ENTERPRISE_ONTOLOGY_V0_1.md`'s own "Versioning" section. A
concept's `ontology_version` never decreases and a concept, once
`APPROVED`, is never renamed or redefined in place -- a genuinely
different definition gets a new `concept_key` and a `superseded_by`-style
note in `justification`, exactly like `TerminologyMappingDecision`'s own
`open_new_version()` never overwrites a terminal row.

**PII.** Nothing here ever needs a worker's name, a real record ID, or
any enterprise-specific content -- only the concept's own name,
definition, and the general (never customer-specific) justification for
introducing it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OntologyConceptLayer:
    """The ontology dimensions this milestone recognizes -- deliberately
    a small, closed, curated set (see `docs/SIE_ENTERPRISE_ONTOLOGY_V0_1.md`'s
    own "Ontology boundaries" section for why `event_subtype` alone is
    not sufficient to represent every kind of enterprise safety concept,
    and what `observation_topic` specifically means)."""

    EVENT_TYPE = "event_type"
    EVENT_SUBTYPE = "event_subtype"
    OBSERVATION_TOPIC = "observation_topic"


LAYERS = (
    OntologyConceptLayer.EVENT_TYPE,
    OntologyConceptLayer.EVENT_SUBTYPE,
    OntologyConceptLayer.OBSERVATION_TOPIC,
)


class OntologyConceptStatus:
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"


STATUSES = (
    OntologyConceptStatus.PROPOSED,
    OntologyConceptStatus.APPROVED,
    OntologyConceptStatus.REJECTED,
    OntologyConceptStatus.DEPRECATED,
)

#: `APPROVED` is the only status eligible to validate a future
#: terminology-mapping proposal against -- mirrors
#: `TerminologyMappingDecision.is_eligible_for_canonical_classification`'s
#: own single-status rule.
ELIGIBLE_STATUSES = (OntologyConceptStatus.APPROVED,)
TERMINAL_STATUSES = (OntologyConceptStatus.APPROVED, OntologyConceptStatus.REJECTED, OntologyConceptStatus.DEPRECATED)


class OntologyConcept(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ontology_concepts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "layer", "parent_domain", "concept_key", name="uq_ontology_concepts_scope"
        ),
    )

    # --- Scope key ---------------------------------------------------------------------------
    #: `NULL` = a GLOBAL, platform-wide concept (Milestone 15's original,
    #: still-default scope); set = an organization-specific extension of
    #: the ontology (Milestone 25A) -- see module docstring. Deliberately
    #: not `OrganizationScopedMixin` (that mixin is NOT NULL) since GLOBAL
    #: concepts genuinely have no owning organization at all.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    layer: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # LAYERS
    #: The canonical `event_type` this concept applies under -- `None`
    #: only for the `event_type` layer itself (a top-level concept has
    #: no enclosing parent).
    parent_domain: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    concept_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # --- Definition ----------------------------------------------------------------------------
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=OntologyConceptStatus.PROPOSED, index=True)

    # --- Versioning ------------------------------------------------------------------------------
    ontology_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- Risk Assessment eligibility (Milestone 25A) -- see module docstring ------------------
    is_risk_area_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    # --- Reviewer identity (mirrors TerminologyMappingDecision's own item 9) ------------------
    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    proposer: Mapped[User | None] = relationship(foreign_keys=[proposed_by_user_id])  # noqa: F821
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_user_id])  # noqa: F821

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_eligible_for_mapping(self) -> bool:
        """The one boolean a future terminology-mapping validation
        actually needs -- only `APPROVED` is."""
        return self.status in ELIGIBLE_STATUSES

    @property
    def is_global(self) -> bool:
        """`organization_id IS NULL` -- a platform-wide SIE concept,
        available to every organization, as opposed to one organization's
        own extension of the ontology (Milestone 25A)."""
        return self.organization_id is None

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<OntologyConcept id={self.id!s} organization_id={self.organization_id!s} layer={self.layer!r} "
            f"parent_domain={self.parent_domain!r} concept_key={self.concept_key!r} status={self.status!r} "
            f"version={self.ontology_version} is_risk_area_eligible={self.is_risk_area_eligible}>"
        )


__all__ = [
    "ELIGIBLE_STATUSES",
    "LAYERS",
    "STATUSES",
    "TERMINAL_STATUSES",
    "OntologyConcept",
    "OntologyConceptLayer",
    "OntologyConceptStatus",
]
