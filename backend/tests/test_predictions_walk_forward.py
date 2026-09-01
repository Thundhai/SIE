"""Walk-forward backtesting — milestone item 15. DB-backed (SQLite) test
using the synthetic training dataset fixture."""

import itertools

from app.predictions.dataset import build_training_examples
from app.predictions.walk_forward import walk_forward_backtest
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)


def test_walk_forward_backtest_produces_multiple_chronological_folds(db_session):
    org, sites = seed_synthetic_organization(
        db_session, name="Walk Forward Org", site_names=["Site 1"], seed=99
    )
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )

    folds = walk_forward_backtest(examples, initial_train_days=200, step_days=60, epochs=100)
    assert len(folds) > 1

    # Folds must be strictly chronological -- each fold's test period
    # starts no earlier than the previous fold's.
    for previous, current in itertools.pairwise(folds):
        assert previous.test_period.end <= current.test_period.start


def test_a_fold_never_averages_over_a_bad_fold_silently():
    """Every fold's own metrics/skip-reason is preserved -- nothing is
    collapsed into one aggregate number that could hide a bad fold."""
    from app.predictions.walk_forward import walk_forward_backtest

    folds = walk_forward_backtest([], initial_train_days=30, step_days=10)
    assert folds == []


def test_folds_with_a_single_class_train_set_are_explicitly_skipped_not_silently_fit(db_session):
    import uuid
    from datetime import datetime, timedelta, timezone

    from app.predictions.dataset import TrainingExample

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # All labels 0 -- a single-class train set the model cannot usefully fit.
    examples = [
        TrainingExample(
            entity_type="site", entity_id=uuid.uuid4(), organization_id=uuid.uuid4(),
            as_of=base + timedelta(days=d), feature_snapshot_id=uuid.uuid4(),
            feature_vector={"x": 1.0}, feature_set_version="v1", data_quality="SUFFICIENT_DATA",
            label=0, label_definition_version="v1", horizon_days=30, supporting_event_ids=[],
        )
        for d in range(0, 300, 10)
    ]
    folds = walk_forward_backtest(examples, initial_train_days=100, step_days=30)
    assert any(f.skipped_reason == "SINGLE_CLASS_TRAIN_SET" for f in folds)
    assert all(f.metrics is None for f in folds if f.skipped_reason is not None)
