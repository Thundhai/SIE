"""Risk concentration analysis — SIE Milestone 22: Enterprise Intelligence
& Risk Analytics Foundation v0.1, item 7.

A deterministic, purely arithmetic "where is adverse safety signal
concentrated" ranking over one already-fetched, point-in-time-correct,
tenant-scoped `SafetyEvent` list — no query of its own, so it inherits
whatever temporal/tenant correctness produced that list (the same
pure-function shape `app/intelligence/enterprise_indicators.py` and
`enterprise_trend.py` already establish).

**Four dimensions, each answering a different "where":**

  * `site` — which site accounts for the largest share of this
    organization's `INCIDENT` events (organization scope only; a
    site-scoped request already *is* one site, so this dimension is
    never returned there — there is nothing to rank).
  * `event_subtype` — within `INCIDENT` events, which subtype (vehicle,
    property damage, injury, ...) accounts for the largest share.
  * `severity` — within the same severity pool
    `app/intelligence/features.py` already uses (`INCIDENT` + `NEAR_MISS`
    events with a recognized `severity`), which band accounts for the
    largest share.
  * `event_type` — across *all* eleven data domains in the window
    (not only `INCIDENT`), which one accounts for the largest share of
    total recorded activity. Distinct in kind from the other three
    (which all rank sub-populations of a single "adverse" set); this one
    answers a data-composition question (e.g. "90% of everything
    recorded this window is OBSERVATION, almost nothing is INCIDENT") a
    real HSE reviewer would also want surfaced.

**Percentages come from real counts, never generated prose** (milestone
item 7's own instruction) — every `ConcentrationContributor.percentage`
is `count / total_for_dimension`, both integers taken directly from the
event list this function was handed.

**Minimum-data safeguard.** A dimension's ranking is only returned when
its own total population reaches `settings.ENTERPRISE_CONCENTRATION_MIN_POPULATION`
(default 5) — a "100% concentration" computed from one or two events is
not statistically meaningful and must never be presented as though it
were (milestone item 7's own instruction: "avoid making low-count
distributions appear statistically meaningful"). Below that floor, the
dimension is simply omitted from the result list, not padded with a
misleading entry.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass

from app.core.config import settings
from app.intelligence.enums import ConcentrationClassification
from app.intelligence.normalization import SEVERITY_ORDINAL
from app.models.safety_event import SafetyEvent

ENTERPRISE_CONCENTRATION_CALCULATION_VERSION = "enterprise-concentration-v1"

_SEVERITY_POOL_TYPES = ("INCIDENT", "NEAR_MISS")


@dataclass
class ConcentrationContributor:
    dimension: str  # "site" | "event_type" | "event_subtype" | "severity"
    key: str
    label: str
    count: int
    total: int
    percentage: float
    classification: str  # ConcentrationClassification value
    calculation_version: str = ENTERPRISE_CONCENTRATION_CALCULATION_VERSION


def _classify_share(percentage: float) -> ConcentrationClassification:
    if percentage >= settings.ENTERPRISE_CONCENTRATION_HIGH_THRESHOLD:
        return ConcentrationClassification.HIGH
    if percentage >= settings.ENTERPRISE_CONCENTRATION_MODERATE_THRESHOLD:
        return ConcentrationClassification.MODERATE
    return ConcentrationClassification.LOW


def _rank(
    dimension: str, counter: Counter, total: int, *, labels: dict[str, str] | None = None
) -> list[ConcentrationContributor]:
    if total < settings.ENTERPRISE_CONCENTRATION_MIN_POPULATION:
        return []
    labels = labels or {}
    contributors = [
        ConcentrationContributor(
            dimension=dimension,
            key=key,
            label=labels.get(key, key),
            count=count,
            total=total,
            percentage=round(count / total, 4),
            classification=_classify_share(count / total).value,
        )
        for key, count in counter.items()
    ]
    contributors.sort(key=lambda c: (-c.count, c.key))
    return contributors


def compute_concentration(
    events: list[SafetyEvent],
    *,
    scope: str,
    site_labels: dict[uuid.UUID, str] | None = None,
) -> list[ConcentrationContributor]:
    """Pure function. `scope` is `"organization"` or `"site"` — the
    `site` dimension is only computed for `"organization"` (see module
    docstring). `site_labels` (an `{id: name}` map, one query fetched
    once by the caller — never per-contributor) fills in a human-
    readable site name; a site id with no entry falls back to its raw
    UUID string rather than failing."""
    site_labels = site_labels or {}
    results: list[ConcentrationContributor] = []

    incidents = [e for e in events if e.event_type == "INCIDENT"]

    if scope == "organization":
        site_counter = Counter(str(e.site_id) for e in incidents if e.site_id is not None)
        results.extend(
            _rank(
                "site",
                site_counter,
                len(incidents),
                labels={str(sid): name for sid, name in site_labels.items()},
            )
        )

    subtype_counter = Counter(e.event_subtype for e in incidents if e.event_subtype)
    results.extend(_rank("event_subtype", subtype_counter, len(incidents)))

    severity_pool = [e for e in events if e.event_type in _SEVERITY_POOL_TYPES and e.severity in SEVERITY_ORDINAL]
    severity_counter = Counter(e.severity for e in severity_pool)
    results.extend(_rank("severity", severity_counter, len(severity_pool)))

    type_counter = Counter(e.event_type for e in events)
    results.extend(_rank("event_type", type_counter, len(events)))

    return results
