"""Cross-metric association scan — SIE Milestone 24: Enterprise
Intelligence Pattern & Correlation Foundation v0.1, items 4-10, 12-16,
18-19.

    What happened?          (app/intelligence/enterprise_indicators.py, unchanged)
        -> What is changing?    (app/intelligence/enterprise_trend.py, unchanged)
            -> What is unusual?     (app/intelligence/enterprise_anomaly.py, unchanged)
                -> What patterns repeatedly occur?      (app/intelligence/recurrence.py, unchanged)
                    -> What safety dimensions appear associated?  (this module)
                        -> What evidence supports that observation?  (bounded supporting_event_ids below)

**Reuses the existing association foundation — does not replace it (item
4).** Every correlation in this module comes from
`app/intelligence/association.py::detect_association()`, the pre-existing
Pearson-correlation-over-aligned-periods function (extended additively in
this same milestone — see its own module docstring) — this module never
computes a second, competing correlation formula.

**Reuses the same closed metric vocabulary anomaly detection already
established (item 16).** `SUPPORTED_ASSOCIATION_METRICS` is *exactly*
`app/intelligence/enterprise_anomaly.py::SUPPORTED_ANOMALY_METRICS`'s own
seven metrics, built from the identical `_METRIC_DEFINITIONS` list
(imported directly, not redefined) — the same event-type/subtype
predicates already reused there from `app/intelligence/enterprise_indicators.py`
and `app/intelligence/signals.py`. No arbitrary caller-supplied metric
name is ever accepted: this module always evaluates the full, fixed set
of pairs itself; there is no `metric_a=<anything>` parameter anywhere in
this codebase's API (item 16).

**Query strategy (item 15) — one shared period sweep, not one query per
metric or per pair.** With 7 supported metrics there are exactly
`C(7,2) = 21` unordered pairs, always (a fixed constant, never
proportional to event volume or organization size — item 19's own "no
MAX_PAIRS needed" rationale, see `app/core/config.py`). A naive
implementation would run one query per metric (or worse, per pair) per
period. Instead, `_bucketed_events()` below issues exactly one query per
*period* (at most `settings.ENTERPRISE_ASSOCIATION_MAX_PERIODS`, 6 by
default) fetching *all* events in that period — unfiltered by
event_type — and every metric's per-period count, for every one of the
21 pairs, is then derived from that same already-fetched event list in
memory (each metric's predicate applied in Python, not a second SQL
filter). Pairwise correlation itself is pure in-memory arithmetic. No
Redis, no background workers, no distributed processing.

**Baseline/period depth is data-driven, not assumed (item 7), mirroring
`enterprise_anomaly.py::_available_baseline_periods()`'s own established
pattern.** `_available_periods()` computes, once, how many complete
`window_days`-length periods actually precede (and include) `as_of`,
using this organization's (or site's) own earliest point-in-time-correct
event (built from `events_as_of()` itself, never a second hand-written
temporal filter). Below `settings.ENTERPRISE_ASSOCIATION_MIN_PERIODS`,
every pair is reported `INSUFFICIENT_DATA` immediately, with
`_bucketed_events()` never even called — there is no history to compute a
meaningful correlation from two or three observations (item 7's own
instruction).

**Periods end at `as_of`, unlike the anomaly baseline (a deliberate,
documented difference).** `app/intelligence/enterprise_anomaly.py`'s
baseline periods deliberately *exclude* the current window (a baseline
must not include the value being compared against it). An association,
by contrast, is about *co-movement across recent history including the
present* — there is no separate "current value" to keep independent of
the baseline the way anomaly detection needs. So this module's periods
run `period_end=as_of`, `num_periods` consecutive `window_days`-length
buckets ending there — the same non-overlapping, temporally-correct
bucketing convention `app/intelligence/temporal.py::bucketed_counts()`
already establishes (each bucket built from `events_as_of()`, both bounds
inclusive, consistent with that function's own documented boundary
semantics — this module does not touch or reimplement it).

**Point-in-time integrity (item 2).** Every event contributing to a
period's metric counts satisfies `event_time <= as_of AND ingestion_time
<= as_of`, inherited entirely from `events_as_of()`. Milestone 22A's
window-boundary rules are the same ones `bucketed_counts()` already
established and this module's own `_bucketed_events()` mirrors exactly
(bucket `N`'s end is bucket `N+1`'s start; no separate boundary rule is
introduced here).

**No causal claim, ever.** This module's evidence and the explanation
service built on top of it (`app/intelligence/explanations.py::
_association_explanations()`) describe *co-movement*, never *cause* — see
`app/intelligence/association.py`'s own hard causal boundary, which this
module's design mirrors exactly, the same way
`app/intelligence/enterprise_anomaly.py` does for anomalies.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.association import ASSOCIATION_CALCULATION_VERSION, detect_association
from app.intelligence.enterprise_anomaly import _METRIC_DEFINITIONS
from app.intelligence.temporal import events_as_of
from app.models.safety_event import SafetyEvent

_MAX_SUPPORTING_EVENT_IDS = 20

SUPPORTED_ASSOCIATION_METRICS: tuple[str, ...] = tuple(key for key, _, _, _ in _METRIC_DEFINITIONS)
_METRIC_LABELS: dict[str, str] = {key: label for key, label, _, _ in _METRIC_DEFINITIONS}


def _as_utc(value: datetime) -> datetime:
    """Normalize a possibly offset-naive `datetime` (SQLite does not
    round-trip `tzinfo`) to UTC-aware -- mirrors the identical,
    already-established pattern in `app/intelligence/reliability.py` and
    `app/intelligence/enterprise_anomaly.py`."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass
class EnterpriseAssociationResult:
    metric_a: str
    metric_b: str
    label_a: str
    label_b: str
    classification: str  # AssociationClassification value
    correlation_coefficient: float | None
    period_count: int
    period_start: datetime | None
    period_end: datetime | None
    window_days: int
    values_a: list[float] = field(default_factory=list)
    values_b: list[float] = field(default_factory=list)
    supporting_event_ids: list[uuid.UUID] = field(default_factory=list)
    calculation_version: str = ASSOCIATION_CALCULATION_VERSION


def _available_periods(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
    as_of: datetime,
    window_days: int,
    max_periods: int,
) -> int:
    """How many complete `window_days`-length periods precede *and
    include* `as_of` (see module docstring for why this differs from
    `enterprise_anomaly.py::_available_baseline_periods()`'s
    `window_start` reference point), given this organization's (or
    site's) own earliest point-in-time-correct event -- capped at
    `max_periods`. Built entirely from `events_as_of()`'s own query (no
    second, hand-written filter); one query total, shared across every
    one of the 21 supported pairs."""
    sub = events_as_of(organization_id=organization_id, as_of=as_of, site_id=site_id).subquery()
    earliest = db.execute(select(func.min(sub.c.event_time))).scalar_one_or_none()
    if earliest is None:
        return 0
    span_days = (as_of - _as_utc(earliest)).days
    if span_days <= 0:
        return 0
    return min(span_days // window_days, max_periods)


def _bucketed_events(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
    period_end: datetime,
    period_days: int,
    num_periods: int,
) -> list[tuple[datetime, datetime, list[SafetyEvent]]]:
    """`num_periods` consecutive, non-overlapping, `period_days`-length
    buckets ending at `period_end`, oldest first -- each a
    `(period_start, period_end, events)` tuple, `events` being *every*
    event in that period regardless of type (no `event_type` filter at
    the query level, unlike `app/intelligence/temporal.py::
    bucketed_counts()`) so every one of the 7 supported metrics' counts
    can be derived from the same fetch, in memory (item 15 -- exactly one
    query per period, never one per metric)."""
    buckets: list[tuple[datetime, datetime, list[SafetyEvent]]] = []
    bucket_end = period_end
    for _ in range(num_periods):
        bucket_start = bucket_end - timedelta(days=period_days)
        query = events_as_of(
            organization_id=organization_id, as_of=bucket_end, window_start=bucket_start, site_id=site_id
        )
        events = list(db.execute(query).scalars().all())
        buckets.append((bucket_start, bucket_end, events))
        bucket_end = bucket_start
    buckets.reverse()
    return buckets


def _metric_matches(events: list[SafetyEvent], *, event_type: str, predicate) -> list[SafetyEvent]:
    return [e for e in events if e.event_type == event_type and (predicate is None or predicate(e))]


def compute_enterprise_associations(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
    as_of: datetime,
    window_days: int,
) -> list[EnterpriseAssociationResult]:
    """Returns exactly `len(SUPPORTED_ASSOCIATION_METRICS) choose 2` (21)
    results, always -- one per unordered metric pair, in a fixed,
    deterministic order (`_METRIC_DEFINITIONS`' own declaration order) --
    never hidden, never fabricated (item 18: an `INSUFFICIENT_DATA` pair
    is still returned, with its real `period_count`, not omitted)."""
    max_periods = settings.ENTERPRISE_ASSOCIATION_MAX_PERIODS
    min_periods = settings.ENTERPRISE_ASSOCIATION_MIN_PERIODS
    available_periods = _available_periods(
        db, organization_id=organization_id, site_id=site_id, as_of=as_of, window_days=window_days, max_periods=max_periods
    )

    buckets: list[tuple[datetime, datetime, list[SafetyEvent]]] = []
    if available_periods >= min_periods:
        buckets = _bucketed_events(
            db,
            organization_id=organization_id,
            site_id=site_id,
            period_end=as_of,
            period_days=window_days,
            num_periods=available_periods,
        )

    # Per-metric, per-period matching events -- computed once, reused for
    # every pair a metric participates in (6 pairs each, out of the 21
    # total) rather than re-filtered per pair.
    matches_by_metric: dict[str, list[list[SafetyEvent]]] = {}
    for metric_key, _, event_type, predicate in _METRIC_DEFINITIONS:
        matches_by_metric[metric_key] = [_metric_matches(events, event_type=event_type, predicate=predicate) for _, _, events in buckets]

    period_start = buckets[0][0] if buckets else None
    period_end = buckets[-1][1] if buckets else None

    results: list[EnterpriseAssociationResult] = []
    for (metric_a, _, _, _), (metric_b, _, _, _) in itertools.combinations(_METRIC_DEFINITIONS, 2):
        if buckets:
            series_a = [float(len(m)) for m in matches_by_metric[metric_a]]
            series_b = [float(len(m)) for m in matches_by_metric[metric_b]]
            # De-duplicated, order-preserving -- an event can satisfy both
            # metrics at once (e.g. an INCIDENT that is also a
            # vehicle_incident_count match), and must not be counted twice
            # in the bounded evidence sample.
            seen: set[uuid.UUID] = set()
            supporting_ids: list[uuid.UUID] = []
            for period_matches_a, period_matches_b in zip(matches_by_metric[metric_a], matches_by_metric[metric_b]):
                for e in period_matches_a + period_matches_b:
                    if e.id not in seen:
                        seen.add(e.id)
                        supporting_ids.append(e.id)
            supporting_ids = supporting_ids[:_MAX_SUPPORTING_EVENT_IDS]
        else:
            series_a, series_b, supporting_ids = [], [], []

        association = detect_association(series_a, series_b, min_periods=min_periods)
        results.append(
            EnterpriseAssociationResult(
                metric_a=metric_a,
                metric_b=metric_b,
                label_a=_METRIC_LABELS[metric_a],
                label_b=_METRIC_LABELS[metric_b],
                classification=association.classification,
                correlation_coefficient=association.correlation_coefficient,
                period_count=association.period_count,
                period_start=period_start,
                period_end=period_end,
                window_days=window_days,
                values_a=series_a,
                values_b=series_b,
                supporting_event_ids=supporting_ids,
                calculation_version=association.calculation_version,
            )
        )
    return results
