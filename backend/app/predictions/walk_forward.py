"""Walk-forward backtesting — milestone item 15 (Predictive Risk
Modeling Specification v0.1), extended by Model Validation & Governance
v0.1 item 18 into an explicit train/validate/test rolling-window shape:

    Train:       [start, cutoff_1]
    Validate:    [cutoff_1, cutoff_1 + window]
    Test:        [cutoff_1 + window, cutoff_1 + 2*window]

    (advance: cutoff_2 = cutoff_1 + window)

    Train:       [start, cutoff_2]                 (= [start, cutoff_1 + window])
    Validate:    [cutoff_2, cutoff_2 + window]      (= fold 1's own test window)
    Test:        [cutoff_2 + window, cutoff_2 + 2*window]

Each fold's validation window becomes the next fold's own held-out test
window from the fold *before* it, and the training window only ever
grows forward in time — the exact shape the milestone's own worked
example describes. **Never allows future information into a training
window**: a fold's `train` partition is always `[start, cutoff]`, its
`validation`/`test` partitions always start strictly after `cutoff`, and
`chronological_split()`-style as_of-date partitioning (never a random
split) is used throughout — see `app/predictions/temporal_split.py`.

**This harness is implemented to prove the architecture works, not to
chase a benchmark number** (per the milestone's own instruction): nothing
here tunes hyperparameters against the backtest results, and every fold's
raw metrics are returned individually, never averaged into a single
number that would hide a fold that performed badly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.predictions.dataset import TrainingExample
from app.predictions.logistic_regression import (
    DEFAULT_EPOCHS,
    DEFAULT_L2,
    DEFAULT_LEARNING_RATE,
    FeaturePreprocessor,
    LogisticRegressionModel,
)
from app.predictions.metrics import EvaluationResult, evaluate
from app.predictions.temporal_split import PeriodBounds

DEFAULT_INITIAL_TRAIN_DAYS = 180
DEFAULT_WINDOW_DAYS = 30


@dataclass
class WalkForwardFold:
    fold_index: int
    train_period: PeriodBounds
    validation_period: PeriodBounds
    test_period: PeriodBounds
    train_size: int
    validation_size: int
    test_size: int
    validation_metrics: EvaluationResult | None
    test_metrics: EvaluationResult | None
    skipped_reason: str | None = None


def _bounds(examples: list[TrainingExample], fallback):
    if not examples:
        return PeriodBounds(start=fallback.date(), end=fallback.date())
    dates = [e.as_of.date() for e in examples]
    return PeriodBounds(start=min(dates), end=max(dates))


def walk_forward_backtest(
    examples: list[TrainingExample],
    *,
    initial_train_days: int = DEFAULT_INITIAL_TRAIN_DAYS,
    window_days: int = DEFAULT_WINDOW_DAYS,
    l2: float = DEFAULT_L2,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    epochs: int = DEFAULT_EPOCHS,
) -> list[WalkForwardFold]:
    if not examples:
        return []

    sorted_examples = sorted(examples, key=lambda e: e.as_of)
    start = sorted_examples[0].as_of
    end = sorted_examples[-1].as_of

    folds: list[WalkForwardFold] = []
    fold_index = 0
    cutoff = start + timedelta(days=initial_train_days)

    while cutoff + timedelta(days=window_days) < end:
        validation_end = cutoff + timedelta(days=window_days)
        test_end = validation_end + timedelta(days=window_days)

        train = [e for e in sorted_examples if e.as_of <= cutoff]
        validation = [e for e in sorted_examples if cutoff < e.as_of <= validation_end]
        test = [e for e in sorted_examples if validation_end < e.as_of <= test_end]
        fold_index += 1

        if not train or not validation or not test or len({e.label for e in train}) < 2:
            folds.append(
                WalkForwardFold(
                    fold_index=fold_index,
                    train_period=_bounds(train, cutoff),
                    validation_period=_bounds(validation, validation_end),
                    test_period=_bounds(test, test_end),
                    train_size=len(train), validation_size=len(validation), test_size=len(test),
                    validation_metrics=None, test_metrics=None,
                    skipped_reason="INSUFFICIENT_DATA_FOR_FOLD" if (not train or not validation or not test) else "SINGLE_CLASS_TRAIN_SET",
                )
            )
            cutoff = validation_end
            continue

        preprocessor = FeaturePreprocessor().fit([e.feature_vector for e in train])
        X_train = preprocessor.transform([e.feature_vector for e in train])
        y_train = [e.label for e in train]
        model = LogisticRegressionModel(l2=l2, learning_rate=learning_rate, epochs=epochs).fit(X_train, y_train)

        X_validation = preprocessor.transform([e.feature_vector for e in validation])
        validation_scores = [model.predict_proba(x) for x in X_validation]
        X_test = preprocessor.transform([e.feature_vector for e in test])
        test_scores = [model.predict_proba(x) for x in X_test]

        folds.append(
            WalkForwardFold(
                fold_index=fold_index,
                train_period=_bounds(train, cutoff),
                validation_period=_bounds(validation, validation_end),
                test_period=_bounds(test, test_end),
                train_size=len(train), validation_size=len(validation), test_size=len(test),
                validation_metrics=evaluate([e.label for e in validation], validation_scores),
                test_metrics=evaluate([e.label for e in test], test_scores),
            )
        )
        cutoff = validation_end

    return folds
