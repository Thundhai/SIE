"""Recurrence and pattern detection — SIE Milestone 22: Enterprise
Intelligence & Risk Analytics Foundation v0.1, item 8.

A deterministic count-and-bucket detector — no clustering, no ML
(explicitly out of scope for this milestone). Two pattern shapes, both
requiring a known `site_id` (a pattern is, by definition, "the same kind
of thing happening repeatedly at the same site" — an event with no site
attribution cannot participate in either):

  * `(site, event_type)` — e.g. "Site 04 + INCIDENT recurred 4 times".
  * `(site, event_subtype)` — e.g. "Site 04 + VEHICLE_INCIDENT recurred 4
    times", a narrower, more specific pattern than the event_type one
    above (only emitted when `event_subtype` is present on the event).

**Population: `INCIDENT` and `NEAR_MISS` events only.** Recurrence
detection is about *adverse* signal repeating, the same population
`app/intelligence/concentration.py`'s severity dimension already uses —
not "this site had 3 AUDITs this quarter" (routine activity, not a risk
pattern). Documented here as a deliberate scope choice, not an oversight.

**Separate sites never combine** (milestone item 20's own required test)
— trivially true by construction: `site_id` is part of every pattern
key, so two sites each reporting 2 vehicle incidents produce two separate
`WATCH`-classified patterns, never one combined `RECURRING` one.

**Classification thresholds** (`settings.ENTERPRISE_RECURRENCE_*`,
documented *initial* defaults — the same standing caveat every other
threshold in this codebase carries):

    count == 1        -> NONE            (not a pattern -- never returned)
    count >= WATCH_MIN (2)                -> WATCH
    count >= RECURRING_MIN (3)            -> RECURRING
    count >= HIGH_MIN (5)                 -> HIGH_RECURRENCE

`classify_recurrence()` is exposed standalone (total over any
non-negative count, including 0/1 -> `NONE`) for direct unit testing of
the exact threshold boundaries (milestone item 20); the sweep itself
(`detect_recurrence()`) only ever emits patterns with `count >= 2` — a
single occurrence is not a pattern, so `NONE` never appears in a real
result list.

**Bounded evidence.** `supporting_event_ids` is capped at
`_MAX_SUPPORTING_EVENT_IDS` (mirrors
`app/intelligence/features.py::_MAX_SOURCE_EVENT_IDS`) — a genuinely
high-recurrence pattern still returns a bounded sample plus the real
total `count`, never an unbounded list.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.core.config import settings
from app.intelligence.enums import RecurrenceClassification
from app.models.safety_event import SafetyEvent

ENTERPRISE_RECURRENCE_CALCULATION_VERSION = "enterprise-recurrence-v1"
_RECURRENCE_POPULATION_TYPES = ("INCIDENT", "NEAR_MISS")
_MAX_SUPPORTING_EVENT_IDS = 20


@dataclass
class RecurrencePattern:
    pattern_key: str
    scope: str  # "site:<site_id>"
    site_id: uuid.UUID
    site_label: str
    event_type: str
    event_subtype: str | None
    count: int
    first_seen: datetime
    last_seen: datetime
    window_start: datetime
    window_end: datetime
    window_days: int
    supporting_event_ids: list[uuid.UUID] = field(default_factory=list)
    classification: str = RecurrenceClassification.NONE.value
    calculation_version: str = ENTERPRISE_RECURRENCE_CALCULATION_VERSION


def classify_recurrence(count: int) -> RecurrenceClassification:
    if count >= settings.ENTERPRISE_RECURRENCE_HIGH_MIN:
        return RecurrenceClassification.HIGH_RECURRENCE
    if count >= settings.ENTERPRISE_RECURRENCE_RECURRING_MIN:
        return RecurrenceClassification.RECURRING
    if count >= settings.ENTERPRISE_RECURRENCE_WATCH_MIN:
        return RecurrenceClassification.WATCH
    return RecurrenceClassification.NONE


def _pattern_from_group(
    key: tuple[uuid.UUID, str, str | None],
    group: list[SafetyEvent],
    *,
    window_start: datetime,
    window_end: datetime,
    window_days: int,
    site_labels: dict[uuid.UUID, str],
) -> RecurrencePattern:
    site_id, event_type, event_subtype = key
    ordered = sorted(group, key=lambda e: e.event_time)
    subtype_part = f"|event_subtype:{event_subtype}" if event_subtype is not None else ""
    pattern_key = f"site:{site_id}|event_type:{event_type}{subtype_part}"
    return RecurrencePattern(
        pattern_key=pattern_key,
        scope=f"site:{site_id}",
        site_id=site_id,
        site_label=site_labels.get(site_id, str(site_id)),
        event_type=event_type,
        event_subtype=event_subtype,
        count=len(ordered),
        first_seen=ordered[0].event_time,
        last_seen=ordered[-1].event_time,
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
        supporting_event_ids=[e.id for e in ordered[:_MAX_SUPPORTING_EVENT_IDS]],
        classification=classify_recurrence(len(ordered)).value,
    )


def detect_recurrence(
    events: list[SafetyEvent],
    *,
    window_start: datetime,
    window_end: datetime,
    window_days: int,
    site_labels: dict[uuid.UUID, str] | None = None,
) -> list[RecurrencePattern]:
    """Pure function over an already-fetched, point-in-time-correct,
    tenant-scoped event list — see module docstring for the population
    and classification rules. Returns only genuine patterns (`count >=
    settings.ENTERPRISE_RECURRENCE_WATCH_MIN`), ranked by count
    descending (ties broken by `pattern_key` for determinism)."""
    site_labels = site_labels or {}
    population = [e for e in events if e.event_type in _RECURRENCE_POPULATION_TYPES and e.site_id is not None]

    by_type: dict[tuple[uuid.UUID, str, None], list[SafetyEvent]] = defaultdict(list)
    by_subtype: dict[tuple[uuid.UUID, str, str], list[SafetyEvent]] = defaultdict(list)
    for e in population:
        by_type[(e.site_id, e.event_type, None)].append(e)
        if e.event_subtype:
            by_subtype[(e.site_id, e.event_type, e.event_subtype)].append(e)

    patterns: list[RecurrencePattern] = []
    for key, group in {**by_type, **by_subtype}.items():
        if len(group) < settings.ENTERPRISE_RECURRENCE_WATCH_MIN:
            continue
        patterns.append(
            _pattern_from_group(
                key,
                group,
                window_start=window_start,
                window_end=window_end,
                window_days=window_days,
                site_labels=site_labels,
            )
        )

    patterns.sort(key=lambda p: (-p.count, p.pattern_key))
    return patterns
