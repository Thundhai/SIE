"""Temporal integrity — milestone items 15-16, the single most important
requirement in this milestone: *no future information may leak into a
historical feature calculation.*

`events_as_of()` below is the **one and only** query builder every
feature/indicator/trend/anomaly/signal calculation in
`app/intelligence/` uses to fetch `SafetyEvent` rows. Centralizing it
here — rather than letting each feature function write its own
`event_time <=` filter — is a deliberate defense: a leakage bug becomes
impossible to introduce accidentally in a new feature, and a regression
test against this one function (`tests/test_temporal_leakage.py`)
protects every caller at once, not just the one feature a test happened
to cover.

**Two timestamps are checked, not one.** The milestone's own worked
example ("if predicting risk for 2026-06-01, a feature must not include
an incident that happened 2026-06-15") is about `event_time`. But a
genuinely point-in-time-correct backtest also needs a second guarantee:
an event that *happened* before the prediction date but was only
*reported/ingested* afterward (a backdated report) would not actually
have been knowable at that historical moment either. `events_as_of()`
therefore filters on **both** `SafetyEvent.event_time <= as_of` and
`SafetyEvent.ingestion_time <= as_of` by default — the stricter,
more-correct default for anything computing a *historical* feature
snapshot. Live "as of right now" queries (the normal case for the
analytics API, where `as_of` defaults to `now()`) are unaffected either
way, since every event in the database necessarily has
`ingestion_time <= now()`.

**Data quality is filtered here too.** `QUARANTINED` and `INVALID`
records are excluded by default (see `app/intelligence/enums.py`'s
`DataQualityStatus` docstring) — every feature/signal calculation
"just works" on usable data without repeating that filter itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, select

from app.intelligence.enums import DataQualityStatus
from app.models.safety_event import SafetyEvent

_USABLE_QUALITY_STATUSES = (DataQualityStatus.VALID.value, DataQualityStatus.PARTIAL.value)


def events_as_of(
    *,
    organization_id: uuid.UUID,
    as_of: datetime,
    window_start: datetime | None = None,
    site_id: uuid.UUID | None = None,
    event_type: str | None = None,
    event_types: list[str] | None = None,
    include_quarantined: bool = False,
    strict_point_in_time: bool = True,
) -> Select:
    """Build (never execute) a `SafetyEvent` query, tenant-scoped and
    temporally correct as of `as_of`. Callers execute it themselves
    (`db.execute(events_as_of(...)).scalars().all()`) so this stays a
    pure query builder, not a service with its own session dependency.
    """
    clauses = [
        SafetyEvent.organization_id == organization_id,
        SafetyEvent.event_time <= as_of,
    ]
    if strict_point_in_time:
        clauses.append(SafetyEvent.ingestion_time <= as_of)
    if window_start is not None:
        clauses.append(SafetyEvent.event_time >= window_start)
    if site_id is not None:
        clauses.append(SafetyEvent.site_id == site_id)
    if event_type is not None:
        clauses.append(SafetyEvent.event_type == event_type)
    if event_types is not None:
        clauses.append(SafetyEvent.event_type.in_(event_types))
    # include_quarantined=True adds QUARANTINED to the usable set (a
    # caller reviewing held-for-review records) — INVALID is never
    # included either way; it is not "held for review", it is data this
    # codebase has determined is not usable at all (see
    # app/intelligence/enums.py::DataQualityStatus's own docstring).
    allowed_statuses = _USABLE_QUALITY_STATUSES + ((DataQualityStatus.QUARANTINED.value,) if include_quarantined else ())
    clauses.append(SafetyEvent.data_quality_status.in_(allowed_statuses))

    return select(SafetyEvent).where(*clauses).order_by(SafetyEvent.event_time)


def window_bounds(as_of: datetime, window_days: int) -> tuple[datetime, datetime]:
    """`(window_start, as_of)` for a trailing window ending at `as_of` —
    the one place "N days" becomes two concrete timestamps, so every
    caller computes the boundary identically."""
    return as_of - timedelta(days=window_days), as_of


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def bucketed_counts(
    db,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
    period_end: datetime,
    period_days: int,
    num_periods: int,
    event_type: str | None = None,
    predicate=None,
) -> list[tuple[datetime, datetime, int]]:
    """`num_periods` consecutive, non-overlapping, `period_days`-length
    buckets ending at `period_end`, oldest first — each a
    `(period_start, period_end, count)` tuple. Shared by
    `app/intelligence/signals.py` (baseline comparison) and
    `app/intelligence/analytics.py` (trend period series), so both use
    the identical, temporally-correct (`events_as_of()`) bucketing
    logic."""
    buckets: list[tuple[datetime, datetime, int]] = []
    bucket_end = period_end
    for _ in range(num_periods):
        bucket_start = bucket_end - timedelta(days=period_days)
        query = events_as_of(
            organization_id=organization_id,
            as_of=bucket_end,
            window_start=bucket_start,
            site_id=site_id,
            event_type=event_type,
        )
        events = db.execute(query).scalars().all()
        count = sum(1 for e in events if predicate(e)) if predicate else len(events)
        buckets.append((bucket_start, bucket_end, count))
        bucket_end = bucket_start
    buckets.reverse()
    return buckets
