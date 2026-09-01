"""Walk-forward backtesting — milestone item 15.

A single chronological train/validation/test split (`temporal_split.py`)
proves the model generalizes to *one* future period. Walk-forward
backtesting proves it generalizes across *many* rolling future periods —
train on everything up to a cutoff, evaluate on the next slice, advance
the cutoff, repeat — which is a materially stronger, and more honest,
signal for a system meant to keep predicting into an open-ended future.

**This harness is implemented to prove the architecture works, not to
chase a benchmark number** (per the milestone's own instruction): nothing
here tunes hyperparameters against the backtest results, and every fold's
raw metrics are returned, never averaged into a single number that would
hide a fold that performed badly.

    distinct as_of dates, sorted
        -> fold 1: train on [start, cutoff_1], test on (cutoff_1, cutoff_1+step]
        -> fold 2: train on [start, cutoff_2], test on (cutoff_2, cutoff_2+step]
        -> ... (cutoff_i = cutoff_1 + (i-1)*step)
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
DEFAULT_STEP_DAYS = 30


@dataclass
class WalkForwardFold:
    fold_index: int
    train_period: PeriodBounds
    test_period: PeriodBounds
    train_size: int
    test_size: int
    metrics: EvaluationResult | None
    skipped_reason: str | None = None


def _bounds(examples: list[TrainingExample]) -> PeriodBounds:
    dates = [e.as_of.date() for e in examples]
    return PeriodBounds(start=min(dates), end=max(dates))


def walk_forward_backtest(
    examples: list[TrainingExample],
    *,
    initial_train_days: int = DEFAULT_INITIAL_TRAIN_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
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

    while cutoff < end:
        test_end = cutoff + timedelta(days=step_days)
        train = [e for e in sorted_examples if e.as_of <= cutoff]
        test = [e for e in sorted_examples if cutoff < e.as_of <= test_end]
        fold_index += 1

        if not train or not test or len({e.label for e in train}) < 2:
            folds.append(
                WalkForwardFold(
                    fold_index=fold_index,
                    train_period=_bounds(train) if train else PeriodBounds(start=cutoff.date(), end=cutoff.date()),
                    test_period=_bounds(test) if test else PeriodBounds(start=test_end.date(), end=test_end.date()),
                    train_size=len(train),
                    test_size=len(test),
                    metrics=None,
                    skipped_reason="INSUFFICIENT_DATA_FOR_FOLD" if (not train or not test) else "SINGLE_CLASS_TRAIN_SET",
                )
            )
            cutoff = test_end
            continue

        preprocessor = FeaturePreprocessor().fit([e.feature_vector for e in train])
        X_train = preprocessor.transform([e.feature_vector for e in train])
        y_train = [e.label for e in train]
        model = LogisticRegressionModel(l2=l2, learning_rate=learning_rate, epochs=epochs).fit(X_train, y_train)

        X_test = preprocessor.transform([e.feature_vector for e in test])
        y_test = [e.label for e in test]
        scores = [model.predict_proba(x) for x in X_test]

        folds.append(
            WalkForwardFold(
                fold_index=fold_index,
                train_period=_bounds(train),
                test_period=_bounds(test),
                train_size=len(train),
                test_size=len(test),
                metrics=evaluate(y_test, scores),
            )
        )
        cutoff = test_end

    return folds
