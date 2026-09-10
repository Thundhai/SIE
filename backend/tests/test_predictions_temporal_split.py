"""Chronological train/validation/test splitting — milestone item 14.
Pure unit tests over `chronological_split()` using bare `TrainingExample`
instances (no database)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.predictions.dataset import TrainingExample
from app.predictions.temporal_split import (
    MIN_DISTINCT_AS_OF_DATES,
    InsufficientTemporalCoverageError,
    chronological_split,
)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _example(days: int, label: int = 0) -> TrainingExample:
    return TrainingExample(
        entity_type="site", entity_id=uuid.uuid4(), organization_id=uuid.uuid4(),
        as_of=BASE + timedelta(days=days), feature_snapshot_id=uuid.uuid4(),
        feature_vector={}, feature_set_version="v1", data_quality="SUFFICIENT_DATA",
        label=label, label_definition_version="v1", horizon_days=30, supporting_event_ids=[],
    )


def test_split_is_strictly_chronological_never_random():
    examples = [_example(d) for d in range(10)]
    split = chronological_split(examples, train_fraction=0.6, validation_fraction=0.2)
    assert max(e.as_of for e in split.train) <= min(e.as_of for e in split.validation)
    assert max(e.as_of for e in split.validation) <= min(e.as_of for e in split.test)
    assert len(split.train) + len(split.validation) + len(split.test) == len(examples)


def test_all_examples_sharing_one_as_of_land_in_the_same_partition():
    """No `as_of` date is ever split across two partitions -- multiple
    sites sharing one as_of must never end up straddling train/test."""
    examples = [_example(d) for d in range(10) for _ in range(3)]  # 3 sites per as_of
    split = chronological_split(examples)
    train_dates = {e.as_of for e in split.train}
    val_dates = {e.as_of for e in split.validation}
    test_dates = {e.as_of for e in split.test}
    assert not (train_dates & val_dates)
    assert not (val_dates & test_dates)
    assert not (train_dates & test_dates)


def test_period_bounds_reflect_each_partitions_actual_as_of_range():
    examples = [_example(d) for d in range(10)]
    split = chronological_split(examples)
    assert split.train_period.start <= split.train_period.end
    assert split.train_period.end <= split.validation_period.start
    assert split.validation_period.end <= split.test_period.start


def test_insufficient_distinct_as_of_dates_raises_rather_than_returning_an_empty_partition():
    examples = [_example(0), _example(1)]
    assert len(examples) < MIN_DISTINCT_AS_OF_DATES
    with pytest.raises(InsufficientTemporalCoverageError):
        chronological_split(examples)


def test_invalid_fractions_are_rejected():
    examples = [_example(d) for d in range(10)]
    with pytest.raises(ValueError):
        chronological_split(examples, train_fraction=0.7, validation_fraction=0.4)
    with pytest.raises(ValueError):
        chronological_split(examples, train_fraction=0, validation_fraction=0.2)
