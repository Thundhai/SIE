"""Enterprise intelligence orchestrator — SIE Milestone 22: Enterprise
Intelligence & Risk Analytics Foundation v0.1, item 1.

    Safety Events
        -> point-in-time filtering        (app/intelligence/temporal.py::events_as_of() -- reused, unchanged)
        -> aggregation                    (current window + immediately preceding equal-length window)
        -> indicators                     (app/intelligence/enterprise_indicators.py)
        -> trend analysis                 (app/intelligence/enterprise_trend.py)
        -> pattern / recurrence analysis  (app/intelligence/recurrence.py)
        -> risk concentration             (app/intelligence/concentration.py)
        -> anomaly detection              (app/intelligence/enterprise_anomaly.py -- SIE Milestone 23)
        -> cross-metric association       (app/intelligence/enterprise_association.py -- SIE Milestone 24)
        -> deterministic risk scoring     (app/intelligence/risk_score.py)
        -> explanation + provenance       (app/intelligence/explanations.py, this module)
        -> Enterprise Intelligence API    (app/api/v1/intelligence.py)

**`anomalies` (SIE Milestone 23: Enterprise Intelligence Explainability
& Anomaly Foundation v0.1, item 11).** A separate intelligence
dimension, sibling to `deterministic_risk`/`predictive_context` — never
folded into `enterprise-risk-v1`'s score or components
(`app/intelligence/risk_score.py` is untouched by Milestone 23).
Something can be statistically unusual without representing elevated
safety risk, and this codebase never conflates the two.

**`associations` (SIE Milestone 24: Enterprise Intelligence Pattern &
Correlation Foundation v0.1, item 8).** Another separate intelligence
dimension, sibling to `anomalies`/`patterns` — also never folded into
`enterprise-risk-v1` (untouched by Milestone 24 too, exactly as
Milestone 23 left it). Association ≠ risk, the same way anomaly ≠ risk:
a strong correlation between two metrics is a statistical observation
about co-movement, never an automatic risk-score adjustment and never a
causal claim (see `app/intelligence/association.py`'s own hard causal
boundary).

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
loop. Anomaly detection (Milestone 23) adds one more shared query (the
earliest-event lookup — see
`app/intelligence/enterprise_anomaly.py::_available_baseline_periods()`)
plus, only when enough history exists, one bounded `bucketed_counts()`
sweep per supported metric (seven, a fixed constant — never proportional
to event volume) — reusing `current_events` for every metric's current-
period side, so this never re-queries the current window. Cross-metric
association (Milestone 24) adds one more shared earliest-event query
(`app/intelligence/enterprise_association.py::_available_periods()`)
plus, only when enough history exists, one query *per period* (not per
metric or per pair) fetching every event in that period — every one of
the 21 supported metric pairs then derives its two series from that same
already-fetched, per-period event list in memory.

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
X%", and this module creates no action of its own. Point-in-time
filtered (Milestone 22A item 3 — `created_at <= as_of`, see
`_actions_context()`), and `overdue_action_count` uses each action's own
`completed_at`/`cancelled_at` transition timestamp rather than its
current, always-mutable `status` to decide whether it was still open as
of `as_of` (Milestone 22A item 5 — see `_terminal_as_of()`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.concentration import (
    ENTERPRISE_CONCENTRATION_CALCULATION_VERSION,
    ConcentrationContributor,
    compute_concentration,
)
from app.intelligence.anomaly import ANOMALY_CALCULATION_VERSION
from app.intelligence.enterprise_anomaly import EnterpriseAnomalyResult, compute_enterprise_anomalies
from app.intelligence.association import ASSOCIATION_CALCULATION_VERSION
from app.intelligence.enterprise_association import EnterpriseAssociationResult, compute_enterprise_associations
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


def _as_utc(value: datetime) -> datetime:
    """Normalize a possibly offset-naive `datetime` (SQLite does not
    round-trip `tzinfo` the way PostgreSQL does, even through a
    `DateTime(timezone=True)` column) to UTC-aware, so it can be safely
    compared in Python against an always-aware `as_of`/`window_start`.
    Every value this codebase ever writes to a timestamp column is
    already UTC (`app.models.base.utcnow`) — this never reinterprets a
    naive value in the wrong zone, only restores the label SQLite
    dropped. Mirrors the identical, already-established pattern in
    `app/intelligence/reliability.py::_as_utc()`,
    `app/services/api_client_service.py`, `app/predictions/predictor.py`,
    and others."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


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
    anomalies: list[EnterpriseAnomalyResult]
    associations: list[EnterpriseAssociationResult]
    risk: RiskScoreResult
    explanations: list[ExplanationItem]
    provenance: Provenance
    predictive_context: PredictiveContext | None = None
    actions_context: ActionsContext | None = None


def _site_labels(db: Session, *, organization_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = db.execute(select(Site.id, Site.name).where(Site.organization_id == organization_id)).all()
    return {site_id: name for site_id, name in rows}


def _terminal_as_of(as_of: datetime, completed_at: datetime | None, cancelled_at: datetime | None) -> bool:
    """Whether a `SafetyAction` had already reached a terminal state
    (`COMPLETED`/`CANCELLED`) *as of* `as_of` — Milestone 22A item 5.
    Uses `completed_at`/`cancelled_at`, which the service layer only
    ever sets once, at the moment of that specific transition (see
    `app/models/safety_action.py`'s own "Closure semantics" docstring),
    never the current, always-mutable `status` column: `status` answers
    "what is this action's state right now", which is the wrong
    question for a historical `as_of` — an action completed yesterday
    was still open as of last week, but its `status` column has no
    memory of that. `completed_at <= as_of` / `cancelled_at <= as_of`
    answers the question this milestone actually asks correctly, using
    only fields already on the row (no `SafetyActionHistory` replay —
    that would be a genuine redesign of this computation, not the
    focused correction this milestone is)."""
    if completed_at is not None and _as_utc(completed_at) <= as_of:
        return True
    if cancelled_at is not None and _as_utc(cancelled_at) <= as_of:
        return True
    return False


def _actions_context(
    db: Session, *, organization_id: uuid.UUID, as_of: datetime, site_id: uuid.UUID | None
) -> ActionsContext:
    """Milestone 22A item 3: `created_at <= as_of` excludes any action
    that did not yet exist as of the requested `as_of` — a historical
    `GET .../enterprise?as_of=<a past date>` call must never surface an
    action created afterward (see
    `tests/test_enterprise_intelligence_service.py`'s regression test).
    `open_action_count`/`high_priority_action_count` keep their original
    "current `status`" definition (never flagged as incorrect — only
    `overdue_action_count`'s reliance on `status` was, see
    `_terminal_as_of()` above); both are still explicitly point-in-time
    filtered by `created_at <= as_of` here.
    """
    clauses = [
        SafetyAction.organization_id == organization_id,
        SafetyAction.created_at <= as_of,
    ]
    if site_id is not None:
        clauses.append(SafetyAction.site_id == site_id)
    rows = db.execute(
        select(
            SafetyAction.status,
            SafetyAction.priority,
            SafetyAction.due_date,
            SafetyAction.completed_at,
            SafetyAction.cancelled_at,
        ).where(*clauses)
    ).all()
    open_count = sum(1 for status, _, _, _, _ in rows if status == ActionStatus.OPEN)
    high_priority_count = sum(
        1
        for status, priority, _, _, _ in rows
        if status not in ACTION_TERMINAL_STATUSES and priority in (ActionPriority.HIGH, ActionPriority.CRITICAL)
    )
    overdue_count = sum(
        1
        for _, _, due_date, completed_at, cancelled_at in rows
        if due_date is not None
        and _as_utc(due_date) < as_of
        and not _terminal_as_of(as_of, completed_at, cancelled_at)
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
    project_id: uuid.UUID | None = None,
    as_of: datetime | None = None,
    window_days: int | None = None,
) -> EnterpriseIntelligenceResult:
    """`scope` is `"organization"` or `"site"`; for `"site"`, `site_id`
    must already have been verified to belong to `organization_id` by the
    caller (see `app/api/v1/intelligence.py::_require_owned_site()`,
    mirroring `app/api/v1/predictions.py`'s own established pattern) --
    this function trusts `organization_id`/`site_id` exactly as every
    other `app/intelligence/*.py` entry point already does.

    `project_id` (SIE Milestone 35A, default `None` -- every existing
    caller's behavior is completely unaffected) genuinely filters
    `event_count`/`indicators`/`trend`/`concentrations`/`patterns`/
    `risk`/`explanations`/`data_sufficiency` to `SafetyEvent` rows
    explicitly attributed to that project (`events_as_of(project_id=...)`
    -- see that function's own docstring). It is deliberately NOT
    threaded into `compute_enterprise_anomalies()`/
    `compute_enterprise_associations()` (each runs its own, separate
    multi-period baseline queries -- wiring project filtering through
    those too is a materially larger change than this correction's own
    narrow scope) nor into `_actions_context()`/`_predictive_context()`
    (`SafetyAction` carries no project attribution in this correction,
    and `Prediction` has no project dimension at all -- see
    `app/models/project.py`'s own docstring for why). Callers that
    surface this result to a caller-facing response must label which
    parts were actually project-filtered -- never imply project scope
    for anomalies/associations/actions/predictive when it wasn't
    applied (see `app/schemas/field_intelligence_context.py`'s own
    `OperationalScopeProjectRead.filtered` field for the one place this
    codebase does that)."""
    as_of = as_of or utcnow()
    window_days = window_days or settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS
    window_start, _ = window_bounds(as_of, window_days)
    previous_start, previous_end = window_bounds(window_start, window_days)

    previous_events = list(
        db.execute(
            events_as_of(
                organization_id=organization_id, as_of=previous_end, window_start=previous_start, site_id=site_id,
                project_id=project_id,
            )
        )
        .scalars()
        .all()
    )
    # Milestone 22A correction: events_as_of()'s window_start filter is
    # `>=` (shared, unchanged -- see app/intelligence/temporal.py; every
    # other caller in this codebase relies on that inclusive lower
    # bound, so it is never touched here). Fetched the same way, the
    # current window's `window_start >= window_start` and the previous
    # window's own `as_of <= window_start` overlap at exactly
    # `event_time == window_start`, double-counting that one instant in
    # both periods. The two windows are defined as non-overlapping,
    # contiguous, adjacent periods -- current: `(window_start, as_of]`,
    # previous: `(previous_start, window_start]` -- so the previous
    # period's own inclusive upper bound is the single source of truth
    # for that boundary instant; it is explicitly excluded from the
    # current period here, never dropped from previous. This is a
    # scoped filter local to this one current/previous comparison, not
    # a change to events_as_of()'s own shared, reused semantics.
    current_events = [
        e
        for e in db.execute(
            events_as_of(
                organization_id=organization_id, as_of=as_of, window_start=window_start, site_id=site_id,
                project_id=project_id,
            )
        )
        .scalars()
        .all()
        if _as_utc(e.event_time) > window_start
    ]

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
    anomalies = compute_enterprise_anomalies(
        db,
        organization_id=organization_id,
        site_id=site_id,
        current_events=current_events,
        as_of=as_of,
        window_start=window_start,
        window_days=window_days,
    )
    associations = compute_enterprise_associations(
        db,
        organization_id=organization_id,
        site_id=site_id,
        as_of=as_of,
        window_days=window_days,
    )

    risk = compute_risk_score(indicators=indicators, trend=trend, recurrence_patterns=patterns, event_count=event_count)
    explanations = generate_explanations(
        risk=risk,
        trend=trend,
        recurrence_patterns=patterns,
        concentration_contributors=concentrations,
        indicators_by_key=indicators_by_key,
        anomalies=anomalies,
        associations=associations,
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
            "anomaly": ANOMALY_CALCULATION_VERSION,
            "association": ASSOCIATION_CALCULATION_VERSION,
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
        anomalies=anomalies,
        associations=associations,
        risk=risk,
        explanations=explanations,
        provenance=provenance,
        predictive_context=_predictive_context(db, organization_id=organization_id, site_id=site_id),
        actions_context=_actions_context(db, organization_id=organization_id, as_of=as_of, site_id=site_id),
    )
