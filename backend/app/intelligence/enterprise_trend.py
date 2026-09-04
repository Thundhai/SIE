"""Period-over-period trend classification — SIE Milestone 22: Enterprise
Intelligence & Risk Analytics Foundation v0.1, item 6.

Distinct from `app/intelligence/trends.py` (left entirely untouched — a
multi-period least-squares regression over N period buckets, still used
by `GET .../analytics/trends`). This module answers a narrower, simpler
question the milestone spec itself poses: *comparing the current analysis
window against the immediately preceding equal-length window, is the
primary safety outcome getting better, worse, or staying about the
same?*

    as_of=2026-09-01, window=30d
        current:  2026-08-03 -> 2026-09-01
        previous: 2026-07-04 -> 2026-08-02   (immediately preceding, equal length)

**Boundary semantics (milestone item 4; corrected in Milestone 22A —
see that milestone's own completion report).** The current window is
`(as_of - window_days, as_of]`; the previous window is the same length,
ending exactly where the current one starts:
`(as_of - 2*window_days, as_of - window_days]` — both boundaries
computed via `app/intelligence/temporal.py::window_bounds()`, called
twice (`window_bounds(as_of, window_days)` then
`window_bounds(window_start, window_days)`), never a second,
independently-hand-written boundary calculation. The two windows are
**strictly non-overlapping**: an event landing exactly on the shared
edge (`event_time == as_of - window_days`) belongs to the **previous**
period only. `events_as_of()`'s own `window_start` filter is `>=`
(shared, unchanged — every other caller in this codebase relies on that
inclusive lower bound), so
`app/intelligence/enterprise_intelligence_service.py::compute_enterprise_intelligence()`
applies one additional, scoped filter after fetching the current
window's events (`event_time > window_start`) to exclude that shared
edge from the current period — the previous period's own inclusive
upper bound (`events_as_of(as_of=window_start, ...)`, i.e.
`event_time <= window_start`) is its single source of truth. See
`tests/test_enterprise_intelligence_service.py`'s exact-boundary test
for the assertion.

**Point-in-time correctness for the previous period (milestone item 3).**
The previous period is fetched via
`events_as_of(as_of=window_start, window_start=previous_start, ...)` —
*not* `as_of=<the request's own as_of>` — mirroring
`app/intelligence/temporal.py::bucketed_counts()`'s own established,
already-tested convention exactly (see that function's docstring): an
event that happened in the previous period but was only ingested *after*
the previous period ended (and before the current `as_of`) would not
actually have been knowable "as of the previous period's own end" either,
so it is correctly excluded from the previous-period baseline. This is
the stricter, more-conservative interpretation of "point-in-time correct"
this codebase has already established as its standard, not a new rule
invented for this milestone.

**Semantic, not merely directional (milestone item 6).** The primary
metric is total `INCIDENT` count — the one lagging indicator every
`SafetyEvent`-backed organization/site in this codebase can report,
regardless of which of the eleven data domains it actually uses. More
incidents is always DETERIORATING; fewer is always IMPROVING — this
module makes no claim about *why* (`app/intelligence/association.py`'s
own "correlation, not causation" boundary applies equally here: this
module has no causal vocabulary at all, only IMPROVING/STABLE/
DETERIORATING/INSUFFICIENT_DATA).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.config import settings
from app.intelligence.enums import EnterpriseTrendClassification
from app.models.safety_event import SafetyEvent

ENTERPRISE_TREND_CALCULATION_VERSION = "enterprise-trend-v1"
ENTERPRISE_TREND_PRIMARY_METRIC = "incident_count"


@dataclass
class EnterpriseTrendResult:
    classification: str  # EnterpriseTrendClassification value
    metric: str
    current_value: int
    previous_value: int
    absolute_change: int
    percentage_change: float | None
    current_period_start: datetime
    current_period_end: datetime
    previous_period_start: datetime
    previous_period_end: datetime
    calculation_version: str = ENTERPRISE_TREND_CALCULATION_VERSION


def _incident_count(events: list[SafetyEvent]) -> int:
    return sum(1 for e in events if e.event_type == "INCIDENT")


def classify_enterprise_trend(
    current_events: list[SafetyEvent],
    previous_events: list[SafetyEvent],
    *,
    window_start: datetime,
    as_of: datetime,
    previous_period_start: datetime,
    previous_period_end: datetime,
    min_combined_events: int | None = None,
    change_threshold: float | None = None,
) -> EnterpriseTrendResult:
    """Pure function over two already-fetched, point-in-time-correct
    event lists — see module docstring for exactly how each was fetched.

    Deterministic rule (documented, not hidden — milestone item 6):

    1. `current_value + previous_value < min_combined_events` (default
       `settings.ENTERPRISE_TREND_MIN_COMBINED_EVENTS`) -> `INSUFFICIENT_DATA`.
       Never build a trend claim on a handful of events.
    2. Otherwise compute `percentage_change`:
       - `previous_value == 0`: undefined as a ratio: `DETERIORATING` if
         `current_value > 0` (any incidents where there were previously
         none, having already cleared the combined-minimum floor above,
         is a real deterioration), else `STABLE` (both zero).
       - `previous_value > 0`: `percentage_change = (current - previous) / previous`.
         `>= change_threshold` (default 20%) -> `DETERIORATING`;
         `<= -change_threshold` -> `IMPROVING`; otherwise `STABLE`.
    """
    min_combined_events = (
        min_combined_events if min_combined_events is not None else settings.ENTERPRISE_TREND_MIN_COMBINED_EVENTS
    )
    change_threshold = (
        change_threshold if change_threshold is not None else settings.ENTERPRISE_TREND_CHANGE_THRESHOLD
    )

    current_value = _incident_count(current_events)
    previous_value = _incident_count(previous_events)
    absolute_change = current_value - previous_value

    common = dict(
        metric=ENTERPRISE_TREND_PRIMARY_METRIC,
        current_value=current_value,
        previous_value=previous_value,
        absolute_change=absolute_change,
        current_period_start=window_start,
        current_period_end=as_of,
        previous_period_start=previous_period_start,
        previous_period_end=previous_period_end,
    )

    if (current_value + previous_value) < min_combined_events:
        return EnterpriseTrendResult(
            classification=EnterpriseTrendClassification.INSUFFICIENT_DATA.value,
            percentage_change=None,
            **common,
        )

    if previous_value == 0:
        percentage_change = None
        classification = (
            EnterpriseTrendClassification.DETERIORATING if current_value > 0 else EnterpriseTrendClassification.STABLE
        )
    else:
        percentage_change = (absolute_change / previous_value)
        if percentage_change >= change_threshold:
            classification = EnterpriseTrendClassification.DETERIORATING
        elif percentage_change <= -change_threshold:
            classification = EnterpriseTrendClassification.IMPROVING
        else:
            classification = EnterpriseTrendClassification.STABLE
        percentage_change = round(percentage_change * 100, 2)

    return EnterpriseTrendResult(
        classification=classification.value,
        percentage_change=percentage_change,
        **common,
    )
