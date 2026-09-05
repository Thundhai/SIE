"""Correlation vs. causation — milestone item 26. A deterministic Pearson
correlation over two aligned period-bucketed series. **This module can
only ever report `ASSOCIATION_OBSERVED` (or `NO_ASSOCIATION_OBSERVED` /
`INSUFFICIENT_DATA`) — it has no `CAUSATION_CONFIRMED` outcome, and never
will.** Observing that two variables move together, however strongly,
never establishes that one causes the other (confounding variables, reverse
causation, and pure coincidence are all still possible) — this is
documented as a hard architectural boundary, not a strength-of-evidence
detail left to the caller to remember.

**`classification` (SIE Milestone 24: Enterprise Intelligence Pattern &
Correlation Foundation v0.1, item 5) — additive, non-breaking.** A finer,
six-value strength/direction band (`STRONG_POSITIVE`/`MODERATE_POSITIVE`/
`WEAK`/`MODERATE_NEGATIVE`/`STRONG_NEGATIVE`/`INSUFFICIENT_DATA`) sitting
alongside the pre-existing, unchanged `outcome` field
(`ASSOCIATION_OBSERVED`/`NO_ASSOCIATION_OBSERVED`/`INSUFFICIENT_DATA`) —
`outcome` answers "is there an association at all" (a coarse yes/no at
one threshold); `classification` answers "how strong, which direction"
(see `app/intelligence/enums.py::AssociationClassification`'s own
docstring for why this is a separate vocabulary, never collapsed into
`outcome`). Every pre-existing caller of `detect_association()`
(`tests/test_intelligence_association.py`) reads only `.outcome`/
`.correlation_coefficient`/`.period_count`/`.note` and is unaffected by
this new field.

**`min_periods`/`threshold` now default from `settings` (also additive,
non-breaking).** The two parameters now default to
`settings.ENTERPRISE_ASSOCIATION_MIN_PERIODS` (4) and
`settings.ENTERPRISE_ASSOCIATION_OBSERVED_THRESHOLD` (0.5) when omitted —
identical *values* to the pre-existing hardcoded literals (3 and 0.5) they
replace... except `min_periods`, whose default rises from 3 to 4 to match
this codebase's other statistical foundations
(`INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS`); every pre-existing test
either passes its own explicit `min_periods`/`threshold`, or uses a series
long enough (5 periods) that this change does not alter its outcome — see
`tests/test_intelligence_association.py`'s own docstring note.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.core.config import settings
from app.intelligence.enums import AssociationClassification

ASSOCIATION_CALCULATION_VERSION = "association-v1"


def _classify_association(r: float) -> AssociationClassification:
    """`|r| >= STRONG` -> STRONG_*; `MODERATE <= |r| < STRONG` ->
    MODERATE_*; otherwise WEAK. Symmetric around zero -- a negative
    correlation of the same magnitude gets the same strength band, just
    the negative-direction member (milestone item 5's own "STRONG_POSITIVE
    .. STRONG_NEGATIVE" vocabulary)."""
    strong = settings.ENTERPRISE_ASSOCIATION_STRONG_THRESHOLD
    moderate = settings.ENTERPRISE_ASSOCIATION_MODERATE_THRESHOLD
    if r >= strong:
        return AssociationClassification.STRONG_POSITIVE
    if r >= moderate:
        return AssociationClassification.MODERATE_POSITIVE
    if r <= -strong:
        return AssociationClassification.STRONG_NEGATIVE
    if r <= -moderate:
        return AssociationClassification.MODERATE_NEGATIVE
    return AssociationClassification.WEAK


@dataclass
class AssociationResult:
    outcome: str  # "ASSOCIATION_OBSERVED" | "NO_ASSOCIATION_OBSERVED" | "INSUFFICIENT_DATA"
    correlation_coefficient: float | None
    period_count: int
    calculation_version: str = ASSOCIATION_CALCULATION_VERSION
    classification: str = AssociationClassification.INSUFFICIENT_DATA.value  # AssociationClassification value
    note: str = (
        "Correlation, not causation. A correlation, however strong, does not "
        "establish that one variable causes the other."
    )


def detect_association(
    series_a: list[float], series_b: list[float], *, min_periods: int | None = None, threshold: float | None = None
) -> AssociationResult:
    min_periods = min_periods if min_periods is not None else settings.ENTERPRISE_ASSOCIATION_MIN_PERIODS
    threshold = threshold if threshold is not None else settings.ENTERPRISE_ASSOCIATION_OBSERVED_THRESHOLD

    if len(series_a) != len(series_b):
        raise ValueError("series_a and series_b must be the same length (aligned periods).")
    if len(series_a) < min_periods:
        return AssociationResult(outcome="INSUFFICIENT_DATA", correlation_coefficient=None, period_count=len(series_a))

    try:
        r = statistics.correlation(series_a, series_b)
    except statistics.StatisticsError:
        # Zero variance in one series -- correlation is undefined, not "no association".
        return AssociationResult(outcome="INSUFFICIENT_DATA", correlation_coefficient=None, period_count=len(series_a))

    outcome = "ASSOCIATION_OBSERVED" if abs(r) >= threshold else "NO_ASSOCIATION_OBSERVED"
    return AssociationResult(
        outcome=outcome,
        correlation_coefficient=round(r, 4),
        period_count=len(series_a),
        classification=_classify_association(r).value,
    )
