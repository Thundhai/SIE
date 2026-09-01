"""Correlation vs. causation — milestone item 26. A deterministic Pearson
correlation over two aligned period-bucketed series. **This module can
only ever report `ASSOCIATION_OBSERVED` (or `NO_ASSOCIATION_OBSERVED` /
`INSUFFICIENT_DATA`) — it has no `CAUSATION_CONFIRMED` outcome, and never
will.** Observing that two variables move together, however strongly,
never establishes that one causes the other (confounding variables, reverse
causation, and pure coincidence are all still possible) — this is
documented as a hard architectural boundary, not a strength-of-evidence
detail left to the caller to remember.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

ASSOCIATION_CALCULATION_VERSION = "association-v1"


@dataclass
class AssociationResult:
    outcome: str  # "ASSOCIATION_OBSERVED" | "NO_ASSOCIATION_OBSERVED" | "INSUFFICIENT_DATA"
    correlation_coefficient: float | None
    period_count: int
    calculation_version: str = ASSOCIATION_CALCULATION_VERSION
    note: str = (
        "Correlation, not causation. A correlation, however strong, does not "
        "establish that one variable causes the other."
    )


def detect_association(
    series_a: list[float], series_b: list[float], *, min_periods: int = 3, threshold: float = 0.5
) -> AssociationResult:
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
    return AssociationResult(outcome=outcome, correlation_coefficient=round(r, 4), period_count=len(series_a))
