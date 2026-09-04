"""Enterprise intelligence orchestrator — SIE Milestone 22: Enterprise
Intelligence & Risk Analytics Foundation v0.1, item 1.

    Safety Events
        -> point-in-time filtering        (app/intelligence/temporal.py::events_as_of() -- reused, unchanged)
        -> aggregation                    (current window + immediately preceding equal-length window)
        -> indicators                     (app/intelligence/enterprise_indicators.py)
        -> trend analysis                 (app/intelligence/enterprise_trend.py)
        -> pattern / recurrence analysis  (app/intelligence/recurrence.py)
        -> risk concentration             (app/intelligence/concentration.py)
        -> deterministic risk scoring     (app/intelligence/risk_score.py)
        -> explanation + provenance       (app/intelligence/explanations.py, this module)
        -> Enterprise Intelligence API    (app/api/v1/intelligence.py)

This module is the one place that touches the database for this
milestone's own computation — every sibling module above is a pure
function over an already-fetched, already-point-in-time-correct event
list (see each module's own docstring). That split mirrors
`app/intelligence/features.py`'s `compute_feature_set()` /
`FeatureEngineeringService` split exactly, for the same reason: the only
place a temporal-leakage or tenant-isolation bug could be introduced is
here, in the query construction, not scattered across five independently
un-auditable modules.

**Not a redesign of retrieval or the existing analytics API.**
`GET .../analytics/summary`, `.../trends`, `.../signals` (item 8's
"existing intelligence routes") are entirely unchanged — this module adds
a new, additive computation on top of the same `events_as_of()` /
`window_bounds()` primitives, never replaces or duplicates their own
feature/signal logic.

**Query strategy (milestone item 22 — avoid N+1).** Exactly four queries
per call, regardless of how many indicators/patterns/contributors are
computed: current-window events, previous-window events, one
organization-wide site id->name lookup, one actions lookup, plus (site
scope only) one latest-prediction lookup. Every downstream computation
(indicators, trend, concentration, recurrence, risk score, explanations)
is a pure function over these already-fetched lists — never a query in a
loop.

**`predictive_context` (item 17).** Populated only from an
*already-recorded* `Prediction` row (the latest one for this site) — this
module never triggers a new prediction, never retrains, and is `None`
whenever no prediction has ever been recorded for that site (including
always, for organization-scope requests: `Prediction.entity_type` is
`"site"` only — see `app/predictions/spec.py::PREDICTION_ENTITY_TYPE`).
`deterministic_risk` (`RiskScoreResult`, this module's own score) and
`predictive_risk` (`PredictiveContext`, the ML model's own calibrated
output) are always two separate, separately-labeled fields — never
combined into one opaque number (see `app/intelligence/risk_score.py`'s
own docstring).

**`actions_context` (item 18).** Purely factual counts from
`SafetyAction` — never a claim like "these actions will reduce risk by
X%", and this module creates no action of its own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.concentration import (
    ENTERPRISE_CONCENTRATION_CALCULATION_VERSION,
    ConcentrationContributor,
    compute_concentration,
)
from app.intelligence.enterprise_indicators import (
    ENTERPRISE_INDICATOR_CALCULATION_VERSION,
    EnterpriseIndicator,
    compute_enterprise_indicators,
)
from app.intelligence.enterprise_trend import (
    ENTERPRISE_TREND_CALCULATION_VERSION,
    EnterpriseTrendResult,
    classify_enterprise_trend,
)
from app.intelligence.explanations import ExplanationItem, generate_explanations
from app.intelligence.recurrence import (
    ENTERPRISE_RECURRENCE_CALCULATION_VERSION,
    RecurrencePattern,
    detect_recurrence,
)
from app.intelligence.risk_score import ENTERPRISE_RISK_SCORE_VERSION, RiskScoreResult, compute_risk_score
from app.intelligence.sufficiency import classify_data_sufficiency
from app.intelligence.temporal import events_as_of, utcnow, window_bounds
from app.models.prediction import Prediction
from app.models.safety_action import SafetyAction
from app.models.safety_action_enums import ACTION_TERMINAL_STATUSES, ActionPriority, ActionStatus
from app.models.site import Site
from app.predictions.spec import PREDICTION_ENTITY_TYPE

_MAX_EVIDENCE_SAMPLE = 25


@dataclass
class ActionsContext:
    open_action_count: int
    overdue_action_count: int
    high_priority_action_count: int


@dataclass
class PredictiveContext:
    prediction_id: uuid.UUID
    prediction_time: datetime
    outcome: str
    risk_score: float | None
    probability: float | None
    risk_category: str | None
    model_version: str | None


@dataclass
class Provenance:
    organization_id: uuid.UUID
    scope: str
    entity_id: uuid.UUID | None
    as_of: datetime
    window_start: datetime
    window_end: datetime
    window_days: int
    generated_at: datetime
    event_count: int
    evidence_sample_event_ids: list[uuid.UUID]
    total_supporting_events: int
    calculation_versions: dict[str, str] = field(default_factory=dict)


@dataclass
class EnterpriseIntelligenceResult:
    scope: str  # "organization" | "site"
    organization_id: uuid.UUID
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    data_sufficiency: str
    event_count: int
    indicators: list[EnterpriseIndicator]
    trend: EnterpriseTrendResult
    patterns: list[RecurrencePattern]
    concentrations: list[ConcentrationContributor]
    risk: RiskScoreResult
    explanations: list[ExplanationItem]
    provenance: Provenance
    predictive_context: PredictiveContext | None = None
    actions_context: ActionsContext | None = None


def _site_labels(db: Session, *, organization_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = db.execute(select(Site.id, Site.name).where(Site.organization_id == organization_id)).all()
    return {site_id: name for site_id, name in rows}


def _actions_context(
    db: Session, *, organization_id: uuid.UUID, as_of: datetime, site_id: uuid.UUID | None
) -> ActionsContext:
    clauses = [SafetyAction.organization_id == organization_id]
    if site_id is not None:
        clauses.append(SafetyAction.site_id == site_id)
    rows = db.execute(
        select(SafetyAction.status, SafetyAction.priority, SafetyAction.due_date).where(*clauses)
    ).all()
    open_count = sum(1 for status, _, _ in rows if status == ActionStatus.OPEN)
    overdue_count = sum(
        1
        for status, _, due_date in rows
        if status not in ACTION_TERMINAL_STATUSES and due_date is not None and due_date < as_of
    )
    high_priority_count = sum(
        1
        for status, priority, _ in rows
        if status not in ACTION_TERMINAL_STATUSES and priority in (ActionPriority.HIGH, ActionPriority.CRITICAL)
    )
    return ActionsContext(
        open_action_count=open_count,
        overdue_action_count=overdue_count,
        high_priority_action_count=high_priority_count,
    )


def _predictive_context(db: Session, *, organization_id: uuid.UUID, site_id: uuid.UUID | None) -> PredictiveContext | None:
    if site_id is None:
        return None  # organization scope -- Prediction.entity_type is "site" only, never fabricated
    prediction = db.execute(
        select(Prediction)
        .where(
            Prediction.organization_id == organization_id,
            Prediction.entity_type == PREDICTION_ENTITY_TYPE,
            Prediction.entity_id == site_id,
        )
        .order_by(Prediction.prediction_time.desc(), Prediction.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if prediction is None:
        return None
    return PredictiveContext(
        prediction_id=prediction.id,
        prediction_time=prediction.prediction_time,
        outcome=prediction.outcome,
        risk_score=prediction.risk_score,
        probability=prediction.probability,
        risk_category=prediction.risk_category,
        model_version=prediction.model_version,
    )


def compute_enterprise_intelligence(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: str,
    site_id: uuid.UUID | None = None,
    as_of: datetime | None = None,
    window_days: int | None = None,
) -> EnterpriseIntelligenceResult:
    """`scope` is `"organization"` or `"site"`; for `"site"`, `site_id`
    must already have been verified to belong to `organization_id` by the
    caller (see `app/api/v1/intelligence.py::_require_owned_site()`,
    mirroring `app/api/v1/predictions.py`'s own established pattern) --
    this function trusts `organization_id`/`site_id` exactly as every
    other `app/intelligence/*.py` entry point already does."""
    as_of = as_of or utcnow()
    window_days = window_days or settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS
    window_start, _ = window_bounds(as_of, window_days)
    previous_start, previous_end = window_bounds(window_start, window_days)

    current_events = list(
        db.execute(
            events_as_of(organization_id=organization_id, as_of=as_of, window_start=window_start, site_id=site_id)
        )
        .scalars()
        .all()
    )
    previous_events = list(
        db.execute(
            events_as_of(
                organization_id=organization_id, as_of=previous_end, window_start=previous_start, site_id=site_id
            )
        )
        .scalars()
        .all()
    )

    event_count = len(current_events)
    data_sufficiency = classify_data_sufficiency(event_count).value

    indicators = compute_enterprise_indicators(
        current_events, previous_events, window_start=window_start, as_of=as_of, window_days=window_days
    )
    indicators_by_key = {i.key: i for i in indicators}

    trend = classify_enterprise_trend(
        current_events,
        previous_events,
        window_start=window_start,
        as_of=as_of,
        previous_period_start=previous_start,
        previous_period_end=previous_end,
    )

    site_labels = _site_labels(db, organization_id=organization_id)
    concentrations = compute_concentration(current_events, scope=scope, site_labels=site_labels)
    patterns = detect_recurrence(
        current_events, window_start=window_start, window_end=as_of, window_days=window_days, site_labels=site_labels
    )

    risk = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=patterns, event_count=event_count)
    explanations = generate_explanations(
        risk=risk,
        trend=trend,
        recurrence_patterns=patterns,
        concentration_contributors=concentrations,
        indicators_by_key=indicators_by_key,
    )

    provenance = Provenance(
        organization_id=organization_id,
        scope=scope,
        entity_id=site_id,
        as_of=as_of,
        window_start=window_start,
        window_end=as_of,
        window_days=window_days,
        generated_at=utcnow(),
        event_count=event_count,
        evidence_sample_event_ids=[e.id for e in current_events[:_MAX_EVIDENCE_SAMPLE]],
        total_supporting_events=event_count,
        calculation_versions={
            "indicators": ENTERPRISE_INDICATOR_CALCULATION_VERSION,
            "trend": ENTERPRISE_TREND_CALCULATION_VERSION,
            "recurrence": ENTERPRISE_RECURRENCE_CALCULATION_VERSION,
            "concentration": ENTERPRISE_CONCENTRATION_CALCULATION_VERSION,
            "risk_score": ENTERPRISE_RISK_SCORE_VERSION,
        },
    )

    return EnterpriseIntelligenceResult(
        scope=scope,
        organization_id=organization_id,
        entity_id=site_id,
        as_of=as_of,
        window_days=window_days,
        data_sufficiency=data_sufficiency,
        event_count=event_count,
        indicators=indicators,
        trend=trend,
        patterns=patterns,
        concentrations=concentrations,
        risk=risk,
        explanations=explanations,
        provenance=provenance,
        predictive_context=_predictive_context(db, organization_id=organization_id, site_id=site_id),
        actions_context=_actions_context(db, organization_id=organization_id, as_of=as_of, site_id=site_id),
    )
