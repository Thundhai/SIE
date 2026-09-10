"""Learning Integration — SIE Milestone 41: the governed bridge answering
*"how does SIE actually use organizational memory to improve
intelligence?"* -- the missing link the loop has needed since SIE
Milestone 40's `OrganizationalMemory`:

    OrganizationalMemory (M40, ACTIVE)
        -> resolve_eligible_organizational_memories()  -- THIS module
            -> deterministic applicability filter against an intelligence
               context (organization/site scope, optional project_id, as_of)
            -> MemoryIntegrationContext -- a list of IntegratedMemory,
               each one traceable back to its own learning candidate,
               outcome, and verification
        -> GET /api/v1/intelligence/memory-context
           GET /api/v1/intelligence/sites/{site_id}/memory-context
           GET /api/v1/intelligence/decisions/{decision_id}/memory-context
           (app/api/v1/intelligence.py, app/api/v1/intelligence_decisions.py)

**This module computes nothing new about intelligence itself.** It does
not touch `compute_enterprise_intelligence()`, `compose_field_
intelligence_context()`, or any prediction/risk/anomaly/trend
computation — those remain entirely unmodified. This module answers a
narrower, orthogonal question: *of the organization's governed
memories, which ones are eligible and applicable right now (or as of a
given historical instant)?* The result is meant to be read *alongside*
existing intelligence output (Observed/Deterministic/Predictive/
Knowledge from M32, or an `IntelligenceDecision`'s own recorded
context) as additional, explicitly-labeled context — never merged into,
and never silently altering, any existing signal.

**Read-only, by construction.** No function in this module calls
`db.add()`, `db.flush()`, or `db.commit()` -- mirrors `app/intelligence/
context_composition.py`'s own "read-only, by construction" contract.
There is no persisted "integration" or "influence" table: M40's own
`OrganizationalMemory`/`OrganizationalMemoryGovernanceDecision` rows and
the immutable M37/M38/M39 provenance chain already contain everything
needed to deterministically reconstruct, at read time, exactly which
memories were eligible and applicable at any `as_of` -- persisting a
second, redundant record of that same fact would be exactly the kind of
duplicate source of truth SIE Milestone 41's own spec (§19) warns
against. See `docs/LEARNING_INTEGRATION_V0_1.md` for the full "why no
migration" account.

**Eligibility -- reused verbatim from M40, never forked (spec §7/§24).**
A memory is eligible for integration iff its resolved current
governance decision, evaluated *as of the same instant the intelligence
context is being evaluated* (`app.services.organizational_memory_
service.resolve_current_memory_governance(..., as_of=as_of)`), is
either absent (implicit `ACTIVE`) or explicitly `ACTIVE`. A `RETRACTED`
resolution excludes the memory. This is the identical function M40's
own `GET .../organizational-memory/{id}/state` endpoint already calls
-- no second "latest memory status" implementation exists anywhere in
this codebase.

**Temporal correctness (spec §8, a hard requirement).** Two independent
`as_of` checks, both required:

1. `OrganizationalMemory.created_at <= as_of` -- a memory that did not
   yet exist at `as_of` can never be considered, regardless of its
   governance state.
2. `resolve_current_memory_governance(..., as_of=as_of)` -- governance
   is resolved *as of the same `as_of`*, never today's current
   governance. A memory `ACTIVE` at `as_of=January 30` and later
   `RETRACTED` on `February 20` is still eligible when evaluated
   `as_of=January 30`, and correctly excluded when evaluated
   `as_of=March 1` -- exactly the worked example in the spec.

Both checks reuse existing, already-tested M40 temporal filters
verbatim; neither is a new reconstruction mechanism.

**Applicability -- explicit, structured, deterministic (spec §9).** Not
every memory is relevant to every context. This module never injects
every organizational memory into every intelligence operation. Instead,
applicability is derived from one already-existing structured field:
the *originating outcome's own* `site_id` (`IntelligenceOutcome.
site_id`, set at M37 record-time, immutable) -- reached via a live join
through the memory's own `learning_candidate_id ->
IntelligenceLearningCandidate.outcome_id`, never copied or
denormalized onto `OrganizationalMemory` itself (M40 deliberately
carries no site/project field of its own; see `MemoryApplicabilityBasis`
below for the resulting four-way, fully-explainable classification).
Project-scoped applicability reuses `app.intelligence.temporal.
is_project_site_associated_as_of()` verbatim -- the exact SIE Milestone
35B/36 point-in-time project/site reconstruction, never a second
project-attribution mechanism.

**No semantic/vector retrieval (spec §12).** Applicability is a plain
structural comparison (`site_id` equality, project/site membership as
of `as_of`) -- no embeddings, no similarity score, no LLM call anywhere
in this module (verified by a static import-audit test, mirroring the
identical M39/M40 precedent).

**Performance note, stated plainly rather than hidden.** Governance
resolution is one small query per eligible-by-time memory (reusing
`resolve_current_memory_governance()` verbatim, per spec §24's explicit
reuse mandate, rather than inlining a second, parallel SQL
reconstruction of "latest governance row"). This is a deliberate
trade-off: `OrganizationalMemory` is, by M40's own design principle, a
small, curated set of durable organizational knowledge -- "experience
that became organizational knowledge," never "everything that
happened" -- so the per-organization row count this loop iterates over
is expected to stay small. If that assumption is ever violated in
practice, a future milestone can introduce a bulk governance-resolution
query without changing this module's public contract.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.temporal import is_project_site_associated_as_of, utcnow
from app.models.intelligence_learning_candidate import IntelligenceLearningCandidate
from app.models.intelligence_outcome import IntelligenceOutcome
from app.models.organizational_memory import OrganizationalMemory
from app.models.organizational_memory_enums import OrganizationalMemoryType
from app.services.organizational_memory_service import resolve_current_memory_governance

MEMORY_INTEGRATION_VERSION = "learning-integration-v1"


class MemoryApplicabilityBasis(str, Enum):
    """Why one eligible memory was judged applicable to a given
    intelligence context -- always exactly one of these four, always
    derived from the same already-existing `IntelligenceOutcome.site_id`
    field, never an opaque score (spec §10's "explainable, never a
    numeric confidence" instruction)."""

    #: The memory's own originating outcome carries no `site_id` at all
    #: -- an organization-wide observation, applicable to any scope
    #: within the organization.
    ORGANIZATION_WIDE = "ORGANIZATION_WIDE"
    #: The context is site-scoped, and the memory's own originating
    #: outcome's `site_id` equals that exact site.
    SITE_MATCH = "SITE_MATCH"
    #: The context is organization-scoped with an explicit `project_id`
    #: narrowing, and the memory's own originating outcome's `site_id`
    #: is one of the sites genuinely associated with that project as of
    #: `as_of` (`is_project_site_associated_as_of()`, SIE Milestone
    #: 35B/36, reused verbatim).
    PROJECT_SITE_MATCH = "PROJECT_SITE_MATCH"
    #: The context is organization-scoped with no `project_id`
    #: narrowing -- an organization-scope rollup, by the same convention
    #: `compute_enterprise_intelligence()`'s own organization scope
    #: already uses, includes every site's data; a site-specific memory
    #: is therefore included, labeled distinctly from `ORGANIZATION_WIDE`
    #: so a caller can always tell "this memory has no site of its own"
    #: apart from "this memory has a site, but the requested scope rolls
    #: up across all sites anyway."
    ORGANIZATION_SCOPE_ROLLUP = "ORGANIZATION_SCOPE_ROLLUP"


@dataclass
class IntegratedMemory:
    """One `OrganizationalMemory` row judged eligible and applicable to
    a given intelligence context -- carries its own full, explicit
    provenance chain (never a second copy of memory/outcome/verification
    content -- spec §16's "reference, never copy" rule) plus the
    governance/applicability facts that explain *why* it appears
    (spec §10)."""

    memory_id: uuid.UUID
    memory_type: OrganizationalMemoryType
    title: str
    memory_content: str
    rationale: str
    memory_created_at: datetime
    learning_candidate_id: uuid.UUID
    outcome_id: uuid.UUID
    verification_id: uuid.UUID
    outcome_site_id: uuid.UUID | None
    applicability_basis: str  # MemoryApplicabilityBasis
    #: Always "ACTIVE" -- only eligible (ACTIVE-resolved) memories ever
    #: appear in `MemoryIntegrationContext.items`. Carried explicitly
    #: (rather than omitted, since it is always the same value) so a
    #: caller reading one `IntegratedMemory` in isolation never has to
    #: assume this fact from context.
    governance_status: str
    #: `False` when no governance decision has ever been recorded for
    #: this memory (the implicit-ACTIVE state); `True` when an explicit
    #: ACTIVE governance decision was found as of `as_of` -- see
    #: `OrganizationalMemoryGovernanceStatus`'s own docstring for why
    #: absence means ACTIVE here, unlike M39's candidates.
    governance_is_explicit: bool
    governance_decided_at: datetime | None


@dataclass
class MemoryIntegrationContext:
    scope: str  # "organization" | "site"
    organization_id: uuid.UUID
    entity_id: uuid.UUID | None  # site_id, when scope == "site"
    project_id: uuid.UUID | None
    as_of: datetime
    generated_at: datetime
    items: list[IntegratedMemory] = field(default_factory=list)
    calculation_version: str = MEMORY_INTEGRATION_VERSION


def _resolve_applicability_basis(
    db: Session,
    *,
    outcome_site_id: uuid.UUID | None,
    scope: str,
    site_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    as_of: datetime,
) -> MemoryApplicabilityBasis | None:
    """`None` means "not applicable to this context" -- the caller
    excludes the memory. See `MemoryApplicabilityBasis`'s own docstring
    for what each returned value means."""
    if outcome_site_id is None:
        return MemoryApplicabilityBasis.ORGANIZATION_WIDE
    if scope == "site":
        if site_id is not None and outcome_site_id == site_id:
            return MemoryApplicabilityBasis.SITE_MATCH
        return None
    # scope == "organization"
    if project_id is not None:
        if is_project_site_associated_as_of(
            db, organization_id=organization_id, project_id=project_id, site_id=outcome_site_id, as_of=as_of
        ):
            return MemoryApplicabilityBasis.PROJECT_SITE_MATCH
        return None
    return MemoryApplicabilityBasis.ORGANIZATION_SCOPE_ROLLUP


def resolve_eligible_organizational_memories(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: str,
    site_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    as_of: datetime | None = None,
) -> MemoryIntegrationContext:
    """The one entry point this milestone adds. `scope`/`site_id` carry
    the identical contract `compose_field_intelligence_context()`
    already documents: for `"site"`, `site_id` must already have been
    verified to belong to `organization_id` by the caller. `project_id`
    only narrows applicability at organization scope (see
    `MemoryApplicabilityBasis.PROJECT_SITE_MATCH`'s own docstring for
    why it is a no-op at site scope, where the site is already fixed).

    Returns memories ordered deterministically -- `OrganizationalMemory.
    created_at DESC, id DESC`, identical to every other M37-M40 list
    read in this codebase -- and never reorders after that: applicability
    and eligibility are pure filters, never a re-ranking."""
    as_of = as_of or utcnow()

    rows = db.execute(
        select(
            OrganizationalMemory,
            IntelligenceLearningCandidate.outcome_id,
            IntelligenceLearningCandidate.verification_id,
            IntelligenceOutcome.site_id,
        )
        .select_from(OrganizationalMemory)
        .join(
            IntelligenceLearningCandidate,
            OrganizationalMemory.learning_candidate_id == IntelligenceLearningCandidate.id,
        )
        .join(IntelligenceOutcome, IntelligenceLearningCandidate.outcome_id == IntelligenceOutcome.id)
        .where(
            OrganizationalMemory.organization_id == organization_id,
            OrganizationalMemory.created_at <= as_of,
        )
        .order_by(OrganizationalMemory.created_at.desc(), OrganizationalMemory.id.desc())
    ).all()

    items: list[IntegratedMemory] = []
    for memory, outcome_id, verification_id, outcome_site_id in rows:
        current_governance = resolve_current_memory_governance(
            db, organization_id=organization_id, memory_id=memory.id, as_of=as_of
        )
        if current_governance is not None and current_governance.status.value != "ACTIVE":
            continue  # RETRACTED as of as_of -- never eligible (spec §7)

        basis = _resolve_applicability_basis(
            db,
            outcome_site_id=outcome_site_id,
            scope=scope,
            site_id=site_id,
            project_id=project_id,
            organization_id=organization_id,
            as_of=as_of,
        )
        if basis is None:
            continue  # not applicable to this context -- excluded, never merely deprioritized

        items.append(
            IntegratedMemory(
                memory_id=memory.id,
                memory_type=memory.memory_type,
                title=memory.title,
                memory_content=memory.memory_content,
                rationale=memory.rationale,
                memory_created_at=memory.created_at,
                learning_candidate_id=memory.learning_candidate_id,
                outcome_id=outcome_id,
                verification_id=verification_id,
                outcome_site_id=outcome_site_id,
                applicability_basis=basis.value,
                governance_status="ACTIVE",
                governance_is_explicit=current_governance is not None,
                governance_decided_at=(current_governance.decided_at if current_governance is not None else None),
            )
        )

    return MemoryIntegrationContext(
        scope=scope,
        organization_id=organization_id,
        entity_id=site_id,
        project_id=project_id,
        as_of=as_of,
        generated_at=utcnow(),
        items=items,
    )


__all__ = [
    "MEMORY_INTEGRATION_VERSION",
    "MemoryApplicabilityBasis",
    "IntegratedMemory",
    "MemoryIntegrationContext",
    "resolve_eligible_organizational_memories",
]
