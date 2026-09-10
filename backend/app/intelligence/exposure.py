"""Exposure normalization — milestone items 18/51. Raw event counts can
be badly misleading without knowing how much work was actually done: 10
incidents in 10,000 hours is not the same risk picture as 10 incidents
in 500 hours.

Exposure is represented as ordinary `SafetyEvent` rows —
`event_type=WORKFORCE`, `event_subtype="EXPOSURE_HOURS"`,
`attributes={"hours": <float>}`, `event_time`/`period_end` marking the
period the hours cover — the same "one canonical table, not a dozen
specialized ones" design `app/models/safety_event.py`'s docstring
explains, rather than a second `exposure_records` table.

**Never fabricated.** `compute_exposure_hours()` returns `None` (never
`0.0`, never an assumed default) when no exposure records exist for the
requested scope/window — `EXPOSURE_DATA_UNAVAILABLE` below is exactly
that `None` case's name, used by every caller that would otherwise
divide by it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.intelligence.temporal import events_as_of

EXPOSURE_DATA_UNAVAILABLE = "EXPOSURE_DATA_UNAVAILABLE"

_EXPOSURE_EVENT_TYPE = "WORKFORCE"
_EXPOSURE_SUBTYPE = "EXPOSURE_HOURS"


def compute_exposure_hours(
    db: Session,
    *,
    organization_id: uuid.UUID,
    as_of: datetime,
    window_start: datetime,
    site_id: uuid.UUID | None = None,
) -> float | None:
    """Sum `attributes["hours"]` across `WORKFORCE`/`EXPOSURE_HOURS`
    events overlapping `[window_start, as_of]`, as of `as_of` (see
    `app/intelligence/temporal.py`). Returns `None` if no exposure
    records are found — see module docstring."""
    query = events_as_of(
        organization_id=organization_id,
        as_of=as_of,
        window_start=window_start,
        site_id=site_id,
        event_type=_EXPOSURE_EVENT_TYPE,
    )
    events = [
        e
        for e in db.execute(query).scalars().all()
        if e.event_subtype == _EXPOSURE_SUBTYPE
    ]
    if not events:
        return None

    total = 0.0
    found_any_hours = False
    for event in events:
        hours = event.attributes.get("hours") if event.attributes else None
        if hours is None:
            continue
        try:
            total += float(hours)
            found_any_hours = True
        except (TypeError, ValueError):
            continue
    return total if found_any_hours else None


def normalize_rate_per_100k_hours(count: int, exposure_hours: float | None) -> float | str:
    """`count / exposure_hours * 100_000`, or the
    `EXPOSURE_DATA_UNAVAILABLE` sentinel string if `exposure_hours` is
    `None` or zero — never a fabricated/misleading rate (milestone item
    18: "if exposure is missing... rather than calculating a misleading
    rate")."""
    if exposure_hours is None or exposure_hours <= 0:
        return EXPOSURE_DATA_UNAVAILABLE
    return round(count / exposure_hours * 100_000, 4)
