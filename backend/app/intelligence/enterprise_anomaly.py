"""Multi-metric anomaly scan — SIE Milestone 23: Enterprise Intelligence
Explainability & Anomaly Foundation v0.1, items 1-9.

    What happened?          (app/intelligence/enterprise_indicators.py, unchanged)
        -> What is changing?    (app/intelligence/enterprise_trend.py, unchanged)
            -> What is unusual?     (this module)
                -> How unusual is it?   (app/intelligence/anomaly.py::detect_anomaly(), reused unchanged)
                    -> What evidence produced that conclusion?  (bounded supporting_event_ids below)

**Reuses the existing anomaly foundation — does not replace it (item
1).** Every anomaly score in this module comes from
`app/intelligence/anomaly.py::detect_anomaly()`, the same z-score-
against-baseline function `app/predictions/feature_snapshot_service.py`
and `app/validation/enterprise_dataset_validation.py` already call —
this milestone extends that function additively (a new `direction`
field — see its own module docstring) rather than writing a second,
competing scoring formula.

**Reuses the existing temporal/bucketing foundation — does not
duplicate it (item 3, item 19).** The current period's per-metric
counts come from `current_events` — the *same*, already-fetched,
already point-in-time-correct (`events_as_of()`) event list
`app/intelligence/enterprise_intelligence_service.py` already builds for
indicators/trend/concentration/recurrence, so this module issues zero
extra queries for the current period. The baseline periods come from
`app/intelligence/temporal.py::bucketed_counts()` — the identical
primitive `app/intelligence/signals.py` and
`app/predictions/feature_snapshot_service.py` already use for their own
baseline comparisons, which itself delegates every bucket's query to
`events_as_of()`. No second, hand-written temporal filter exists
anywhere in this module.

**Supported metrics (item 1) — exactly the seven the milestone names,
each already genuinely represented in this codebase's own canonical
`event_type`/`event_subtype` vocabulary.** The subtype-matching
predicates are reused verbatim from
`app/intelligence/enterprise_indicators.py` (`_vehicle`, `_injury`,
`_property_damage` — the identical functions Milestone 22's own
`vehicle_incident_count`/`injury_event_count`/
`property_damage_event_count` indicators already use) and
`app/intelligence/signals.py` (`is_unsafe_observation`) — never
redefined a second time. No metric here has no genuine underlying data
representation; nothing is fabricated.

**Baseline depth is data-driven, not assumed (item 2, item 7).** Before
scanning any metric, `_available_baseline_periods()` computes — once,
shared across all seven metrics, so this costs exactly one additional
query regardless of how many metrics are scanned — how many complete
`window_days`-length periods actually precede the current window, using
this organization's (or site's) own earliest point-in-time-correct
event (built from `events_as_of()` itself — see that function's own
docstring for the two-timestamp `event_time <= as_of AND ingestion_time
<= as_of` guarantee, inherited here unchanged). When that count is below
`settings.INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS`, every metric is
reported `INSUFFICIENT_DATA` immediately — there is no history to
fabricate a baseline from, so `bucketed_counts()` is never even called
for that scan. Above the minimum, at most
`settings.ENTERPRISE_ANOMALY_BASELINE_PERIODS_MAX` periods are used —
"recent history", not "all of history since the organization's first
event".

**Non-overlapping with the current window, by construction.** Baseline
buckets are fetched via `bucketed_counts(..., period_end=window_start,
...)` — ending exactly at `window_start`, the identical convention
`app/intelligence/signals.py::_baseline_bucket_counts()` already
established. `current_events` (reused from the orchestrator) already
excludes `event_time == window_start` itself (the Milestone 22A
boundary correction — see
`app/intelligence/enterprise_intelligence_service.py`'s own docstring),
so the shared boundary instant belongs to the last baseline bucket only,
never both.

**Direction, not just magnitude (item 5).** Each result's `direction`
(`ABOVE_BASELINE`/`BELOW_BASELINE`/`NONE`) comes straight from
`detect_anomaly()`'s own new field — "incident count unusually high" and
"incident count unusually low" are both `ANOMALOUS` but are reported
distinctly, never collapsed into a single undifferentiated signal.

**No causal claim, ever.** This module (and its evidence) says *what*
is unusual and *how* unusual, never *why* — see
`app/intelligence/association.py`'s own hard causal boundary, which this
module's design deliberately mirrors, and
`app/intelligence/explanations.py::_anomaly_explanations()`'s own
docstring for the exact template wording this produces.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.anomaly import ANOMALY_CALCULATION_VERSION, detect_anomaly
from app.intelligence.enterprise_indicators import _injury, _property_damage, _vehicle
from app.intelligence.signals import is_unsafe_observation
from app.intelligence.temporal import bucketed_counts, events_as_of
from app.models.safety_event import SafetyEvent

_MAX_SUPPORTING_EVENT_IDS = 20

_Predicate = Callable[[SafetyEvent], bool]

# (metric key, label, event_type, predicate|None) -- the closed
# vocabulary of metrics this milestone supports (item 1). Every
# predicate here is imported, never redefined -- see module docstring.
_METRIC_DEFINITIONS: list[tuple[str, str, str, _Predicate | None]] = [
    ("incident_count", "Incident Count", "INCIDENT", None),
    ("near_miss_count", "Near Misses", "NEAR_MISS", None),
    ("observation_count", "Observations", "OBSERVATION", None),
    ("unsafe_observation_count", "Unsafe Observations", "OBSERVATION", is_unsafe_observation),
    ("vehicle_incident_count", "Vehicle Incidents", "INCIDENT", _vehicle),
    ("injury_event_count", "Injury Events", "INCIDENT", _injury),
    ("property_damage_event_count", "Property Damage Events", "INCIDENT", _property_damage),
]

SUPPORTED_ANOMALY_METRICS: tuple[str, ...] = tuple(key for key, _, _, _ in _METRIC_DEFINITIONS)


def _as_utc(value: datetime) -> datetime:
    """Normalize a possibly offset-naive `datetime` (SQLite does not
    round-trip `tzinfo`) to UTC-aware -- mirrors the identical,
    already-established pattern in `app/intelligence/reliability.py` and
    `app/intelligence/enterprise_intelligence_service.py`."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass
class EnterpriseAnomalyResult:
    metric: str
    label: str
    status: str  # AnomalyStatus value
    direction: str  # AnomalyDirection value
    current_value: float
    baseline_mean: float | None
    baseline_stdev: float | None
    z_score: float | None
    baseline_period_count: int
    current_period_start: datetime
    current_period_end: datetime
    window_days: int
    supporting_event_count: int
    baseline_window_start: datetime | None = None
    baseline_window_end: datetime | None = None
    supporting_event_ids: list[uuid.UUID] = field(default_factory=list)
    calculation_version: str = ANOMALY_CALCULATION_VERSION


def _available_baseline_periods(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
    as_of: datetime,
    window_start: datetime,
    window_days: int,
    max_periods: int,
) -> int:
    """How many complete `window_days`-length periods precede
    `window_start`, given this organization's (or site's) own earliest
    point-in-time-correct event — capped at `max_periods`. Built
    entirely from `events_as_of()`'s own query (no second, hand-written
    filter — see module docstring); one query total, shared across every
    metric this scan evaluates."""
    sub = events_as_of(organization_id=organization_id, as_of=as_of, site_id=site_id).subquery()
    earliest = db.execute(select(func.min(sub.c.event_time))).scalar_one_or_none()
    if earliest is None:
        return 0
    span_days = (window_start - _as_utc(earliest)).days
    if span_days <= 0:
        return 0
    return min(span_days // window_days, max_periods)


def compute_enterprise_anomalies(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
    current_events: list[SafetyEvent],
    as_of: datetime,
    window_start: datetime,
    window_days: int,
) -> list[EnterpriseAnomalyResult]:
    """`current_events` must already be the same point-in-time-correct,
    tenant-scoped, Milestone-22A-boundary-corrected event list
    `compute_enterprise_intelligence()` builds for indicators/trend —
    see module docstring for why this makes the current-period side of
    every metric here free (zero additional queries)."""
    max_periods = settings.ENTERPRISE_ANOMALY_BASELINE_PERIODS_MAX
    min_periods = settings.INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS
    available_periods = _available_baseline_periods(
        db,
        organization_id=organization_id,
        site_id=site_id,
        as_of=as_of,
        window_start=window_start,
        window_days=window_days,
        max_periods=max_periods,
    )

    results: list[EnterpriseAnomalyResult] = []
    for metric_key, label, event_type, predicate in _METRIC_DEFINITIONS:
        current_matches = [
            e for e in current_events if e.event_type == event_type and (predicate is None or predicate(e))
        ]
        current_value = float(len(current_matches))

        baseline_window_start: datetime | None = None
        baseline_window_end: datetime | None = None
        if available_periods < min_periods:
            # No history to fabricate a baseline from -- skip the query
            # entirely (item 16: avoid unnecessary queries).
            anomaly = detect_anomaly(current_value, [])
        else:
            buckets = bucketed_counts(
                db,
                organization_id=organization_id,
                site_id=site_id,
                period_end=window_start,
                period_days=window_days,
                num_periods=available_periods,
                event_type=event_type,
                predicate=predicate,
            )
            baseline_values = [float(count) for _, _, count in buckets]
            anomaly = detect_anomaly(current_value, baseline_values)
            if buckets:
                baseline_window_start = buckets[0][0]
                baseline_window_end = buckets[-1][1]

        results.append(
            EnterpriseAnomalyResult(
                metric=metric_key,
                label=label,
                status=anomaly.status,
                direction=anomaly.direction,
                current_value=current_value,
                baseline_mean=anomaly.baseline_mean,
                baseline_stdev=anomaly.baseline_stdev,
                z_score=anomaly.z_score,
                baseline_period_count=anomaly.baseline_period_count,
                current_period_start=window_start,
                current_period_end=as_of,
                window_days=window_days,
                supporting_event_count=len(current_matches),
                baseline_window_start=baseline_window_start,
                baseline_window_end=baseline_window_end,
                supporting_event_ids=[e.id for e in current_matches[:_MAX_SUPPORTING_EVENT_IDS]],
                calculation_version=anomaly.calculation_version,
            )
        )
    return results
