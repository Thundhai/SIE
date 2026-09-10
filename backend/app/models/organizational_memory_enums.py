"""Enums for `app/models/organizational_memory.py` — SIE Milestone 40:
Organizational Memory Architecture.
"""

from enum import Enum


class OrganizationalMemoryType(str, Enum):
    """A deliberately small, closed taxonomy of *what kind of durable
    knowledge* one organizational memory represents — not a
    classification of the underlying operational event/incident (that
    is `OntologyConcept`'s own job — see below for why this is a
    separate, non-ontology-backed enum).

    LESSON_LEARNED         -- a general takeaway from an accepted
                               experience, applicable beyond the single
                               originating outcome.
    EFFECTIVE_PRACTICE      -- a specific approach/control that worked
                               and is worth repeating.
    FAILED_APPROACH         -- a specific approach/control that did not
                               work, worth avoiding in future.
    EARLY_WARNING_PATTERN   -- a recognizable precursor pattern the
                               organization wants to watch for going
                               forward.
    CONTROL_INSIGHT         -- an insight specifically about the
                               adequacy/gap of an existing control.

    **Why this is a plain, closed Python/DB enum, never an
    `OntologyConcept`.** `OntologyConcept`'s `layer` values
    (`event_type` / `event_subtype` / `observation_topic`) classify
    *what happened in the operational world* -- the same axis
    `SafetyEvent.event_type`/`event_subtype` already uses. This enum
    classifies a completely orthogonal axis: *what epistemic kind of
    organizational knowledge statement this memory is* -- a property of
    the memory record itself, not of the incident/event it derives
    from. Routing it through `OntologyConcept` would conflate two
    unrelated classification systems (one governs safety-event
    terminology, the other governs a knowledge-statement's own shape)
    and would let an ontology governance action accidentally add or
    remove valid *memory* categories -- a capability nobody has asked
    for and that M40 spec §8 explicitly warns against ("Do NOT make the
    taxonomy closed in a way that conflicts with SIE's ontology
    architecture" -- satisfied here precisely by keeping the two
    systems independent, never overlapping, never in tension).
    Precedent: `IntelligenceOutcomeClassification` and
    `IntelligenceLearningCandidateGovernanceStatus` are the identical
    kind of small, closed, non-ontology-backed enum for their own
    milestones' own record-shape concepts -- this mirrors that
    established pattern exactly, not a new one.
    """

    LESSON_LEARNED = "LESSON_LEARNED"
    EFFECTIVE_PRACTICE = "EFFECTIVE_PRACTICE"
    FAILED_APPROACH = "FAILED_APPROACH"
    EARLY_WARNING_PATTERN = "EARLY_WARNING_PATTERN"
    CONTROL_INSIGHT = "CONTROL_INSIGHT"


class OrganizationalMemoryGovernanceStatus(str, Enum):
    """The resolved lifecycle state of one `OrganizationalMemory` row --
    deliberately binary, mirroring `IntelligenceLearningCandidateGovernanceStatus`'s
    own small-taxonomy discipline (M39 precedent) applied to a
    different question:

    ACTIVE    -- the memory is currently considered valid organizational
                 knowledge. This is the implicit state of a
                 newly-created memory (no governance-decision row yet
                 exists) -- mirrors `IntelligenceLearningCandidate`'s
                 own "absence of a governance decision is its own valid
                 state" precedent, except here the default absent state
                 is ACTIVE (a memory is authoritative the moment an
                 authorized actor creates it) rather than "pending"
                 (M39's candidates start unresolved because a *separate*
                 human still has to judge them; M40's memory is already
                 the direct output of that same judgment).
    RETRACTED -- a later, explicit human act: this memory turned out to
                 be outdated, incorrect, or no longer applicable. Per
                 M40 spec §11, retracting a memory never erases or edits
                 the original knowledge statement -- it is a new,
                 append-only governance-decision row layered on top,
                 exactly like a corrected M38 verification or a
                 reconsidered M39 governance decision. A retracted
                 memory's history (including why it was created and
                 why it was later retracted) remains fully readable
                 forever.

    Reactivation (a later ACTIVE row after a RETRACTED one) is
    permitted by the same append-only mechanism -- a reviewer changing
    their mind twice is still just two more rows, never a mutation.
    """

    ACTIVE = "ACTIVE"
    RETRACTED = "RETRACTED"


__all__ = ["OrganizationalMemoryType", "OrganizationalMemoryGovernanceStatus"]
