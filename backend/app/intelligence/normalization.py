"""Normalization utilities — milestone item 14. Every function here is a
pure, deterministic mapping from a raw source value to a normalized one,
returning `None` (never a guess, never a silent default) when the raw
value cannot be confidently normalized — the caller (`app/intelligence/validation.py`)
is what turns that `None` into a reported `ValidationIssue`.
`SafetyEvent.source_value` always preserves the original raw value
regardless of what normalization did with it.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.intelligence.enums import SeverityLevel

NORMALIZATION_VERSION = "normalize-v1"
"""Bumped whenever any function in this module changes in a way that
would change historical output for the same input — see the milestone's
own "calculation_version" requirement (item 39), mirrored here as
`SafetyEvent.normalization_version`."""

# Aliases a real source system might plausibly use for each normalized
# severity level. Deliberately generic (numbers, common words) rather
# than tuned to any one named vendor's exact scale.
_SEVERITY_ALIASES: dict[str, SeverityLevel] = {
    "low": SeverityLevel.LOW,
    "minor": SeverityLevel.LOW,
    "negligible": SeverityLevel.LOW,
    "1": SeverityLevel.LOW,
    "medium": SeverityLevel.MEDIUM,
    "moderate": SeverityLevel.MEDIUM,
    "2": SeverityLevel.MEDIUM,
    "high": SeverityLevel.HIGH,
    "major": SeverityLevel.HIGH,
    "serious": SeverityLevel.HIGH,
    "3": SeverityLevel.HIGH,
    "critical": SeverityLevel.CRITICAL,
    "severe": SeverityLevel.CRITICAL,
    "fatal": SeverityLevel.CRITICAL,
    "catastrophic": SeverityLevel.CRITICAL,
    "4": SeverityLevel.CRITICAL,
}

# Ordinal weight for averaging (see app/intelligence/features.py's
# avg_severity feature) -- a plain, documented 1-4 scale, never presented
# as a measurement unit or a probability.
SEVERITY_ORDINAL: dict[str, int] = {
    SeverityLevel.LOW.value: 1,
    SeverityLevel.MEDIUM.value: 2,
    SeverityLevel.HIGH.value: 3,
    SeverityLevel.CRITICAL.value: 4,
}

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_severity(raw: str | None) -> str | None:
    """Map a source system's own severity label onto
    `SeverityLevel` — or `None` if it doesn't match any known alias
    (reported as `INVALID_SEVERITY` by validation.py, never guessed)."""
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    level = _SEVERITY_ALIASES.get(key)
    return level.value if level else None


def normalize_datetime(raw: str | datetime | None) -> datetime | None:
    """Parse an ISO-8601 string (or pass through an already-`datetime`
    value) into a timezone-aware UTC `datetime`. Returns `None` for
    anything unparseable — never silently truncates or guesses a date."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    try:
        # datetime.fromisoformat handles "Z" only from Python 3.11+;
        # normalize that one common case explicitly for portability.
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize_category(raw: str | None) -> str | None:
    """Light-touch normalization for free-text categorical fields
    (location/department/contractor/activity/project): trims and
    collapses internal whitespace only. Deliberately does *not*
    title-case, alias, or otherwise rewrite the value — milestone item
    14 is explicit: "do not destroy source values." Two source systems
    spelling a contractor's name differently are a data-quality/entity-
    resolution problem for a future milestone, not something this
    function silently papers over."""
    if raw is None:
        return None
    collapsed = _WHITESPACE_RE.sub(" ", str(raw)).strip()
    return collapsed or None


def normalize_status(raw: str | None) -> str | None:
    """Trims and upper-cases a status value (`"open "` -> `"OPEN"`) — the
    one normalization applied uniformly across domains, since every
    domain's own status vocabulary (OPEN/CLOSED/OVERDUE for corrective
    actions, ACTIVE/EXPIRED for training/permits, ...) is otherwise
    free-form (see app/models/safety_event.py's docstring)."""
    if raw is None:
        return None
    collapsed = _WHITESPACE_RE.sub(" ", str(raw)).strip().upper()
    return collapsed or None


def normalize_units_hours(raw: float | int | str | None) -> float | None:
    """Coerce an exposure-hours value to a non-negative float, or `None`
    if it cannot be (milestone item 18 — exposure normalization must
    never fabricate a number from a malformed one)."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None
