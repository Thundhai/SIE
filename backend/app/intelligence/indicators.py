"""Leading and lagging indicators — milestone item 21. A thin,
labeling-only layer over `app/intelligence/features.py`'s `FeatureValue`
output: every indicator *is* a feature, categorized as one that measures
outcomes already realized (`LAGGING`) or one that measures activity
believed to precede outcomes (`LEADING`) — never presented as a
predictive probability (milestone item 21's own instruction).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.intelligence.enums import IndicatorCategory
from app.intelligence.features import FeatureValue

LAGGING_INDICATOR_NAMES: tuple[str, ...] = (
    "incident_count",
    "severe_event_count",
    "incidents_per_100000_hours",
)

LEADING_INDICATOR_NAMES: tuple[str, ...] = (
    "near_miss_count",
    "observation_count",
    "overdue_action_count",
    "inspection_count",
    "training_completion_rate",
)


@dataclass
class IndicatorValue:
    name: str
    category: str  # IndicatorCategory value
    feature: FeatureValue


def compute_indicators(features: dict[str, FeatureValue]) -> list[IndicatorValue]:
    indicators: list[IndicatorValue] = []
    for name in LAGGING_INDICATOR_NAMES:
        if name in features:
            indicators.append(IndicatorValue(name=name, category=IndicatorCategory.LAGGING.value, feature=features[name]))
    for name in LEADING_INDICATOR_NAMES:
        if name in features:
            indicators.append(IndicatorValue(name=name, category=IndicatorCategory.LEADING.value, feature=features[name]))
    return indicators
