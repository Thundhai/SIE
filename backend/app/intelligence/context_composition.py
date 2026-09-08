"""Field Intelligence Context composition — SIE Milestone 32: Field
Intelligence Context Composition v0.1, the first *implementation*
milestone of the Field Intelligence Context work
(`backend/docs/SIE_FIELD_INTELLIGENCE_CONTEXT_V0_1.md`, §7).

    compute_enterprise_intelligence()  -> Observed (partial) + Deterministic + Predictive (raw)
        + a handful of new, bounded, read-only queries -> Observed (rest)
        + RetrievalService.search() (only when a query is supplied)      -> Knowledge/Evidence
        -> assembled, never merged, into FieldIntelligenceContextResult
        -> GET /api/v1/intelligence/context (app/api/v1/intelligence.py)

**This module computes nothing new.** Every number in this response
already exists somewhere in this codebase, produced by a function this
module calls verbatim:

* Deterministic signal, predictive signal (raw), `actions_context`
  counts, `data_sufficiency`, `event_count`, and the evidence-sample
  event ids all come from `compute_enterprise_intelligence()`
  (`app/intelligence/enterprise_intelligence_service.py`) — called
  exactly once, exactly as `app/api/v1/intelligence.py`'s own
  `/enterprise` and `/sites/{id}` routes already call it. This module
  never re-implements indicators, trend, anomaly, recurrence,
  association, or `enterprise-risk-v1`.
* Knowledge/evidence comes from `RetrievalService.search()`
  (`app/retrieval/retrieval_service.py`) — called exactly as
  `app/api/v1/retrieval.py` already calls it, unchanged.
* The remaining Observed-category facts (open findings, open actions)
  are the one genuinely new piece of work this milestone adds: a small,
  bounded number of `SELECT`s over already-existing tables
  (`RiskAssessment`/`RiskAssessmentFinding`/`RiskAssessmentControl`/
  `SafetyAction`), mirroring `_actions_context()`'s own
  "point-in-time-filtered, tenant-scoped, no query in a loop" shape —
  never a new statistical or risk-scoring computation.

**Four categories, never merged (§7's own Diagram C).** `Observed`,
`Deterministic`, `Predictive`, `Knowledge/Evidence` are always four
separate, separately-labeled sections of the response — this module
builds one `FieldIntelligenceContextResult` dataclass with one field
per category, never a single flattened dict a caller could
accidentally treat as one undifferentiated feed. `deterministic_risk`
and `predictive_signal` in particular are never combined into one
number (§9's own explicit rule, inherited unchanged from
`compute_enterprise_intelligence()`'s own docstring).

**The staleness rule (§10).** `compute_enterprise_intelligence()`'s own
`_predictive_context()` deliberately has no `as_of` filter on
`Prediction` itself (it always returns the *latest* recorded
prediction for the site, regardless of when `as_of` is) — correct for
its own "always show the latest governed prediction" contract, but
wrong for a historical Field Intelligence Context: replaying
`as_of=<six months ago>` must never surface a prediction that was
*generated* after that historical instant as if it were contemporaneous
knowledge. This module adds exactly one extra check on top of the
already-fetched `PredictiveContext` (a single by-id lookup of the same
`Prediction` row already selected — no new computation, and normally
served from the session identity map rather than a new round trip):
when `Prediction.created_at > as_of`, the raw value is withheld and
`PredictiveSignalOutcome.EXCLUDED_GENERATED_AFTER_AS_OF` is returned
instead of the prediction — never included with a flag a caller could
ignore.

**Failure isolation, not blanket failure-to-normal conversion.** The
four categories are composed independently (mirroring
`HomePage.tsx`'s "one `AsyncState` per section" pattern, M30 §3.12,
M31 §7's own explicit "mirrors HomePage.tsx" instruction). A failure
reading Observed's finding/action queries never blanks Deterministic or
Predictive (already computed from the same `compute_enterprise_intelligence()`
call) — it is reported as `ObservedFactOutcome.UNAVAILABLE` with the
error's own message, distinct from `ObservedFactOutcome.OK` (there is
nothing to blank into "no findings" or "0" that could be confused with
a genuinely empty result). Knowledge/Evidence is `NOT_QUERIED` when no
`knowledge_query` was supplied at all (not attempted, and not an
error), `UNAVAILABLE` when a query was supplied and the retrieval call
itself raised, and otherwise carries `RetrievalResponse.outcome`
verbatim (`RESULTS`/`NO_RELEVANT_EVIDENCE`) unchanged.

**Read-only.** No function in this module calls `db.add()`, `db.flush()`,
or `db.commit()` — mirrors `app/risk_assessment/reporting.py`'s own
"read-only, by construction" contract, applied here instead to a
cross-domain composition rather than one assessment's own report.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.enterprise_intelligence_service import (
    ActionsContext,
    EnterpriseIntelligenceResult,
    PredictiveContext,
    Provenance,
    compute_enterprise_intelligence,
)
from app.intelligence.temporal import utcnow
from app.models.ontology_concept import OntologyConcept
from app.models.prediction import Prediction
from app.models.risk_assessment import RiskAssessment, RiskAssessmentControl, RiskAssessmentFinding
from app.models.risk_assessment_enums import FindingStatus, RiskAssessmentStatus, RiskCandidateStatus
from app.models.safety_action import SafetyAction
from app.models.safety_action_enums import ActionStatus
from app.retrieval.filters import RetrievalFilters
from app.retrieval.results import RetrievalResponse
from app.retrieval.retrieval_service import retrieval_service

logger = logging.getLogger(__name__)

FIELD_INTELLIGENCE_CONTEXT_COMPOSITION_VERSION = "field-intelligence-context-v1"

# Bounded, fixed-size samples -- never proportional to org/site data
# volume, the same discipline `_MAX_EVIDENCE_SAMPLE` already establishes
# in `enterprise_intelligence_service.py`.
_MAX_FINDING_SAMPLE = 10
_MAX_ACTION_SAMPLE = 10


def _as_utc(value: datetime) -> datetime:
    """Identical to `enterprise_intelligence_service._as_utc()` — SQLite
    does not round-trip `tzinfo`; every value this codebase writes is
    already UTC, this only restores the label."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


# --- Observed ------------------------------------------------------------------------------


class ObservedFactOutcome(str, Enum):
    OK = "OK"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class ObservedFinding:
    finding_id: uuid.UUID
    title: str
    status: str
    risk_area_label: str
    inherent_risk_classification: str | None
    residual_risk_classification: str | None
    assessment_id: uuid.UUID
    site_id: uuid.UUID | None
    created_at: datetime


@dataclass
class ObservedAction:
    action_id: uuid.UUID
    title: str
    status: str
    priority: str
    due_date: datetime | None
    site_id: uuid.UUID | None


@dataclass
class ObservedFactSummary:
    outcome: str  # ObservedFactOutcome
    unavailable_reason: str | None
    event_count: int
    evidence_sample_event_ids: list[uuid.UUID]
    open_finding_count: int
    open_finding_sample: list[ObservedFinding]
    open_finding_control_count: int
    actions: ActionsContext | None
    open_action_sample: list[ObservedAction]


def _open_finding_clauses(*, organization_id: uuid.UUID, as_of: datetime, site_id: uuid.UUID | None) -> list:
    """Shared filter for "what this organization currently, governedly,
    considers an open finding, as of `as_of`" — reused, unchanged, by
    the count query, the sample query, and the associated-control count
    query below, so the three can never silently disagree about what
    counts as "open."

    Only `APPROVED` assessments count (never `DRAFT`/`IN_REVIEW` —
    unapproved work-in-progress is not yet a governed organizational
    fact) and only human-confirmed findings (`candidate_status` `NULL`
    -- human-authored -- or `ACCEPTED` -- a reviewed, accepted
    system-generated candidate; `IDENTIFIED`/`UNDER_REVIEW` are still
    unreviewed system suggestions, and `REJECTED` was explicitly
    declined -- see `RiskCandidateStatus`'s own docstring). Both the
    assessment's own `approved_at` and the finding's own `created_at`
    are point-in-time filtered against `as_of` -- an assessment approved,
    or a finding created, after the requested `as_of` must not appear in
    a historical view (`events_as_of()`'s own discipline, applied here to
    a different table)."""
    clauses = [
        RiskAssessment.organization_id == organization_id,
        RiskAssessment.status == RiskAssessmentStatus.APPROVED,
        RiskAssessment.approved_at.isnot(None),
        RiskAssessment.approved_at <= as_of,
        RiskAssessmentFinding.status != FindingStatus.CLOSED,
        RiskAssessmentFinding.created_at <= as_of,
        (
            RiskAssessmentFinding.candidate_status.is_(None)
            | (RiskAssessmentFinding.candidate_status == RiskCandidateStatus.ACCEPTED)
        ),
    ]
    if site_id is not None:
        clauses.append(RiskAssessment.site_id == site_id)
    return clauses


def _observed_findings(
    db: Session, *, organization_id: uuid.UUID, as_of: datetime, site_id: uuid.UUID | None
) -> tuple[int, list[ObservedFinding], int]:
    """Three bounded queries: a count, a capped sample (never more rows
    fetched than `_MAX_FINDING_SAMPLE`, regardless of how many open
    findings actually exist), and a count of controls belonging to
    those same open findings -- never a per-finding control query (no
    query in a loop, mirroring `compute_enterprise_intelligence()`'s own
    "exactly four queries... regardless of how many" discipline)."""
    clauses = _open_finding_clauses(organization_id=organization_id, as_of=as_of, site_id=site_id)

    count = db.execute(
        select(func.count(RiskAssessmentFinding.id))
        .select_from(RiskAssessmentFinding)
        .join(RiskAssessment, RiskAssessmentFinding.assessment_id == RiskAssessment.id)
        .where(*clauses)
    ).scalar_one()

    rows = db.execute(
        select(
            RiskAssessmentFinding.id,
            RiskAssessmentFinding.title,
            RiskAssessmentFinding.status,
            RiskAssessmentFinding.inherent_risk_classification,
            RiskAssessmentFinding.residual_risk_classification,
            RiskAssessmentFinding.assessment_id,
            RiskAssessmentFinding.created_at,
            RiskAssessment.site_id,
            OntologyConcept.concept_key,
        )
        .select_from(RiskAssessmentFinding)
        .join(RiskAssessment, RiskAssessmentFinding.assessment_id == RiskAssessment.id)
        .join(OntologyConcept, RiskAssessmentFinding.risk_area_concept_id == OntologyConcept.id)
        .where(*clauses)
        .order_by(RiskAssessmentFinding.created_at.desc())
        .limit(_MAX_FINDING_SAMPLE)
    ).all()
    sample = [
        ObservedFinding(
            finding_id=finding_id,
            title=title,
            status=status.value if hasattr(status, "value") else status,
            risk_area_label=concept_key,
            inherent_risk_classification=inherent,
            residual_risk_classification=residual,
            assessment_id=assessment_id,
            site_id=finding_site_id,
            created_at=created_at,
        )
        for finding_id, title, status, inherent, residual, assessment_id, created_at, finding_site_id, concept_key in rows
    ]

    control_count = db.execute(
        select(func.count(RiskAssessmentControl.id))
        .select_from(RiskAssessmentControl)
        .join(RiskAssessmentFinding, RiskAssessmentControl.finding_id == RiskAssessmentFinding.id)
        .join(RiskAssessment, RiskAssessmentFinding.assessment_id == RiskAssessment.id)
        .where(*clauses)
    ).scalar_one()

    return count, sample, control_count


def _observed_actions_sample(
    db: Session, *, organization_id: uuid.UUID, as_of: datetime, site_id: uuid.UUID | None
) -> list[ObservedAction]:
    """One capped, point-in-time-filtered query -- the same
    `created_at <= as_of` discipline `_actions_context()` already
    applies (Milestone 22A item 3), reused here rather than
    reinterpreted. Aggregate counts (`open_action_count`,
    `overdue_action_count`, `high_priority_action_count`) are never
    recomputed here -- they come from `ActionsContext`
    (`compute_enterprise_intelligence()`'s own `_actions_context()`),
    reused verbatim; this query only supplies the small, concrete
    sample list that a count alone cannot."""
    clauses = [
        SafetyAction.organization_id == organization_id,
        SafetyAction.created_at <= as_of,
        SafetyAction.status == ActionStatus.OPEN,
    ]
    if site_id is not None:
        clauses.append(SafetyAction.site_id == site_id)
    rows = db.execute(
        select(
            SafetyAction.id,
            SafetyAction.title,
            SafetyAction.status,
            SafetyAction.priority,
            SafetyAction.due_date,
            SafetyAction.site_id,
        )
        .where(*clauses)
        # Ordered by due_date only, soonest first (nulls last) -- not by
        # priority: ActionPriority's own string values do not sort into
        # severity order alphabetically (CRITICAL < HIGH < LOW < MEDIUM),
        # so ordering by it would silently misrepresent urgency.
        .order_by(SafetyAction.due_date.asc().nulls_last())
        .limit(_MAX_ACTION_SAMPLE)
    ).all()
    return [
        ObservedAction(
            action_id=action_id,
            title=title,
            status=status.value if hasattr(status, "value") else status,
            priority=priority.value if hasattr(priority, "value") else priority,
            due_date=due_date,
            site_id=action_site_id,
        )
        for action_id, title, status, priority, due_date, action_site_id in rows
    ]


def _observed_fact_summary(
    db: Session, *, enterprise: EnterpriseIntelligenceResult, organization_id: uuid.UUID, as_of: datetime, site_id: uuid.UUID | None
) -> ObservedFactSummary:
    """`event_count`/`evidence_sample_event_ids` are read straight off
    the already-computed `enterprise` result -- zero new queries for the
    event half of Observed (they were already fetched via
    `events_as_of()` inside `compute_enterprise_intelligence()`). Only
    the finding/control/action reads below are new. Wrapped so a failure
    here (e.g. a transient DB error on the new queries) never blanks the
    Deterministic/Predictive categories already computed from the same
    `enterprise` result -- see module docstring's "failure isolation"
    section."""
    try:
        open_finding_count, open_finding_sample, control_count = _observed_findings(
            db, organization_id=organization_id, as_of=as_of, site_id=site_id
        )
        open_action_sample = _observed_actions_sample(db, organization_id=organization_id, as_of=as_of, site_id=site_id)
    except Exception as exc:  # noqa: BLE001 -- deliberate: isolate this category's failure, never the whole response
        logger.exception("Field Intelligence Context: Observed-category query failed")
        return ObservedFactSummary(
            outcome=ObservedFactOutcome.UNAVAILABLE.value,
            unavailable_reason=str(exc),
            event_count=enterprise.event_count,
            evidence_sample_event_ids=list(enterprise.provenance.evidence_sample_event_ids),
            open_finding_count=0,
            open_finding_sample=[],
            open_finding_control_count=0,
            actions=enterprise.actions_context,
            open_action_sample=[],
        )
    return ObservedFactSummary(
        outcome=ObservedFactOutcome.OK.value,
        unavailable_reason=None,
        event_count=enterprise.event_count,
        evidence_sample_event_ids=list(enterprise.provenance.evidence_sample_event_ids),
        open_finding_count=open_finding_count,
        open_finding_sample=open_finding_sample,
        open_finding_control_count=control_count,
        actions=enterprise.actions_context,
        open_action_sample=open_action_sample,
    )


# --- Predictive ------------------------------------------------------------------------------


class PredictiveSignalOutcome(str, Enum):
    AVAILABLE = "AVAILABLE"
    # No `Prediction` row exists for this site (or this is an
    # organization-scope request -- `PredictiveContext` is site-only,
    # see `_predictive_context()`'s own docstring).
    NOT_AVAILABLE = "NOT_AVAILABLE"
    # A prediction exists, but it was generated (Prediction.created_at)
    # after the requested as_of -- withheld, never presented as
    # contemporaneous. See module docstring's "the staleness rule".
    EXCLUDED_GENERATED_AFTER_AS_OF = "EXCLUDED_GENERATED_AFTER_AS_OF"


@dataclass
class PredictiveSignalContext:
    outcome: str  # PredictiveSignalOutcome
    value: PredictiveContext | None


def _predictive_signal(db: Session, *, enterprise: EnterpriseIntelligenceResult, as_of: datetime) -> PredictiveSignalContext:
    prediction = enterprise.predictive_context
    if prediction is None:
        return PredictiveSignalContext(outcome=PredictiveSignalOutcome.NOT_AVAILABLE.value, value=None)

    # Single by-id lookup of the exact row compute_enterprise_intelligence()
    # already selected -- ordinarily served from the session identity map
    # (no new round trip), never a re-query of "the latest prediction"
    # (that would risk picking a *different* row than the one already
    # composed into `enterprise`).
    row = db.get(Prediction, prediction.prediction_id)
    generated_at = _as_utc(row.created_at) if row is not None else None
    if generated_at is not None and generated_at > as_of:
        return PredictiveSignalContext(outcome=PredictiveSignalOutcome.EXCLUDED_GENERATED_AFTER_AS_OF.value, value=None)
    return PredictiveSignalContext(outcome=PredictiveSignalOutcome.AVAILABLE.value, value=prediction)


# --- Knowledge / Evidence ---------------------------------------------------------------------


class KnowledgeEvidenceOutcome(str, Enum):
    # RetrievalResponse.outcome verbatim, plus:
    NOT_QUERIED = "NOT_QUERIED"  # no knowledge_query supplied -- not attempted, not an error
    UNAVAILABLE = "UNAVAILABLE"  # a query was supplied but the retrieval call itself raised


@dataclass
class KnowledgeEvidenceContext:
    outcome: str
    unavailable_reason: str | None
    response: RetrievalResponse | None


def _knowledge_evidence(
    db: Session, *, organization_id: uuid.UUID, knowledge_query: str | None, knowledge_top_k: int | None
) -> KnowledgeEvidenceContext:
    """Reuses `RetrievalService.search()` unchanged -- same tenant
    scoping shape `app/api/v1/retrieval.py` already establishes
    (`allowed_organization_id` is the caller's already-authorized
    organization, never request input taken at face value). Only
    attempted when the caller actually supplies a query: there is no
    free-text question implicit in "give me this site's context", and
    fabricating one (e.g. from indicator labels) would be exactly the
    kind of invented input this milestone's own constraints forbid."""
    if not knowledge_query:
        return KnowledgeEvidenceContext(outcome=KnowledgeEvidenceOutcome.NOT_QUERIED.value, unavailable_reason=None, response=None)
    try:
        response = retrieval_service.search(
            db,
            query_text=knowledge_query,
            allowed_organization_id=organization_id,
            filters=RetrievalFilters(),
            top_k=knowledge_top_k,
        )
    except Exception as exc:  # noqa: BLE001 -- deliberate: isolate this category's failure, never the whole response
        logger.exception("Field Intelligence Context: Knowledge/Evidence retrieval failed")
        return KnowledgeEvidenceContext(outcome=KnowledgeEvidenceOutcome.UNAVAILABLE.value, unavailable_reason=str(exc), response=None)
    return KnowledgeEvidenceContext(outcome=response.outcome.value, unavailable_reason=None, response=response)


# --- Composition -------------------------------------------------------------------------------


@dataclass
class FieldIntelligenceContextResult:
    scope: str  # "organization" | "site"
    organization_id: uuid.UUID
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    generated_at: datetime
    data_sufficiency: str
    event_count: int
    observed: ObservedFactSummary
    deterministic: EnterpriseIntelligenceResult
    predictive: PredictiveSignalContext
    knowledge: KnowledgeEvidenceContext
    provenance: Provenance
    calculation_versions: dict[str, str] = field(default_factory=dict)


def compose_field_intelligence_context(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: str,
    site_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    as_of: datetime | None = None,
    window_days: int | None = None,
    knowledge_query: str | None = None,
    knowledge_top_k: int | None = None,
) -> FieldIntelligenceContextResult:
    """`scope`/`site_id` carry the identical contract
    `compute_enterprise_intelligence()` already documents: for
    `"site"`, `site_id` must already have been verified to belong to
    `organization_id` by the caller (`app/api/v1/intelligence.py::
    _require_owned_site()`) -- this function trusts them exactly as
    every other `app/intelligence/*.py` entry point does.

    `project_id` (SIE Milestone 35A, default `None`) is passed straight
    through to `compute_enterprise_intelligence()` -- see that
    function's own docstring for exactly which parts of `deterministic`
    (and, via `enterprise.event_count`/`evidence_sample_event_ids`,
    `observed`) it genuinely filters, and which it deliberately does
    not."""
    as_of = as_of or utcnow()
    window_days = window_days or settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS

    enterprise = compute_enterprise_intelligence(
        db, organization_id=organization_id, scope=scope, site_id=site_id, project_id=project_id, as_of=as_of,
        window_days=window_days,
    )

    observed = _observed_fact_summary(db, enterprise=enterprise, organization_id=organization_id, as_of=as_of, site_id=site_id)
    predictive = _predictive_signal(db, enterprise=enterprise, as_of=as_of)
    knowledge = _knowledge_evidence(
        db, organization_id=organization_id, knowledge_query=knowledge_query, knowledge_top_k=knowledge_top_k
    )

    calculation_versions = dict(enterprise.provenance.calculation_versions)
    calculation_versions["context_composition"] = FIELD_INTELLIGENCE_CONTEXT_COMPOSITION_VERSION

    return FieldIntelligenceContextResult(
        scope=scope,
        organization_id=organization_id,
        entity_id=site_id,
        as_of=as_of,
        window_days=window_days,
        generated_at=utcnow(),
        data_sufficiency=enterprise.data_sufficiency,
        event_count=enterprise.event_count,
        observed=observed,
        deterministic=enterprise,
        predictive=predictive,
        knowledge=knowledge,
        provenance=enterprise.provenance,
        calculation_versions=calculation_versions,
    )


__all__ = [
    "FIELD_INTELLIGENCE_CONTEXT_COMPOSITION_VERSION",
    "FieldIntelligenceContextResult",
    "ObservedFactOutcome",
    "ObservedFactSummary",
    "ObservedFinding",
    "ObservedAction",
    "PredictiveSignalOutcome",
    "PredictiveSignalContext",
    "KnowledgeEvidenceOutcome",
    "KnowledgeEvidenceContext",
    "compose_field_intelligence_context",
]
