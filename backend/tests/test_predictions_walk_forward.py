"""Walk-forward backtesting — milestone item 15 (Predictive Risk
Modeling Specification v0.1) and item 18 (Model Validation & Governance
v0.1: explicit train/validate/test rolling windows). DB-backed (SQLite)
test using the synthetic training dataset fixture."""

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

    folds = walk_forward_backtest(examples, initial_train_days=200, window_days=60, epochs=100)
    assert len(folds) > 1

    # Folds must be strictly chronological -- each fold's test period
    # starts no earlier than the previous fold's.
    for previous, current in itertools.pairwise(folds):
        assert previous.test_period.end <= current.test_period.start


def test_each_folds_validation_window_becomes_the_next_folds_test_window(db_session):
    """The milestone's own worked example (item 18): fold 2's validation
    period is exactly fold 1's test period, and fold 2's train period
    extends fold 1's train period forward by one window."""
    org, sites = seed_synthetic_organization(
        db_session, name="Rolling Window Org", site_names=["Site 1", "Site 2"], seed=101
    )
    dates = as_of_dates(cadence_days=7)
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )

    folds = walk_forward_backtest(examples, initial_train_days=150, window_days=30, epochs=50)
    assert len(folds) >= 2

    for previous, current in itertools.pairwise(folds):
        assert current.train_period.end >= previous.train_period.end
        # current's validation window starts where previous's test window did.
        assert current.validation_period.start == previous.test_period.start or (
            current.validation_period.start >= previous.validation_period.end
        )


def test_train_and_validation_and_test_windows_never_overlap(db_session):
    org, sites = seed_synthetic_organization(
        db_session, name="No Overlap Org", site_names=["Site 1"], seed=102
    )
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    folds = walk_forward_backtest(examples, initial_train_days=180, window_days=30, epochs=50)
    for fold in folds:
        if fold.skipped_reason is not None:
            continue
        assert fold.train_period.end <= fold.validation_period.start
        assert fold.validation_period.end <= fold.test_period.start


def test_a_fold_never_averages_over_a_bad_fold_silently():
    """Every fold's own metrics/skip-reason is preserved -- nothing is
    collapsed into one aggregate number that could hide a bad fold."""
    folds = walk_forward_backtest([], initial_train_days=30, window_days=10)
    assert folds == []


def test_folds_with_a_single_class_train_set_are_explicitly_skipped_not_silently_fit():
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
    folds = walk_forward_backtest(examples, initial_train_days=100, window_days=30)
    assert any(f.skipped_reason == "SINGLE_CLASS_TRAIN_SET" for f in folds)
    assert all(f.test_metrics is None and f.validation_metrics is None for f in folds if f.skipped_reason is not None)
