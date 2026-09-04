"""Deterministic enterprise risk score — SIE Milestone 22: Enterprise
Intelligence & Risk Analytics Foundation v0.1, items 9-10.

**This is a transparent, rule-based prioritization score, not a
black-box ML model and not a predicted probability.** Every input is a
plain count or a classification already computed by a sibling,
independently-testable module (`enterprise_indicators.py`,
`enterprise_trend.py`, `recurrence.py`); every weight and reference
constant below is a plain module-level constant, inspectable by reading
this file, never learned from data. Contrast
`app/predictions/predictor.py`, which produces a genuinely
model-fitted, calibration-gated probability from a trained classifier —
that is a *different* number, answering a *different* question, and this
module never combines the two into one opaque figure (see
`app/intelligence/enterprise_intelligence_service.py`'s own docstring:
`deterministic_risk` and `predictive_risk` are always kept as two
separate, separately-labeled fields when both exist).

**No causal claim, ever.** A high score means "several rule-based
indicators of concern are elevated right now" — never "X is causing
elevated risk" (see `app/intelligence/association.py`'s own hard
boundary, which this module inherits in spirit even though it performs
no correlation analysis itself).

**Five documented components**, each already computed by a sibling
module, each independently bounded to `[0, 100]` before weighting:

  * `incident_severity` — `(severity_high_count + severity_critical_count)`
    from the current window's indicators, scaled against
    `settings.ENTERPRISE_RISK_SEVERITY_REFERENCE_COUNT` (documented
    provisional reference: this many severe events in one window is a
    "full" severity score).
  * `incident_frequency` — the current window's `incident_count`, scaled
    against `settings.ENTERPRISE_RISK_FREQUENCY_REFERENCE_COUNT`.
  * `deteriorating_trend` — `enterprise_trend.py`'s own
    IMPROVING/STABLE/DETERIORATING classification and percentage change,
    mapped onto a 0-100 scale: `STABLE` contributes `0` (no added risk
    signal — a quiet, unchanging window must never itself inflate the
    score); `DETERIORATING` scales from just above 50 up to 100 with the
    size of the increase; `IMPROVING` scales down from just below 50
    toward 0 with the size of the decrease.
  * `recurring_patterns` — `recurrence.py`'s own WATCH/RECURRING/
    HIGH_RECURRENCE patterns, each contributing fixed, documented points
    (never omitted for "insufficient data": zero patterns is itself a
    real, valid, fully-computable answer — contributes 0).
  * `leading_lagging_imbalance` — the ratio of lagging activity
    (incidents) to leading activity (near misses + observations +
    inspections) in the current window; a site reporting many incidents
    but almost no proactive leading-indicator activity is a real,
    factual signal this codebase's own canonical data supports.

**A component that cannot be computed (e.g. `deteriorating_trend` when
the trend itself is `INSUFFICIENT_DATA`) is *omitted*, not scored as a
fabricated neutral value** — the remaining, genuinely-computed
components' documented weights are re-normalized to still sum to 100,
so the final score stays on the same `[0, 100]` scale regardless of how
many components were computable. This module never invents a number for
data it does not have (milestone item 13's own instruction, applied here
too, not only to the overall gate below).

**The overall gate (milestone item 13).** No score is computed at all —
`score=None`, `classification=None` — when the window's total event
count is below `settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS` (the same
threshold `app/intelligence/sufficiency.py` already uses to call a
window `INSUFFICIENT_DATA`; reused, not duplicated). "One event
technically permits an arithmetic result" is exactly the case this gate
exists to refuse.

**Classification bands** (milestone item 10, fixed and documented):

    0-24    LOW
    25-49   MODERATE
    50-74   HIGH
    75-100  CRITICAL
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from app.intelligence.enterprise_indicators import EnterpriseIndicator
from app.intelligence.enterprise_trend import EnterpriseTrendResult
from app.intelligence.enums import RecurrenceClassification, RiskClassification
from app.intelligence.recurrence import RecurrencePattern

ENTERPRISE_RISK_SCORE_VERSION = "enterprise-risk-v1"

# --- Component reference constants & weights -------------------------------------
# Documented *provisional* defaults (milestone's own instruction: "not
# scientifically validated"). Kept as plain module constants, mirroring
# `app/predictions/spec.py::ELEVATED_RISK_THRESHOLD` -- these are this
# one versioned formula's own internal parameters, not a generic
# operational knob an env var should override (contrast the
# `settings.ENTERPRISE_*` thresholds in enterprise_trend.py/recurrence.py/
# concentration.py, which genuinely are deployment-tunable).
WEIGHT_SEVERITY = 30.0
WEIGHT_FREQUENCY = 25.0
WEIGHT_TREND = 20.0
WEIGHT_RECURRENCE = 15.0
WEIGHT_IMBALANCE = 10.0

SEVERITY_REFERENCE_COUNT = 5.0
"""This many HIGH/CRITICAL-severity events in one window -> a "full" (100)
incident_severity component score, before weighting."""

FREQUENCY_REFERENCE_COUNT = 10.0
"""This many INCIDENT events in one window -> a "full" (100)
incident_frequency component score, before weighting."""

TREND_NEW_SIGNAL_SCORE = 75.0
"""The deteriorating_trend component's score when the previous period
had zero incidents and the current period has more than zero (a real
percentage change is undefined -- see `enterprise_trend.py`) -- a fixed,
documented "new adverse signal" score rather than an undefined ratio."""

RECURRENCE_POINTS: dict[str, float] = {
    RecurrenceClassification.WATCH.value: 10.0,
    RecurrenceClassification.RECURRING.value: 25.0,
    RecurrenceClassification.HIGH_RECURRENCE.value: 50.0,
}
"""Points contributed per detected pattern, by its own classification --
summed and capped at 100 before weighting."""

IMBALANCE_SCALE = 50.0
"""Multiplier applied to `lagging_total / (leading_total + 1)` (the "+1"
avoids division by zero when there is no leading-indicator activity at
all) to produce the imbalance component's 0-100 score, before capping."""

_SCORE_BANDS: tuple[tuple[float, RiskClassification], ...] = (
    (75.0, RiskClassification.CRITICAL),
    (50.0, RiskClassification.HIGH),
    (25.0, RiskClassification.MODERATE),
    (0.0, RiskClassification.LOW),
)


@dataclass
class RiskScoreComponent:
    key: str
    label: str
    raw_score: float  # this component's own [0, 100] score, before weighting
    weight: float  # this component's documented weight (of 100), before re-normalization
    normalized_weight: float  # weight re-normalized across only the computed components
    contribution: float  # raw_score * (normalized_weight / 100) -- this component's points toward the final score


@dataclass
class RiskScoreResult:
    score: float | None
    classification: str | None  # RiskClassification value, or None when score is None
    version: str = ENTERPRISE_RISK_SCORE_VERSION
    components: list[RiskScoreComponent] = field(default_factory=list)
    insufficient_data_reason: str | None = None


def classify_risk_score(score: float) -> RiskClassification:
    for floor, classification in _SCORE_BANDS:
        if score >= floor:
            return classification
    return RiskClassification.LOW  # pragma: no cover -- unreachable, score is always >= 0


def _severity_component(indicators_by_key: dict[str, EnterpriseIndicator]) -> float | None:
    high = indicators_by_key["severity_high_count"].value
    critical = indicators_by_key["severity_critical_count"].value
    severe_total = high + critical
    return min(severe_total / SEVERITY_REFERENCE_COUNT, 1.0) * 100.0


def _frequency_component(indicators_by_key: dict[str, EnterpriseIndicator]) -> float | None:
    incident_count = indicators_by_key["incident_count"].value
    return min(incident_count / FREQUENCY_REFERENCE_COUNT, 1.0) * 100.0


def _trend_component(trend: EnterpriseTrendResult) -> float | None:
    if trend.classification == "INSUFFICIENT_DATA":
        return None
    if trend.classification == "STABLE":
        # A stable trend adds no risk signal -- 0, not a "neutral" 50.
        # Contrast the pre-Milestone-22 draft of this function (kept only
        # in git history): centering STABLE at 50 meant a window with
        # zero incidents in both periods still contributed points toward
        # the score purely from "nothing changed", which is not a real
        # risk signal and made a genuinely quiet window score above 0.
        return 0.0
    if trend.percentage_change is None:
        # DETERIORATING with an undefined ratio (previous period was
        # zero) -- STABLE-from-zero is already handled above.
        return TREND_NEW_SIGNAL_SCORE
    clamped = max(-100.0, min(100.0, trend.percentage_change))
    if trend.classification == "DETERIORATING":
        # clamped >= settings.ENTERPRISE_TREND_CHANGE_THRESHOLD*100 by
        # construction (that's what made it DETERIORATING) -- score
        # ranges from just above 50 up to 100.
        return 50.0 + clamped / 2.0
    # IMPROVING -- clamped <= -threshold by construction -- score ranges
    # from just below 50 down to 0.
    return max(0.0, 50.0 + clamped / 2.0)


def _recurrence_component(patterns: list[RecurrencePattern]) -> float:
    total = sum(RECURRENCE_POINTS.get(p.classification, 0.0) for p in patterns)
    return min(total, 100.0)


def _imbalance_component(indicators_by_key: dict[str, EnterpriseIndicator]) -> float | None:
    lagging_total = indicators_by_key["incident_count"].value
    leading_total = (
        indicators_by_key["near_miss_count"].value
        + indicators_by_key["observation_count"].value
        + indicators_by_key["inspection_count"].value
    )
    if lagging_total == 0 and leading_total == 0:
        return None
    ratio = lagging_total / (leading_total + 1)
    return min(ratio * IMBALANCE_SCALE, 100.0)


def compute_risk_score(
    *,
    indicators: list[EnterpriseIndicator],
    trend: EnterpriseTrendResult,
    recurrence_patterns: list[RecurrencePattern],
    event_count: int,
) -> RiskScoreResult:
    """Pure function over already-computed sibling results — see module
    docstring for the full component/weighting/gating design."""
    if event_count < settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS:
        return RiskScoreResult(
            score=None,
            classification=None,
            insufficient_data_reason=(
                f"Fewer than {settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS} events in the analysis "
                "window -- a risk score is not computed on this little data (see "
                "app/intelligence/sufficiency.py)."
            ),
        )

    indicators_by_key = {i.key: i for i in indicators}

    raw_components: list[tuple[str, str, float, float]] = []  # key, label, raw_score, weight
    severity = _severity_component(indicators_by_key)
    if severity is not None:
        raw_components.append(("incident_severity", "Incident Severity", severity, WEIGHT_SEVERITY))
    frequency = _frequency_component(indicators_by_key)
    if frequency is not None:
        raw_components.append(("incident_frequency", "Incident Frequency", frequency, WEIGHT_FREQUENCY))
    trend_score = _trend_component(trend)
    if trend_score is not None:
        raw_components.append(("deteriorating_trend", "Trend", trend_score, WEIGHT_TREND))
    raw_components.append(
        ("recurring_patterns", "Recurring Patterns", _recurrence_component(recurrence_patterns), WEIGHT_RECURRENCE)
    )
    imbalance = _imbalance_component(indicators_by_key)
    if imbalance is not None:
        raw_components.append(
            ("leading_lagging_imbalance", "Leading/Lagging Imbalance", imbalance, WEIGHT_IMBALANCE)
        )

    total_weight = sum(w for _, _, _, w in raw_components)
    components: list[RiskScoreComponent] = []
    score = 0.0
    for key, label, raw_score, weight in raw_components:
        normalized_weight = (weight / total_weight) * 100.0
        contribution = raw_score * (normalized_weight / 100.0)
        score += contribution
        components.append(
            RiskScoreComponent(
                key=key,
                label=label,
                raw_score=round(raw_score, 2),
                weight=weight,
                normalized_weight=round(normalized_weight, 2),
                contribution=round(contribution, 2),
            )
        )

    score = round(min(max(score, 0.0), 100.0), 1)
    return RiskScoreResult(score=score, classification=classify_risk_score(score).value, components=components)
