"""Grouped LEADING/LAGGING indicators with period-over-period comparison
— SIE Milestone 22: Enterprise Intelligence & Risk Analytics Foundation
v0.1, item 5.

Distinct from `app/intelligence/indicators.py` (which this milestone
leaves untouched — it is the existing `GET .../analytics/summary`
endpoint's own indicator list, a thin re-labeling of
`app/intelligence/features.py`'s `FeatureValue`s). This module is a
purpose-built, pure function over two already-fetched event lists (the
current window and the immediately preceding equal-length window — see
`app/intelligence/enterprise_trend.py`'s docstring for why the previous
period is computed with `events_as_of(as_of=window_start, ...)` rather
than `as_of=<the request's own as_of>`), so it never touches the database
itself and is trivially unit-testable.

**Every indicator here is a plain count over canonical, already-collected
`SafetyEvent` fields** (`event_type`, `event_subtype`, `severity`,
`status`) — never a fabricated metric. `event_subtype` matching is a
case-insensitive substring check, the same pattern
`app/intelligence/signals.py::is_unsafe_observation()` already
establishes for "unsafe" — deliberately loose (this codebase's own
`event_subtype` is free text, not a closed vocabulary; see
`app/models/safety_event.py`'s docstring) but scoped to the specific
subtype values this codebase's own fixtures and ingestion adapters
already produce (`VEHICLE_INCIDENT`, `PROPERTY_DAMAGE`, `FIRST_AID_CASE`,
`COMPLIANCE_FINDING`, ...) — never invented ones. "Fires" (milestone
item 5's own example list) is deliberately **not** included: nothing in
this codebase's existing event-subtype vocabulary genuinely represents
it, and item 5 is explicit — "do not fabricate unavailable indicators."

**A count is always a determinate integer, never `None`.** Unlike
`FeatureValue` (which has genuine rate-typed features that can be
unavailable — e.g. no exposure-hours data), every indicator here is a
plain count, which is always computable (zero is a real, meaningful
answer, never "unavailable"). Only `percentage_change` can be
undefined — division by a zero previous-period count — and that case is
reported explicitly (`unavailable_reason="PREVIOUS_PERIOD_ZERO"`, value
`None`) rather than as a misleading `0%` or `inf%` (milestone item 5's
own instruction).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.intelligence.enums import IndicatorCategory
from app.models.safety_event import SafetyEvent

ENTERPRISE_INDICATOR_CALCULATION_VERSION = "enterprise-indicator-v1"

_Predicate = Callable[[SafetyEvent], bool]


@dataclass
class EnterpriseIndicator:
    key: str
    label: str
    value: int
    category: str  # IndicatorCategory value -- also this indicator's milestone-item-5 "classification"
    period_start: datetime
    period_end: datetime
    window_days: int
    previous_value: int = 0
    absolute_change: int = 0
    percentage_change: float | None = None
    trend_direction: str | None = None  # "INCREASING" | "DECREASING" | "STABLE"
    unavailable_reason: str | None = None
    calculation_version: str = ENTERPRISE_INDICATOR_CALCULATION_VERSION


def _vehicle(e: SafetyEvent) -> bool:
    return "vehicle" in (e.event_subtype or "").lower()


def _property_damage(e: SafetyEvent) -> bool:
    return "property_damage" in (e.event_subtype or "").lower().replace(" ", "_")


def _injury(e: SafetyEvent) -> bool:
    subtype = (e.event_subtype or "").lower().replace(" ", "_")
    return "injury" in subtype or "first_aid" in subtype


def _unsafe_observation(e: SafetyEvent) -> bool:
    return "unsafe" in (e.event_subtype or "").lower()


def _audit_finding(e: SafetyEvent) -> bool:
    return "finding" in (e.event_subtype or "").lower()


def _overdue_action(e: SafetyEvent) -> bool:
    return e.status == "OVERDUE"


def _severity(level: str) -> _Predicate:
    return lambda e: e.severity == level


# (key, label, category, event_types, predicate|None) -- the one place
# this milestone's indicator vocabulary is defined. Adding a new
# indicator is a one-line addition here, never a schema change (mirrors
# `app/intelligence/indicators.py::LAGGING_INDICATOR_NAMES`'s own
# "extending this is additive" shape).
_INDICATOR_DEFINITIONS: list[tuple[str, str, IndicatorCategory, tuple[str, ...], _Predicate | None]] = [
    # --- Lagging (outcomes already realized) --------------------------------
    ("incident_count", "Incident Count", IndicatorCategory.LAGGING, ("INCIDENT",), None),
    ("vehicle_incident_count", "Vehicle Incidents", IndicatorCategory.LAGGING, ("INCIDENT",), _vehicle),
    (
        "property_damage_event_count",
        "Property Damage Events",
        IndicatorCategory.LAGGING,
        ("INCIDENT",),
        _property_damage,
    ),
    ("injury_event_count", "Injury Events", IndicatorCategory.LAGGING, ("INCIDENT",), _injury),
    # Severity distribution (milestone item 5's own example) -- one
    # indicator per band, over the same "severity pool" definition
    # app/intelligence/features.py already uses (incidents + near misses)
    # so this milestone does not invent a second severity population.
    (
        "severity_low_count",
        "Low Severity Events",
        IndicatorCategory.LAGGING,
        ("INCIDENT", "NEAR_MISS"),
        _severity("LOW"),
    ),
    (
        "severity_medium_count",
        "Medium Severity Events",
        IndicatorCategory.LAGGING,
        ("INCIDENT", "NEAR_MISS"),
        _severity("MEDIUM"),
    ),
    (
        "severity_high_count",
        "High Severity Events",
        IndicatorCategory.LAGGING,
        ("INCIDENT", "NEAR_MISS"),
        _severity("HIGH"),
    ),
    (
        "severity_critical_count",
        "Critical Severity Events",
        IndicatorCategory.LAGGING,
        ("INCIDENT", "NEAR_MISS"),
        _severity("CRITICAL"),
    ),
    # --- Leading (activity believed to precede outcomes) --------------------
    ("near_miss_count", "Near Misses", IndicatorCategory.LEADING, ("NEAR_MISS",), None),
    ("observation_count", "Observations", IndicatorCategory.LEADING, ("OBSERVATION",), None),
    (
        "unsafe_observation_count",
        "Unsafe Observations (Hazards)",
        IndicatorCategory.LEADING,
        ("OBSERVATION",),
        _unsafe_observation,
    ),
    ("inspection_count", "Inspections", IndicatorCategory.LEADING, ("INSPECTION",), None),
    ("audit_finding_count", "Audit Findings", IndicatorCategory.LEADING, ("AUDIT",), _audit_finding),
    (
        "overdue_action_count",
        "Overdue Actions",
        IndicatorCategory.LEADING,
        ("CORRECTIVE_ACTION",),
        _overdue_action,
    ),
]


def _count_matching(events: list[SafetyEvent], event_types: tuple[str, ...], predicate: _Predicate | None) -> int:
    subset = (e for e in events if e.event_type in event_types)
    if predicate is not None:
        subset = (e for e in subset if predicate(e))
    return sum(1 for _ in subset)


def compute_enterprise_indicators(
    current_events: list[SafetyEvent],
    previous_events: list[SafetyEvent],
    *,
    window_start: datetime,
    as_of: datetime,
    window_days: int,
) -> list[EnterpriseIndicator]:
    """Pure function — `current_events`/`previous_events` are already
    point-in-time-filtered, tenant-scoped `SafetyEvent` lists (see module
    docstring for how the previous window is fetched). No database
    access here, so this is trivially unit-testable and cannot itself
    introduce a temporal-leakage or tenant-isolation bug — both are
    already guaranteed by whatever produced the two event lists."""
    indicators: list[EnterpriseIndicator] = []
    for key, label, category, event_types, predicate in _INDICATOR_DEFINITIONS:
        current_value = _count_matching(current_events, event_types, predicate)
        previous_value = _count_matching(previous_events, event_types, predicate)
        absolute_change = current_value - previous_value

        if previous_value == 0:
            percentage_change = 0.0 if absolute_change == 0 else None
            unavailable_reason = None if absolute_change == 0 else "PREVIOUS_PERIOD_ZERO"
        else:
            percentage_change = round((absolute_change / previous_value) * 100, 2)
            unavailable_reason = None

        if current_value > previous_value:
            trend_direction = "INCREASING"
        elif current_value < previous_value:
            trend_direction = "DECREASING"
        else:
            trend_direction = "STABLE"

        indicators.append(
            EnterpriseIndicator(
                key=key,
                label=label,
                value=current_value,
                category=category.value,
                period_start=window_start,
                period_end=as_of,
                window_days=window_days,
                previous_value=previous_value,
                absolute_change=absolute_change,
                percentage_change=percentage_change,
                trend_direction=trend_direction,
                unavailable_reason=unavailable_reason,
            )
        )
    return indicators
