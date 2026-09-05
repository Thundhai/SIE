"""Enumerations for the Risk Assessment domain — SIE Milestone 25:
Enterprise Risk Assessment Foundation v0.1.

Mirrors `app/models/safety_action_enums.py`'s own stated philosophy: a
domain that needs a real, enforced state machine gets its own small enums
module, backed by native PostgreSQL enum columns (every table this
milestone introduces is brand-new, created via `op.create_table()`,
which auto-creates the enum type — safe from migration 0005's
enum-type-creation defect exactly like `safety_actions`' own columns
already are; see that module's docstring).

**`RiskArea` — removed (SIE Milestone 25A: Governed Risk-Area &
Organization-Extensible Risk Taxonomy v0.1).** Milestone 25 originally
represented risk areas as this closed Python enum (11 members, each
mirroring an already-established concept key elsewhere in this
codebase). Milestone 25A replaces it entirely:
`RiskAssessmentFinding.risk_area_concept_id` now references a governed
`OntologyConcept` row directly (`app/models/ontology_concept.py`) —
SIE's original 11 risk areas remain fully usable (seeded, as GLOBAL,
`is_risk_area_eligible=True` concepts, by migration 0017 — see
`app/risk_assessment/risk_area_ontology_seed.py`), but an organization
may now extend the taxonomy with its own governed concept (e.g.
`DROPPED_OBJECTS`) with no Python enum change and no migration. See
`app/risk_assessment/risk_area_resolution.py` for the one place a
finding's `risk_area_concept_id` is validated, and
`docs/RISK_ASSESSMENT_FOUNDATION_V0_1.md` for the full rationale. There
is deliberately only one authoritative risk-area taxonomy left in this
codebase (never this enum *and* `OntologyConcept` both).

**Risk matrix vocabulary (items 9-10).** `RiskAssessmentRiskBand` uses
the same LOW/MODERATE/HIGH/CRITICAL *words* `app/intelligence/enums.py::
RiskClassification` uses for `enterprise-risk-v1`'s own 0-100 score bands
— but is a deliberately distinct enum/scale, mirroring
`ConcentrationClassification`'s own precedent (same milestone) for
exactly the same reason: a "16/HIGH" risk-matrix rating must never be
confused with, or numerically compared against, `enterprise-risk-v1`'s
own unrelated "62/HIGH" score. See `app/models/risk_assessment.py`'s own
docstring for the full "inherent risk ≠ enterprise-risk-v1" boundary
(item 10).
"""

from enum import Enum


class RiskAssessmentScope(str, Enum):
    """Item 5. `LOCATION` is accepted at the schema/API level for
    forward compatibility with the assessment hierarchy the milestone
    describes (item 3) — but SIE's current data model has no first-class
    `Location` entity (only `Organization` -> `Site`; see
    `app/models/site.py`), and item 5 is explicit that this milestone
    must not invent a parallel location table merely to fill that gap.
    A `LOCATION`-scope assessment is therefore, today, structurally
    identical to an `ORGANIZATION`-scope one (`site_id` stays `NULL`;
    intelligence context is computed at organization scope) — the
    distinction is scope semantics/title only until a genuine `Location`
    model is introduced in a future milestone, at which point this
    member becomes meaningful without any breaking change to the enum,
    the API contract, or stored data."""

    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    SITE = "SITE"


class RiskAssessmentStatus(str, Enum):
    """The assessment lifecycle (item 4). `APPROVED` is not directly
    editable and `SUPERSEDED` is historical-only/fully terminal — see
    `is_allowed_assessment_transition()` below. `SUPERSEDED` is reached
    only as the automatic side effect of a new version, in the same
    lineage, being approved (`app/services/risk_assessment_service.py::
    open_new_version()`) — there is no direct client-invoked "supersede"
    operation in this milestone's own minimum API surface (item 22)."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class RiskAssessmentRiskBand(str, Enum):
    """The risk-matrix band (items 9-10) — see module docstring for why
    this is a distinct enum from `app/intelligence/enums.py::
    RiskClassification` despite sharing the same four words."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, Enum):
    """An assessment finding's own tracking status — deliberately
    distinct from `RiskCandidateStatus` below (a finding can be `OPEN`
    for months while still `ACCEPTED` as a candidate) and from
    `app.models.safety_action_enums.ActionStatus` (a finding is not an
    action; it may *link to* one or more, via
    `RiskAssessmentFindingEvidence`, item 17)."""

    OPEN = "OPEN"
    ADDRESSED = "ADDRESSED"
    CLOSED = "CLOSED"


class RiskCandidateStatus(str, Enum):
    """Item 15's own named states. `NULL` on
    `RiskAssessmentFinding.candidate_status` (not a fifth member here)
    means "not system-generated at all" — a finding a human authored
    directly, never subject to candidate review in the first place. Only
    `ACCEPTED` candidates (or a `NULL`/manually-authored finding) may ever
    carry a `likelihood`/`consequence` rating — see
    `app/models/risk_assessment.py`'s own "candidate ≠ approved risk"
    docstring section (item 15's own instruction, item 27's architectural
    boundary)."""

    IDENTIFIED = "IDENTIFIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class FindingSource(str, Enum):
    """What produced this finding (item 7's "source", item 15's
    "originating intelligence type" — the same vocabulary answers both:
    a system-generated finding's `source` *is* its originating
    intelligence type). `MANUAL`/`INSPECTION` are the two non-candidate
    origins (`candidate_status` stays `NULL` for both); every other
    member is system-generated (`candidate_status` starts `IDENTIFIED`)
    and traces back to a specific, already-existing SIE Milestone 22-24
    computation — never a fabricated source."""

    MANUAL = "MANUAL"
    INSPECTION = "INSPECTION"
    INTELLIGENCE_RISK_SCORE = "INTELLIGENCE_RISK_SCORE"
    INTELLIGENCE_ANOMALY = "INTELLIGENCE_ANOMALY"
    INTELLIGENCE_PATTERN = "INTELLIGENCE_PATTERN"
    INTELLIGENCE_ASSOCIATION = "INTELLIGENCE_ASSOCIATION"
    INTELLIGENCE_CONCENTRATION = "INTELLIGENCE_CONCENTRATION"
    INTELLIGENCE_TREND = "INTELLIGENCE_TREND"
    INTELLIGENCE_INDICATOR = "INTELLIGENCE_INDICATOR"
    KNOWLEDGE = "KNOWLEDGE"


class ControlType(str, Enum):
    """The milestone's own example list (item 11) — deliberately compact,
    mirroring `app/models/safety_action_enums.py::ActionType`'s own
    "intentionally compact, not a complete framework" precedent. Not a
    Bow-Tie/HAZOP/LOPA hierarchy-of-controls engine (item 11's own "do
    not build" instruction) — just a closed label."""

    ELIMINATION = "ELIMINATION"
    SUBSTITUTION = "SUBSTITUTION"
    ENGINEERING = "ENGINEERING"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    PPE = "PPE"


class ControlStatus(str, Enum):
    """Whether a control actually exists yet — distinct from
    `ControlEffectiveness` below (item 12's own "distinguish 'no control
    information was provided' from 'the control is ineffective'" — those
    are two different fields answering two different questions, not one
    field trying to answer both)."""

    PROPOSED = "PROPOSED"
    IN_PLACE = "IN_PLACE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class ControlEffectiveness(str, Enum):
    """Item 12, verbatim. `NOT_ASSESSED` (the default) is a genuinely
    different state from `INEFFECTIVE` — "no control information was
    provided" must never be silently read as "the control is
    ineffective," and this codebase never conflates the two anywhere a
    residual-risk rating is derived."""

    NOT_ASSESSED = "NOT_ASSESSED"
    INEFFECTIVE = "INEFFECTIVE"
    PARTIALLY_EFFECTIVE = "PARTIALLY_EFFECTIVE"
    EFFECTIVE = "EFFECTIVE"


class RiskEvidenceType(str, Enum):
    """What kind of thing a `RiskAssessmentFindingEvidence` row points at
    (item 8). `EVENT`/`ACTION`/`KNOWLEDGE_DOCUMENT` carry a real
    `reference_id` (validated, at write time, to belong to the same
    organization — or be `GLOBAL` knowledge — mirroring
    `app/services/safety_action_service.py`'s own reference-validation
    precedent). `ANOMALY`/`PATTERN`/`ASSOCIATION` reference a
    *computed*, non-persisted intelligence result (Milestones 23/24
    produce no database row of their own for one anomaly/pattern/
    association) — for those, `reference_id` stays `NULL` and
    `reference_label` carries the exact, already-established
    `evidence_reference` string format
    `app/intelligence/explanations.py` already produces (e.g.
    `"anomaly:incident_count"`, a recurrence `pattern_key`,
    `"association:incident_count:near_miss_count"`) — reused verbatim,
    never a second, competing reference format."""

    EVENT = "EVENT"
    ANOMALY = "ANOMALY"
    PATTERN = "PATTERN"
    ASSOCIATION = "ASSOCIATION"
    KNOWLEDGE_DOCUMENT = "KNOWLEDGE_DOCUMENT"
    ACTION = "ACTION"
    OTHER = "OTHER"


# --- Assessment lifecycle transition matrix (item 4, item 23) -------------------------

_ALLOWED_ASSESSMENT_TRANSITIONS: dict[RiskAssessmentStatus, frozenset[RiskAssessmentStatus]] = {
    RiskAssessmentStatus.DRAFT: frozenset({RiskAssessmentStatus.IN_REVIEW}),
    RiskAssessmentStatus.IN_REVIEW: frozenset({RiskAssessmentStatus.APPROVED}),
    # APPROVED -> SUPERSEDED happens only as the automatic side effect of
    # approving a new version in the same lineage (see
    # app/services/risk_assessment_service.py::open_new_version()) --
    # still expressed here so is_allowed_assessment_transition() stays the
    # single source of truth for "is this transition ever legal at all",
    # exactly like app/models/safety_action_enums.py's own matrix.
    RiskAssessmentStatus.APPROVED: frozenset({RiskAssessmentStatus.SUPERSEDED}),
    RiskAssessmentStatus.SUPERSEDED: frozenset(),
}

#: Only these two statuses may ever be mutated via PATCH (item 23:
#: "DRAFT: Editable. IN_REVIEW: Controlled editing. APPROVED: Not
#: directly editable. SUPERSEDED: Historical only.").
ASSESSMENT_EDITABLE_STATUSES: frozenset[RiskAssessmentStatus] = frozenset(
    {RiskAssessmentStatus.DRAFT, RiskAssessmentStatus.IN_REVIEW}
)


def is_allowed_assessment_transition(current: str, target: str) -> bool:
    """Mirrors `app.models.safety_action_enums.is_allowed_action_transition()`
    exactly: an unrecognized `current`/`target` string is simply not an
    allowed transition (returns `False`), never an exception."""
    try:
        return RiskAssessmentStatus(target) in _ALLOWED_ASSESSMENT_TRANSITIONS[RiskAssessmentStatus(current)]
    except ValueError:
        return False


__all__ = [
    "ASSESSMENT_EDITABLE_STATUSES",
    "ControlEffectiveness",
    "ControlStatus",
    "ControlType",
    "FindingSource",
    "FindingStatus",
    "RiskAssessmentRiskBand",
    "RiskAssessmentScope",
    "RiskAssessmentStatus",
    "RiskCandidateStatus",
    "RiskEvidenceType",
    "is_allowed_assessment_transition",
]
