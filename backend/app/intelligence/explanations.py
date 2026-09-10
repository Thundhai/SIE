"""Structured, deterministic explanation generation — SIE Milestone 22:
Enterprise Intelligence & Risk Analytics Foundation v0.1, item 11.

**Not LLM-generated narrative.** Every `ExplanationItem` here is produced
by substituting already-computed numbers into a fixed Python string
template — there is no free-form generation step, nothing an LLM wrote,
nothing that could hallucinate a factor this milestone's own modules
never actually computed. Every item's `evidence_reference` points back to
the exact computed object (a risk-score component key, a trend metric
name, a recurrence pattern key, a concentration dimension/key pair) that
produced it — an auditor can always trace an explanation sentence back to
the arithmetic behind it.

**No causal language.** Every template describes *what changed* or *what
was observed*, never *why* — "Incident count changed from 2 to 5" is
permitted; "poor supervision caused the increase" is not, and this module
has no vocabulary capable of producing the latter (see
`app/intelligence/association.py`'s own hard causal boundary, which this
module's design deliberately mirrors).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.intelligence.concentration import ConcentrationContributor
from app.intelligence.enterprise_anomaly import EnterpriseAnomalyResult
from app.intelligence.enterprise_association import EnterpriseAssociationResult
from app.intelligence.enterprise_indicators import EnterpriseIndicator
from app.intelligence.enterprise_trend import EnterpriseTrendResult
from app.intelligence.recurrence import RecurrencePattern
from app.intelligence.risk_score import RiskScoreResult

_MAX_RECURRENCE_EXPLANATIONS = 5
_MAX_CONCENTRATION_EXPLANATIONS = 5
_MAX_ASSOCIATION_EXPLANATIONS = 5
_NOTABLE_ASSOCIATION_CLASSIFICATIONS = (
    "STRONG_POSITIVE",
    "MODERATE_POSITIVE",
    "MODERATE_NEGATIVE",
    "STRONG_NEGATIVE",
)


@dataclass
class ExplanationItem:
    code: str
    message: str
    value: float | int | None = None
    baseline: float | int | None = None
    contribution: float | None = None
    evidence_reference: str = ""


def _risk_component_explanations(risk: RiskScoreResult, indicators_by_key: dict[str, EnterpriseIndicator]) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []
    for component in risk.components:
        if component.contribution <= 0:
            continue
        if component.key == "incident_severity":
            severe = indicators_by_key["severity_high_count"].value + indicators_by_key["severity_critical_count"].value
            message = f"{severe} severe (HIGH/CRITICAL severity) event(s) were recorded in the current period."
            value, baseline = severe, None
        elif component.key == "incident_frequency":
            incident = indicators_by_key["incident_count"]
            message = f"{incident.value} incident(s) were recorded in the current period."
            value, baseline = incident.value, incident.previous_value
        elif component.key == "leading_lagging_imbalance":
            incident = indicators_by_key["incident_count"].value
            leading = (
                indicators_by_key["near_miss_count"].value
                + indicators_by_key["observation_count"].value
                + indicators_by_key["inspection_count"].value
            )
            message = (
                f"{incident} incident(s) were recorded against only {leading} leading-indicator "
                "activities (near misses, observations, inspections) in the current period."
            )
            value, baseline = incident, leading
        else:
            continue
        items.append(
            ExplanationItem(
                code=component.key.upper(),
                message=message,
                value=value,
                baseline=baseline,
                contribution=component.contribution,
                evidence_reference=f"indicator:{component.key.replace('incident_', '') if component.key != 'incident_severity' else 'severity_high_count+severity_critical_count'}",
            )
        )
    return items


def _trend_explanation(trend: EnterpriseTrendResult, risk: RiskScoreResult) -> ExplanationItem | None:
    if trend.classification == "INSUFFICIENT_DATA":
        return None
    trend_component = next((c for c in risk.components if c.key == "deteriorating_trend"), None)
    if trend.percentage_change is not None:
        sign = "+" if trend.percentage_change >= 0 else ""
        message = (
            f"Incident count changed from {trend.previous_value} to {trend.current_value} "
            f"({sign}{trend.percentage_change}%) over the current {(trend.current_period_end - trend.current_period_start).days}-day "
            f"period compared with the previous equal-length period."
        )
    else:
        message = (
            f"Incident count changed from {trend.previous_value} to {trend.current_value} over the "
            f"current {(trend.current_period_end - trend.current_period_start).days}-day period compared "
            "with the previous equal-length period."
        )
    return ExplanationItem(
        code=f"TREND_{trend.classification}",
        message=message,
        value=trend.current_value,
        baseline=trend.previous_value,
        contribution=trend_component.contribution if trend_component else None,
        evidence_reference="trend:incident_count",
    )


def _recurrence_explanations(patterns: list[RecurrencePattern]) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []
    for pattern in patterns[:_MAX_RECURRENCE_EXPLANATIONS]:
        if pattern.classification == "NONE":
            continue
        subject = pattern.event_subtype or pattern.event_type
        message = (
            f"{subject} recurred {pattern.count} times at {pattern.site_label} between "
            f"{pattern.first_seen.date().isoformat()} and {pattern.last_seen.date().isoformat()} "
            f"({pattern.classification})."
        )
        items.append(
            ExplanationItem(
                code=f"RECURRING_PATTERN_{pattern.classification}",
                message=message,
                value=pattern.count,
                baseline=None,
                contribution=None,
                evidence_reference=pattern.pattern_key,
            )
        )
    return items


def _concentration_explanations(contributors: list[ConcentrationContributor]) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []
    notable = [c for c in contributors if c.classification in ("HIGH", "MODERATE")]
    for contributor in notable[:_MAX_CONCENTRATION_EXPLANATIONS]:
        message = (
            f"{contributor.label} accounts for {round(contributor.percentage * 100)}% of {contributor.dimension} "
            f"activity ({contributor.count} of {contributor.total}) -- risk contribution: {contributor.classification}."
        )
        items.append(
            ExplanationItem(
                code=f"CONCENTRATION_{contributor.dimension.upper()}_{contributor.classification}",
                message=message,
                value=contributor.count,
                baseline=contributor.total,
                contribution=None,
                evidence_reference=f"{contributor.dimension}:{contributor.key}",
            )
        )
    return items


def _anomaly_explanation(anomaly: EnterpriseAnomalyResult) -> ExplanationItem | None:
    """SIE Milestone 23: Enterprise Intelligence Explainability & Anomaly
    Foundation v0.1, item 10. Only `ANOMALOUS` metrics get an
    explanation sentence (mirrors this module's own established
    convention — `_concentration_explanations()` above only explains
    `HIGH`/`MODERATE` contributors, never every dimension). Every number
    in the message is read directly off `anomaly` — nothing generated,
    nothing causal (milestone item 9's own worked example: "Incident
    count was 8 this period versus a historical baseline mean of 2.4"
    is permitted; "poor supervision caused the spike" is not, and this
    function has no vocabulary capable of producing it)."""
    if anomaly.status != "ANOMALOUS" or anomaly.baseline_mean is None:
        return None
    difference = anomaly.current_value - anomaly.baseline_mean
    sign = "+" if difference >= 0 else ""
    if anomaly.z_score is not None:
        message = (
            f"{anomaly.label} was {anomaly.current_value:g} this period versus a historical baseline mean of "
            f"{anomaly.baseline_mean:g} ({sign}{difference:g}, z={anomaly.z_score:g}) -- {anomaly.direction}."
        )
    else:
        # Zero-variance baseline (app/intelligence/anomaly.py's own
        # documented "z-score is undefined, not fabricated" case).
        message = (
            f"{anomaly.label} was {anomaly.current_value:g} this period versus a constant historical baseline of "
            f"{anomaly.baseline_mean:g} ({sign}{difference:g}) -- {anomaly.direction}."
        )
    return ExplanationItem(
        code=f"ANOMALY_{anomaly.metric.upper()}_{anomaly.direction}",
        message=message,
        value=anomaly.current_value,
        baseline=anomaly.baseline_mean,
        contribution=None,
        evidence_reference=f"anomaly:{anomaly.metric}",
    )


def _anomaly_explanations(anomalies: list[EnterpriseAnomalyResult]) -> list[ExplanationItem]:
    items = [_anomaly_explanation(a) for a in anomalies]
    return [item for item in items if item is not None]


_ASSOCIATION_STRENGTH_WORDS = {
    "STRONG_POSITIVE": "strong positive",
    "MODERATE_POSITIVE": "moderate positive",
    "MODERATE_NEGATIVE": "moderate negative",
    "STRONG_NEGATIVE": "strong negative",
}


def _association_explanation(association: EnterpriseAssociationResult) -> ExplanationItem | None:
    """SIE Milestone 24: Enterprise Intelligence Pattern & Correlation
    Foundation v0.1, item 10. Only notable (non-`WEAK`, non-
    `INSUFFICIENT_DATA`) pairs get an explanation sentence -- mirrors this
    module's own established convention (`_concentration_explanations()`
    above only explains `HIGH`/`MODERATE` contributors, never every
    dimension). Every number is read directly off `association` --
    nothing generated, and never a causal claim (milestone item 10's own
    worked example: "Incident count and near-miss count showed a strong
    positive association across 6 historical periods (r=0.91)" is
    permitted; "near misses caused the increase in incidents" is not, and
    this function has no vocabulary capable of producing it)."""
    if association.classification not in _NOTABLE_ASSOCIATION_CLASSIFICATIONS:
        return None
    if association.correlation_coefficient is None:
        return None
    strength = _ASSOCIATION_STRENGTH_WORDS[association.classification]
    message = (
        f"{association.label_a} and {association.label_b} showed a {strength} association across "
        f"{association.period_count} historical periods (r={association.correlation_coefficient:g})."
    )
    return ExplanationItem(
        code=f"ASSOCIATION_{association.metric_a.upper()}_{association.metric_b.upper()}_{association.classification}",
        message=message,
        value=association.correlation_coefficient,
        baseline=None,
        contribution=None,
        evidence_reference=f"association:{association.metric_a}:{association.metric_b}",
    )


def _association_explanations(associations: list[EnterpriseAssociationResult]) -> list[ExplanationItem]:
    """Unlike `_recurrence_explanations()`/`_concentration_explanations()`
    (whose inputs already arrive ranked by strength/count), `associations`
    is in a fixed, deterministic metric-pair declaration order, not
    sorted by strength (item 14's own "reconstructable" requirement) --
    so this filters for notable classifications *first*, then bounds the
    result to `_MAX_ASSOCIATION_EXPLANATIONS`, rather than slicing the
    fixed-order input before filtering (which could arbitrarily drop a
    genuinely notable pair that happens to sort late)."""
    items = [_association_explanation(a) for a in associations]
    return [item for item in items if item is not None][:_MAX_ASSOCIATION_EXPLANATIONS]


def generate_explanations(
    *,
    risk: RiskScoreResult,
    trend: EnterpriseTrendResult,
    recurrence_patterns: list[RecurrencePattern],
    concentration_contributors: list[ConcentrationContributor],
    indicators_by_key: dict[str, EnterpriseIndicator],
    anomalies: list[EnterpriseAnomalyResult] | None = None,
    associations: list[EnterpriseAssociationResult] | None = None,
) -> list[ExplanationItem]:
    """Pure function over already-computed sibling results. Order:
    risk-score component drivers first (each maps 1:1 to a component that
    actually contributed points), then the trend explanation, then
    recurrence patterns, then notable concentration contributors, then
    anomalous metrics (SIE Milestone 23), then notable cross-metric
    associations (SIE Milestone 24) -- the same order a human reviewer
    would want to read them in (score drivers, then supporting context,
    then statistically unusual signals, then co-movement across metrics)."""
    items: list[ExplanationItem] = []
    items.extend(_risk_component_explanations(risk, indicators_by_key))
    trend_item = _trend_explanation(trend, risk)
    if trend_item is not None:
        items.append(trend_item)
    items.extend(_recurrence_explanations(recurrence_patterns))
    items.extend(_concentration_explanations(concentration_contributors))
    items.extend(_anomaly_explanations(anomalies or []))
    items.extend(_association_explanations(associations or []))
    return items
