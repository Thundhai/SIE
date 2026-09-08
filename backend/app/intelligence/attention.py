"""Intelligence Attention & Delivery — SIE Milestone 33: the first
attention/delivery layer on top of the Field Intelligence Context
(`app/intelligence/context_composition.py`, SIE Milestone 32). Answers
one question: *"what should a human pay attention to right now, and
why?"*

    compose_field_intelligence_context()  -> Observed + Deterministic + Predictive (M32, unchanged)
        -> a fixed set of category builders, each reading already-computed
           fields off that result (or a small, bounded, existing-table
           read for evidence gaps)
        -> AttentionItem list, deterministically prioritized and sorted
        -> GET /api/v1/intelligence/attention, /sites/{site_id}/attention
           (app/api/v1/intelligence.py)

**This module computes nothing new.** Every attention item is a
*selection and explanation* over a number that already exists,
produced by a function this module calls verbatim via
`compose_field_intelligence_context()`:

* `DETERIORATING_TREND` reads `EnterpriseTrendResult.classification`
  (`app/intelligence/enterprise_trend.py`).
* `SIGNIFICANT_ANOMALY` reads `EnterpriseAnomalyResult.status`/`.direction`
  (`app/intelligence/enterprise_anomaly.py`).
* `RECURRING_PATTERN` reads `RecurrencePattern.classification`
  (`app/intelligence/recurrence.py`).
* `ELEVATED_RISK` reads `RiskScoreResult.classification`/`.score`
  (`app/intelligence/risk_score.py`) -- `enterprise-risk-v1`.
* `PREDICTIVE_RISK` reads the M32 `PredictiveSignalContext` (which
  already applies the staleness rule -- see below).
* `UNRESOLVED_FINDING`/`OVERDUE_ACTIONS` read M32's own Observed
  category (`open_finding_sample`/`open_action_sample`/`actions`) --
  zero new queries.
* `EVIDENCE_GAP` is the one place this module issues its own read: one
  bounded query (`WHERE finding_id IN <=10 ids>`, the same
  `_MAX_FINDING_SAMPLE` cap M32 already established) over
  `RiskAssessmentControl.effectiveness` for the findings already in
  M32's own `open_finding_sample` -- never a query in a loop, never a
  new statistical computation.

No new ML model, no new statistical algorithm, no LLM. Every band a
priority is drawn from is an *existing* classification vocabulary --
see "Prioritization" below.

**Prioritization is a lookup table, not a score.** `AttentionPriority`
*is* `app.intelligence.enums.RiskClassification`
(`LOW`/`MODERATE`/`HIGH`/`CRITICAL`) -- reused verbatim, not a
competing taxonomy. Where a category's own existing classification
already uses that exact vocabulary (`ELEVATED_RISK`'s `RiskClassification`,
`UNRESOLVED_FINDING`'s `RiskAssessmentRiskBand` -- an identical
LOW/MODERATE/HIGH/CRITICAL band set, see
`app/risk_assessment/risk_matrix.py`), the classification is used
directly, unchanged. Where a category's own vocabulary differs
(`EnterpriseTrendClassification`, `AnomalyStatus`, `RecurrenceClassification`,
`RiskCategory`), `_PRIORITY_MAP` below is the one, explicit, documented
translation table -- every mapping traceable to one line, never a
computed/weighted number. `_sort_items()` orders by
`(priority band, fixed category order, title)` -- three fully
inspectable keys, never an opaque composite score.

**Temporal correctness is inherited, not reimplemented.** Every field
this module reads already passed through M32's/M22's own `as_of`
filtering (`events_as_of()`, the `RiskAssessment.approved_at`/
`RiskAssessmentFinding.created_at`/`SafetyAction.created_at <= as_of`
governance filters, and the M32 staleness rule on `Prediction`). This
module adds no new temporal filter of its own except the one bounded
evidence-gap query, which reuses M32's own `open_finding_sample` (already
`as_of`-filtered) as its only input -- it queries controls *for those
findings*, not a fresh, unfiltered sweep.

**Failure isolation.** Each category builder runs inside its own
try/except; a failure building one category is recorded in
`category_statuses` as `UNAVAILABLE` and excluded from `items`, never
propagated to blank the whole response. `compose_field_intelligence_context()`
itself is the one unguarded, atomic call every category depends on
(mirrors M32's/M22's own architecture: there is no per-lens failure
isolation *inside* `compute_enterprise_intelligence()` either -- this
module does not invent a boundary the orchestrator itself does not
have).

**Read-only.** No function in this module calls `db.add()`, `db.flush()`,
or `db.commit()`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.context_composition import (
    FieldIntelligenceContextResult,
    PredictiveSignalOutcome,
    compose_field_intelligence_context,
)
from app.intelligence.enterprise_intelligence_service import _site_labels
from app.intelligence.enums import (
    AnomalyStatus,
    EnterpriseTrendClassification,
    RecurrenceClassification,
    RiskClassification,
)
from app.models.risk_assessment import RiskAssessmentControl
from app.models.risk_assessment_enums import ControlEffectiveness
from app.predictions.enums import RiskCategory

logger = logging.getLogger(__name__)

ATTENTION_COMPOSITION_VERSION = "intelligence-attention-v1"

# Bounded, fixed-size -- never proportional to how many items a category
# could otherwise produce (mirrors context_composition.py's own
# `_MAX_FINDING_SAMPLE`/`_MAX_ACTION_SAMPLE` discipline).
_MAX_EVIDENCE_EVENT_IDS = 5


def _as_utc(value: datetime) -> datetime:
    """Identical to context_composition.py's own `_as_utc()` -- SQLite
    does not round-trip `tzinfo`; every value this codebase writes is
    already UTC, this only restores the label."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class AttentionCategory(str, Enum):
    """Stable, versioned category slugs -- a client filters/groups on
    these, never on `title`/`explanation` free text."""

    DETERIORATING_TREND = "DETERIORATING_TREND"
    SIGNIFICANT_ANOMALY = "SIGNIFICANT_ANOMALY"
    RECURRING_PATTERN = "RECURRING_PATTERN"
    ELEVATED_RISK = "ELEVATED_RISK"
    PREDICTIVE_RISK = "PREDICTIVE_RISK"
    UNRESOLVED_FINDING = "UNRESOLVED_FINDING"
    OVERDUE_ACTIONS = "OVERDUE_ACTIONS"
    EVIDENCE_GAP = "EVIDENCE_GAP"


# Fixed display/tiebreak order -- the spec's own listed order (worsening
# trends, anomalies, recurring patterns, elevated risk, predictive risk,
# unresolved intervention context, evidence gaps). Used only as the
# *second* sort key, after priority band -- see `_sort_items()`.
_CATEGORY_ORDER = [
    AttentionCategory.DETERIORATING_TREND,
    AttentionCategory.SIGNIFICANT_ANOMALY,
    AttentionCategory.RECURRING_PATTERN,
    AttentionCategory.ELEVATED_RISK,
    AttentionCategory.PREDICTIVE_RISK,
    AttentionCategory.UNRESOLVED_FINDING,
    AttentionCategory.OVERDUE_ACTIONS,
    AttentionCategory.EVIDENCE_GAP,
]

# The one, explicit translation table from a category's own existing
# classification vocabulary to the shared, reused AttentionPriority
# vocabulary (RiskClassification: LOW/MODERATE/HIGH/CRITICAL). A
# category whose own vocabulary IS already RiskClassification
# (ELEVATED_RISK, UNRESOLVED_FINDING -- RiskAssessmentRiskBand shares
# the identical value set, see app/risk_assessment/risk_matrix.py) uses
# the classification directly and never appears here. Every mapping is
# one line, independently reviewable -- never a weighted/computed score.
_PRIORITY_MAP: dict[tuple[str, str], str] = {
    (AttentionCategory.DETERIORATING_TREND.value, EnterpriseTrendClassification.DETERIORATING.value): (
        RiskClassification.HIGH.value
    ),
    (AttentionCategory.SIGNIFICANT_ANOMALY.value, AnomalyStatus.ANOMALOUS.value): RiskClassification.HIGH.value,
    (AttentionCategory.RECURRING_PATTERN.value, RecurrenceClassification.WATCH.value): RiskClassification.MODERATE.value,
    (AttentionCategory.RECURRING_PATTERN.value, RecurrenceClassification.RECURRING.value): RiskClassification.HIGH.value,
    (AttentionCategory.RECURRING_PATTERN.value, RecurrenceClassification.HIGH_RECURRENCE.value): (
        RiskClassification.CRITICAL.value
    ),
    (AttentionCategory.PREDICTIVE_RISK.value, RiskCategory.ELEVATED.value): RiskClassification.HIGH.value,
    (AttentionCategory.PREDICTIVE_RISK.value, RiskCategory.MODERATE.value): RiskClassification.MODERATE.value,
}

# A category is worth surfacing as an attention item only above this
# floor -- LOW is, definitionally, "nothing unusual," never an
# attention item (mirrors every existing lens's own "LOW is the
# baseline, not a finding" convention, e.g. RiskClassification.LOW /
# ConcentrationClassification.LOW).
_PRIORITY_RANK = {
    RiskClassification.LOW.value: 0,
    RiskClassification.MODERATE.value: 1,
    RiskClassification.HIGH.value: 2,
    RiskClassification.CRITICAL.value: 3,
}


@dataclass
class AttentionEvidence:
    """What backs this item -- always references to real, already-
    persisted rows, never a copy of their content. Mirrors M32's own
    `evidence_sample_event_ids` pattern, generalized to whichever entity
    type a category's evidence actually is."""

    source: str  # e.g. "enterprise_trend", "enterprise_anomaly", "recurrence", "risk_score", "prediction", "risk_assessment_finding", "safety_action", "risk_assessment_control"
    calculation_version: str | None
    entity_ids: list[uuid.UUID] = field(default_factory=list)
    event_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class AttentionItem:
    category: str  # AttentionCategory
    priority: str  # RiskClassification value -- reused, not a new taxonomy
    title: str
    explanation: str
    scope: str  # "organization" | "site"
    site_id: uuid.UUID | None
    site_label: str | None
    as_of: datetime
    window_days: int
    evidence: AttentionEvidence
    limitation: str | None = None


@dataclass
class AttentionCategoryStatus:
    """Failure isolation and limitation exposure, per category -- always
    present for every category this endpoint knows about, so a caller
    never has to infer "not evaluated" from a category's mere absence
    from `items`."""

    category: str
    status: str  # "EVALUATED" | "UNAVAILABLE" | "NOT_EVALUATED"
    reason: str | None
    item_count: int


@dataclass
class AttentionResult:
    scope: str
    organization_id: uuid.UUID
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    generated_at: datetime
    items: list[AttentionItem]
    category_statuses: list[AttentionCategoryStatus]
    calculation_versions: dict[str, str]


def _sort_key(item: AttentionItem) -> tuple:
    category_index = _CATEGORY_ORDER.index(AttentionCategory(item.category))
    return (-_PRIORITY_RANK[item.priority], category_index, item.title)


def _sort_items(items: list[AttentionItem]) -> list[AttentionItem]:
    return sorted(items, key=_sort_key)


# --- Category builders -------------------------------------------------------------------------
# Each takes the already-composed M32 result (plus, for EVIDENCE_GAP, the
# db session for its own single bounded query) and returns
# `(items, status)`. None of these issue a query in a loop; none
# recompute anything `compose_field_intelligence_context()` already
# computed.


def _scope_kwargs(context: FieldIntelligenceContextResult, site_label: str | None) -> dict:
    return dict(
        scope=context.scope,
        site_id=context.entity_id,
        site_label=site_label,
        as_of=context.as_of,
        window_days=context.window_days,
    )


def _deteriorating_trend_items(
    context: FieldIntelligenceContextResult, *, site_label: str | None
) -> tuple[list[AttentionItem], AttentionCategoryStatus]:
    trend = context.deterministic.trend
    if trend.classification != EnterpriseTrendClassification.DETERIORATING.value:
        return [], AttentionCategoryStatus(
            category=AttentionCategory.DETERIORATING_TREND.value, status="EVALUATED", reason=None, item_count=0
        )
    priority = _PRIORITY_MAP[(AttentionCategory.DETERIORATING_TREND.value, trend.classification)]
    change = (
        f"{trend.percentage_change:+.1f}%" if trend.percentage_change is not None else "an unquantifiable change"
    )
    explanation = (
        f"{trend.metric} rose from {trend.previous_value} to {trend.current_value} "
        f"({change}) between {trend.previous_period_start.date()}–{trend.previous_period_end.date()} "
        f"and {trend.current_period_start.date()}–{trend.current_period_end.date()}."
    )
    item = AttentionItem(
        category=AttentionCategory.DETERIORATING_TREND.value,
        priority=priority,
        title=f"{trend.metric} is deteriorating",
        explanation=explanation,
        evidence=AttentionEvidence(
            source="enterprise_trend",
            calculation_version=trend.calculation_version,
            event_ids=list(context.provenance.evidence_sample_event_ids[:_MAX_EVIDENCE_EVENT_IDS]),
        ),
        **_scope_kwargs(context, site_label),
    )
    return [item], AttentionCategoryStatus(
        category=AttentionCategory.DETERIORATING_TREND.value, status="EVALUATED", reason=None, item_count=1
    )


def _significant_anomaly_items(
    context: FieldIntelligenceContextResult, *, site_label: str | None
) -> tuple[list[AttentionItem], AttentionCategoryStatus]:
    items: list[AttentionItem] = []
    for anomaly in context.deterministic.anomalies:
        if anomaly.status != AnomalyStatus.ANOMALOUS.value:
            continue
        priority = _PRIORITY_MAP[(AttentionCategory.SIGNIFICANT_ANOMALY.value, anomaly.status)]
        direction = "above" if anomaly.direction == "ABOVE_BASELINE" else "below"
        z_note = f" (z={anomaly.z_score:.2f})" if anomaly.z_score is not None else ""
        baseline_text = f"{anomaly.baseline_mean:.1f}" if anomaly.baseline_mean is not None else "unavailable"
        explanation = (
            f"{anomaly.label} is unusually {direction} its baseline: current value "
            f"{anomaly.current_value:.1f} vs. a {anomaly.baseline_period_count}-period baseline mean of "
            f"{baseline_text}{z_note}."
        )
        item = AttentionItem(
            category=AttentionCategory.SIGNIFICANT_ANOMALY.value,
            priority=priority,
            title=f"Anomalous {anomaly.label.lower()}",
            explanation=explanation,
            evidence=AttentionEvidence(
                source="enterprise_anomaly",
                calculation_version=anomaly.calculation_version,
                event_ids=list(anomaly.supporting_event_ids[:_MAX_EVIDENCE_EVENT_IDS]),
            ),
            **_scope_kwargs(context, site_label),
        )
        items.append(item)
    return items, AttentionCategoryStatus(
        category=AttentionCategory.SIGNIFICANT_ANOMALY.value, status="EVALUATED", reason=None, item_count=len(items)
    )


def _recurring_pattern_items(
    context: FieldIntelligenceContextResult, *, site_label: str | None
) -> tuple[list[AttentionItem], AttentionCategoryStatus]:
    items: list[AttentionItem] = []
    for pattern in context.deterministic.patterns:
        key = (AttentionCategory.RECURRING_PATTERN.value, pattern.classification)
        if key not in _PRIORITY_MAP:
            continue  # RecurrenceClassification.NONE -- never actually emitted, defensive only
        priority = _PRIORITY_MAP[key]
        subtype = f"/{pattern.event_subtype}" if pattern.event_subtype else ""
        explanation = (
            f"{pattern.count} {pattern.event_type}{subtype} events recurred at {pattern.site_label} between "
            f"{pattern.first_seen.date()} and {pattern.last_seen.date()} "
            f"(classification: {pattern.classification})."
        )
        item = AttentionItem(
            category=AttentionCategory.RECURRING_PATTERN.value,
            priority=priority,
            title=f"Recurring {pattern.event_type.lower()} at {pattern.site_label}",
            explanation=explanation,
            evidence=AttentionEvidence(
                source="recurrence",
                calculation_version=pattern.calculation_version,
                event_ids=list(pattern.supporting_event_ids[:_MAX_EVIDENCE_EVENT_IDS]),
            ),
            scope=context.scope,
            site_id=pattern.site_id,
            site_label=pattern.site_label,
            as_of=context.as_of,
            window_days=context.window_days,
        )
        items.append(item)
    return items, AttentionCategoryStatus(
        category=AttentionCategory.RECURRING_PATTERN.value, status="EVALUATED", reason=None, item_count=len(items)
    )


def _elevated_risk_items(
    context: FieldIntelligenceContextResult, *, site_label: str | None
) -> tuple[list[AttentionItem], AttentionCategoryStatus]:
    risk = context.deterministic.risk
    if risk.score is None or risk.classification is None:
        return [], AttentionCategoryStatus(
            category=AttentionCategory.ELEVATED_RISK.value,
            status="NOT_EVALUATED",
            reason=risk.insufficient_data_reason or "Deterministic risk score unavailable.",
            item_count=0,
        )
    if _PRIORITY_RANK.get(risk.classification, 0) < _PRIORITY_RANK[RiskClassification.MODERATE.value]:
        return [], AttentionCategoryStatus(
            category=AttentionCategory.ELEVATED_RISK.value, status="EVALUATED", reason=None, item_count=0
        )
    top_components = sorted(risk.components, key=lambda c: c.contribution, reverse=True)[:3]
    driver_text = ", ".join(f"{c.label} ({c.contribution:.1f} pts)" for c in top_components) or "no scored components"
    explanation = (
        f"Deterministic risk score ({risk.version}) is {risk.score:.1f}, classified {risk.classification}. "
        f"Largest contributors: {driver_text}."
    )
    item = AttentionItem(
        category=AttentionCategory.ELEVATED_RISK.value,
        priority=risk.classification,
        title=f"Deterministic risk is {risk.classification.lower()}",
        explanation=explanation,
        evidence=AttentionEvidence(
            source="risk_score",
            calculation_version=risk.version,
            event_ids=list(context.provenance.evidence_sample_event_ids[:_MAX_EVIDENCE_EVENT_IDS]),
        ),
        **_scope_kwargs(context, site_label),
    )
    return [item], AttentionCategoryStatus(
        category=AttentionCategory.ELEVATED_RISK.value, status="EVALUATED", reason=None, item_count=1
    )


def _predictive_risk_items(
    context: FieldIntelligenceContextResult, *, site_label: str | None
) -> tuple[list[AttentionItem], AttentionCategoryStatus]:
    predictive = context.predictive
    if predictive.outcome == PredictiveSignalOutcome.EXCLUDED_GENERATED_AFTER_AS_OF.value:
        return [], AttentionCategoryStatus(
            category=AttentionCategory.PREDICTIVE_RISK.value,
            status="NOT_EVALUATED",
            reason=(
                "A newer prediction exists for this site but was generated after the requested as_of; "
                "excluded to preserve temporal correctness (see SIE_FIELD_INTELLIGENCE_CONTEXT_V0_1.md #10)."
            ),
            item_count=0,
        )
    if predictive.outcome != PredictiveSignalOutcome.AVAILABLE.value or predictive.value is None:
        reason = None if context.scope == "site" else "Predictive signals are site-scoped only."
        return [], AttentionCategoryStatus(
            category=AttentionCategory.PREDICTIVE_RISK.value, status="EVALUATED", reason=reason, item_count=0
        )
    prediction = predictive.value
    key = (AttentionCategory.PREDICTIVE_RISK.value, prediction.risk_category or "")
    if key not in _PRIORITY_MAP:
        return [], AttentionCategoryStatus(
            category=AttentionCategory.PREDICTIVE_RISK.value, status="EVALUATED", reason=None, item_count=0
        )
    priority = _PRIORITY_MAP[key]
    probability_text = f"{prediction.probability:.0%}" if prediction.probability is not None else "uncalibrated"
    limitation = None if prediction.probability is not None else "Model calibration not validated; no probability shown."
    explanation = (
        f"Predictive model {prediction.model_version or 'unversioned'} rates this site's forward risk "
        f"{prediction.risk_category} (probability: {probability_text}) as of prediction time "
        f"{prediction.prediction_time.date()}. This is a model output, not an observed fact."
    )
    item = AttentionItem(
        category=AttentionCategory.PREDICTIVE_RISK.value,
        priority=priority,
        title=f"Predictive risk is {prediction.risk_category.lower()}",
        explanation=explanation,
        evidence=AttentionEvidence(
            source="prediction",
            calculation_version=prediction.model_version,
            entity_ids=[prediction.prediction_id],
        ),
        limitation=limitation,
        **_scope_kwargs(context, site_label),
    )
    return [item], AttentionCategoryStatus(
        category=AttentionCategory.PREDICTIVE_RISK.value, status="EVALUATED", reason=None, item_count=1
    )


def _unresolved_finding_items(
    context: FieldIntelligenceContextResult, *, site_label: str | None, site_labels: dict[uuid.UUID, str]
) -> tuple[list[AttentionItem], AttentionCategoryStatus]:
    observed = context.observed
    if observed.outcome != "OK":
        return [], AttentionCategoryStatus(
            category=AttentionCategory.UNRESOLVED_FINDING.value,
            status="UNAVAILABLE",
            reason=observed.unavailable_reason,
            item_count=0,
        )
    items: list[AttentionItem] = []
    for finding in observed.open_finding_sample:
        classification = finding.residual_risk_classification or finding.inherent_risk_classification
        if classification is None or _PRIORITY_RANK.get(classification, 0) < _PRIORITY_RANK[RiskClassification.HIGH.value]:
            continue
        basis = "residual" if finding.residual_risk_classification else "inherent"
        explanation = (
            f'Open finding "{finding.title}" ({finding.risk_area_label}) carries {basis} risk '
            f"{classification}, status {finding.status}."
        )
        finding_site_label = site_labels.get(finding.site_id) if finding.site_id else None
        item = AttentionItem(
            category=AttentionCategory.UNRESOLVED_FINDING.value,
            priority=classification,
            title=f'Unresolved finding: "{finding.title}"',
            explanation=explanation,
            evidence=AttentionEvidence(
                source="risk_assessment_finding",
                calculation_version=None,
                entity_ids=[finding.finding_id],
            ),
            scope=context.scope,
            site_id=finding.site_id,
            site_label=finding_site_label,
            as_of=context.as_of,
            window_days=context.window_days,
        )
        items.append(item)
    return items, AttentionCategoryStatus(
        category=AttentionCategory.UNRESOLVED_FINDING.value, status="EVALUATED", reason=None, item_count=len(items)
    )


def _overdue_actions_items(
    context: FieldIntelligenceContextResult, *, site_label: str | None
) -> tuple[list[AttentionItem], AttentionCategoryStatus]:
    observed = context.observed
    if observed.outcome != "OK":
        return [], AttentionCategoryStatus(
            category=AttentionCategory.OVERDUE_ACTIONS.value,
            status="UNAVAILABLE",
            reason=observed.unavailable_reason,
            item_count=0,
        )
    actions = observed.actions
    if actions is None or actions.overdue_action_count == 0:
        return [], AttentionCategoryStatus(
            category=AttentionCategory.OVERDUE_ACTIONS.value, status="EVALUATED", reason=None, item_count=0
        )
    # Reuses the already-fetched, already as_of-filtered open_action_sample
    # (M32) -- no new query. `overdue` here means the same thing
    # `_actions_context()`'s own `overdue_action_count` already means
    # (`due_date < as_of` and not yet terminal as of `as_of`); this
    # in-memory filter over the small existing sample identifies *which*
    # of the sampled actions are the overdue ones, for the explanation
    # text -- the count itself is never recomputed.
    overdue_sample = [
        a for a in observed.open_action_sample if a.due_date is not None and _as_utc(a.due_date) < context.as_of
    ]
    priority = RiskClassification.HIGH.value if actions.high_priority_action_count > 0 else RiskClassification.MODERATE.value
    titles = ", ".join(f'"{a.title}"' for a in overdue_sample[:3])
    sample_note = f" Examples: {titles}." if titles else ""
    explanation = (
        f"{actions.overdue_action_count} safety action(s) are overdue as of {context.as_of.date()}, "
        f"including {actions.high_priority_action_count} high/critical-priority action(s).{sample_note}"
    )
    item = AttentionItem(
        category=AttentionCategory.OVERDUE_ACTIONS.value,
        priority=priority,
        title=f"{actions.overdue_action_count} overdue safety action(s)",
        explanation=explanation,
        evidence=AttentionEvidence(
            source="safety_action",
            calculation_version=None,
            entity_ids=[a.action_id for a in overdue_sample[:_MAX_EVIDENCE_EVENT_IDS]],
        ),
        **_scope_kwargs(context, site_label),
    )
    return [item], AttentionCategoryStatus(
        category=AttentionCategory.OVERDUE_ACTIONS.value, status="EVALUATED", reason=None, item_count=1
    )


def _evidence_gap_items(
    db: Session, context: FieldIntelligenceContextResult, *, site_label: str | None, site_labels: dict[uuid.UUID, str]
) -> tuple[list[AttentionItem], AttentionCategoryStatus]:
    observed = context.observed
    if observed.outcome != "OK":
        return [], AttentionCategoryStatus(
            category=AttentionCategory.EVIDENCE_GAP.value,
            status="UNAVAILABLE",
            reason=observed.unavailable_reason,
            item_count=0,
        )
    # Only high/critical-risk findings are worth flagging a gap on --
    # a gap on a LOW/MODERATE finding is not, by itself, an attention
    # item (mirrors ELEVATED_RISK's own MODERATE-and-above floor).
    candidates = [
        f
        for f in observed.open_finding_sample
        if _PRIORITY_RANK.get(f.residual_risk_classification or f.inherent_risk_classification or "", 0)
        >= _PRIORITY_RANK[RiskClassification.HIGH.value]
    ]
    if not candidates:
        return [], AttentionCategoryStatus(
            category=AttentionCategory.EVIDENCE_GAP.value, status="EVALUATED", reason=None, item_count=0
        )
    finding_ids = [f.finding_id for f in candidates]
    rows = db.execute(
        select(RiskAssessmentControl.finding_id, RiskAssessmentControl.effectiveness).where(
            RiskAssessmentControl.finding_id.in_(finding_ids)
        )
    ).all()
    assessed_finding_ids = {
        finding_id for finding_id, effectiveness in rows if effectiveness != ControlEffectiveness.NOT_ASSESSED
    }
    items: list[AttentionItem] = []
    for finding in candidates:
        if finding.finding_id in assessed_finding_ids:
            continue  # at least one control has an actual effectiveness assessment -- not a gap
        classification = finding.residual_risk_classification or finding.inherent_risk_classification
        explanation = (
            f'High-risk finding "{finding.title}" ({finding.risk_area_label}, {classification}) has no '
            f"control-effectiveness assessment on file -- no evidence yet that its mitigations work."
        )
        finding_site_label = site_labels.get(finding.site_id) if finding.site_id else None
        item = AttentionItem(
            category=AttentionCategory.EVIDENCE_GAP.value,
            priority=RiskClassification.MODERATE.value,
            title=f'Evidence gap: "{finding.title}"',
            explanation=explanation,
            evidence=AttentionEvidence(
                source="risk_assessment_control",
                calculation_version=None,
                entity_ids=[finding.finding_id],
            ),
            scope=context.scope,
            site_id=finding.site_id,
            site_label=finding_site_label,
            as_of=context.as_of,
            window_days=context.window_days,
        )
        items.append(item)
    return items, AttentionCategoryStatus(
        category=AttentionCategory.EVIDENCE_GAP.value, status="EVALUATED", reason=None, item_count=len(items)
    )


def _run_category(
    category: AttentionCategory,
    build: Callable[[], tuple[list[AttentionItem], AttentionCategoryStatus]],
    *,
    items: list[AttentionItem],
    category_statuses: list[AttentionCategoryStatus],
) -> None:
    """Runs one category builder inside its own try/except, appending
    its items (on success) and exactly one `AttentionCategoryStatus` --
    the one, uniform failure-isolation boundary every category goes
    through, regardless of how many extra arguments its own builder
    needs (they differ: `_evidence_gap_items` needs `db`,
    `_unresolved_finding_items` needs `site_labels`, etc. -- captured by
    the caller's closure instead of forcing one shared signature on
    every builder)."""
    try:
        built_items, status = build()
    except Exception as exc:  # noqa: BLE001 -- deliberate: isolate this category's failure, never the whole response
        logger.exception("Attention: category %s failed", category.value)
        category_statuses.append(
            AttentionCategoryStatus(category=category.value, status="UNAVAILABLE", reason=str(exc), item_count=0)
        )
        return
    items.extend(built_items)
    category_statuses.append(status)


def compose_attention(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: str,
    site_id: uuid.UUID | None = None,
    as_of: datetime | None = None,
    window_days: int | None = None,
) -> AttentionResult:
    """`scope`/`site_id` carry the identical contract
    `compose_field_intelligence_context()` already documents -- for
    `"site"`, `site_id` must already have been verified to belong to
    `organization_id` by the caller. Site labels (never a raw UUID
    presented as a label) are resolved once, here, via the same
    `_site_labels()` id->name lookup `compute_enterprise_intelligence()`
    already uses internally for concentration/recurrence labels --
    reused, not re-implemented; one query regardless of how many items
    end up needing a label."""
    site_labels = _site_labels(db, organization_id=organization_id)
    site_label = site_labels.get(site_id) if site_id is not None else None
    context = compose_field_intelligence_context(
        db, organization_id=organization_id, scope=scope, site_id=site_id, as_of=as_of, window_days=window_days
    )

    items: list[AttentionItem] = []
    category_statuses: list[AttentionCategoryStatus] = []

    _run_category(
        AttentionCategory.DETERIORATING_TREND,
        lambda: _deteriorating_trend_items(context, site_label=site_label),
        items=items,
        category_statuses=category_statuses,
    )
    _run_category(
        AttentionCategory.SIGNIFICANT_ANOMALY,
        lambda: _significant_anomaly_items(context, site_label=site_label),
        items=items,
        category_statuses=category_statuses,
    )
    _run_category(
        AttentionCategory.RECURRING_PATTERN,
        lambda: _recurring_pattern_items(context, site_label=site_label),
        items=items,
        category_statuses=category_statuses,
    )
    _run_category(
        AttentionCategory.ELEVATED_RISK,
        lambda: _elevated_risk_items(context, site_label=site_label),
        items=items,
        category_statuses=category_statuses,
    )
    _run_category(
        AttentionCategory.PREDICTIVE_RISK,
        lambda: _predictive_risk_items(context, site_label=site_label),
        items=items,
        category_statuses=category_statuses,
    )
    _run_category(
        AttentionCategory.UNRESOLVED_FINDING,
        lambda: _unresolved_finding_items(context, site_label=site_label, site_labels=site_labels),
        items=items,
        category_statuses=category_statuses,
    )
    _run_category(
        AttentionCategory.OVERDUE_ACTIONS,
        lambda: _overdue_actions_items(context, site_label=site_label),
        items=items,
        category_statuses=category_statuses,
    )
    _run_category(
        AttentionCategory.EVIDENCE_GAP,
        lambda: _evidence_gap_items(db, context, site_label=site_label, site_labels=site_labels),
        items=items,
        category_statuses=category_statuses,
    )

    calculation_versions = dict(context.calculation_versions)
    calculation_versions["attention"] = ATTENTION_COMPOSITION_VERSION

    return AttentionResult(
        scope=context.scope,
        organization_id=context.organization_id,
        entity_id=context.entity_id,
        as_of=context.as_of,
        window_days=context.window_days,
        generated_at=context.generated_at,
        items=_sort_items(items),
        category_statuses=category_statuses,
        calculation_versions=calculation_versions,
    )


__all__ = [
    "ATTENTION_COMPOSITION_VERSION",
    "AttentionCategory",
    "AttentionEvidence",
    "AttentionItem",
    "AttentionCategoryStatus",
    "AttentionResult",
    "compose_attention",
]
