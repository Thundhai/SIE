"""Chronological train/validation/test splitting — milestone item 14.

**Never a random split.** A random row-level split would let a model
trained on `as_of=2026-03-01` examples be validated against
`as_of=2026-01-15` examples — information from the model's own future
(relative to some validation rows) would have leaked into training. This
module splits on the sorted, *distinct* set of `as_of` dates instead of
on row count, so no `as_of` date is ever split across two partitions
(every example sharing one `as_of` lands in the same partition) and the
partitions are strictly time-ordered: every training `as_of` <= every
validation `as_of` <= every test `as_of`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.predictions.dataset import TrainingExample

DEFAULT_TRAIN_FRACTION = 0.6
DEFAULT_VALIDATION_FRACTION = 0.2
# test fraction is whatever remains

MIN_DISTINCT_AS_OF_DATES = 3
"""Fewer distinct `as_of` dates than this and a chronological 3-way split
is not meaningful (one or more partitions would be empty) -- callers get
an explicit `InsufficientTemporalCoverageError`, never a silently-empty
validation/test set."""


class InsufficientTemporalCoverageError(ValueError):
    """Raised instead of returning a degenerate (empty) split."""


@dataclass
class PeriodBounds:
    start: date
    end: date


@dataclass
class TemporalSplit:
    train: list[TrainingExample]
    validation: list[TrainingExample]
    test: list[TrainingExample]
    train_period: PeriodBounds
    validation_period: PeriodBounds
    test_period: PeriodBounds


def _period_bounds(examples: list[TrainingExample]) -> PeriodBounds:
    dates = [e.as_of.date() if isinstance(e.as_of, datetime) else e.as_of for e in examples]
    return PeriodBounds(start=min(dates), end=max(dates))


def chronological_split(
    examples: list[TrainingExample],
    *,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
) -> TemporalSplit:
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("train_fraction and validation_fraction must each be in (0, 1)")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train_fraction + validation_fraction must leave a non-empty test fraction")

    distinct_dates = sorted({e.as_of for e in examples})
    if len(distinct_dates) < MIN_DISTINCT_AS_OF_DATES:
        raise InsufficientTemporalCoverageError(
            f"Need at least {MIN_DISTINCT_AS_OF_DATES} distinct as_of dates for a "
            f"train/validation/test split; got {len(distinct_dates)}."
        )

    n = len(distinct_dates)
    train_end_idx = max(1, round(n * train_fraction))
    validation_end_idx = max(train_end_idx + 1, round(n * (train_fraction + validation_fraction)))
    validation_end_idx = min(validation_end_idx, n - 1)  # leave >=1 date for test

    train_dates = set(distinct_dates[:train_end_idx])
    validation_dates = set(distinct_dates[train_end_idx:validation_end_idx])
    test_dates = set(distinct_dates[validation_end_idx:])

    if not train_dates or not validation_dates or not test_dates:
        raise InsufficientTemporalCoverageError(
            "Computed split produced an empty partition -- increase temporal coverage "
            "or adjust train_fraction/validation_fraction."
        )

    train = [e for e in examples if e.as_of in train_dates]
    validation = [e for e in examples if e.as_of in validation_dates]
    test = [e for e in examples if e.as_of in test_dates]

    return TemporalSplit(
        train=train,
        validation=validation,
        test=test,
        train_period=_period_bounds(train),
        validation_period=_period_bounds(validation),
        test_period=_period_bounds(test),
    )
