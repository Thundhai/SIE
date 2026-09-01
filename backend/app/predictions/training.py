"""Training orchestration — composes every other module in this package
into one call: `dataset -> temporal_split -> fit -> evaluate -> register`.

**Milestone item 48 — the boundary this module exists inside of:**
"Unless necessary to prove the architecture, DO NOT train a production
predictive model in this milestone." `train_baseline_model()` exists
*only* to prove the full pipeline is wired correctly end to end — the
resulting `ModelRegistryEntry` is always created with `status=TRAINED`
(never auto-promoted, see `model_registry.py`) and its `notes` field is
always stamped with the caller-overridable-but-defaulted
`PROTOTYPE_MODEL_LABEL` below. **Nothing in this codebase describes a
model trained by this function as production predictive intelligence.**

This module makes no network/file-system side effects beyond the
database writes `model_registry.create_model_entry()` itself performs —
it is safe to call repeatedly (each call trains a fresh model version;
see `model_registry.py`'s versioning).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.predictions import model_registry
from app.predictions.dataset import TrainingExample
from app.predictions.logistic_regression import (
    DEFAULT_EPOCHS,
    DEFAULT_L2,
    DEFAULT_LEARNING_RATE,
    FeaturePreprocessor,
    LogisticRegressionModel,
)
from app.predictions.metrics import evaluate_by_data_quality
from app.predictions.spec import (
    FEATURE_SET_VERSION,
    HORIZON_DAYS,
    LABEL_DEFINITION_VERSION,
    PREDICTION_ENTITY_TYPE,
    PREDICTION_TARGET_VERSION,
    TRAINING_DATA_VERSION,
)
from app.predictions.temporal_split import chronological_split

DEFAULT_MODEL_NAME = "site-elevated-risk-baseline"

PROTOTYPE_MODEL_LABEL = (
    "Prototype Model — Synthetic Data. Trained to prove the predictive "
    "modeling pipeline works end to end (dataset construction, temporal "
    "splitting, model fitting, evaluation, and registration). This model "
    "has NOT been validated against real-world data and must never be "
    "described as production predictive intelligence. See "
    "app/predictions/spec.py and the milestone's own item 48."
)


def _group_metrics(split_examples: list[TrainingExample], y_scores: list[float]) -> dict:
    y_true = [e.label for e in split_examples]
    data_qualities = [e.data_quality for e in split_examples]
    grouped = evaluate_by_data_quality(y_true, y_scores, data_qualities)

    def _as_dict(result):
        if result is None:
            return None
        return {
            "sample_size": result.sample_size,
            "positive_count": result.positive_count,
            "precision": result.precision,
            "recall": result.recall,
            "f1": result.f1,
            "pr_auc": result.pr_auc,
            "roc_auc": result.roc_auc,
            "brier_score": result.brier_score,
            "confusion": {
                "true_positive": result.confusion.true_positive,
                "false_positive": result.confusion.false_positive,
                "true_negative": result.confusion.true_negative,
                "false_negative": result.confusion.false_negative,
            },
        }

    return {
        "overall": _as_dict(grouped.overall),
        "sufficient_data": _as_dict(grouped.sufficient_data),
        "limited_data": _as_dict(grouped.limited_data),
    }


def train_baseline_model(
    db: Session,
    *,
    organization_id: uuid.UUID,
    examples: list[TrainingExample],
    model_name: str = DEFAULT_MODEL_NAME,
    l2: float = DEFAULT_L2,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    epochs: int = DEFAULT_EPOCHS,
    notes: str | None = None,
    user_id: uuid.UUID | None = None,
):
    """Trains one `LogisticRegressionModel` (milestone item 20's one
    allowed baseline) on `examples`, evaluates it on a chronological
    validation/test split, and registers it as a `TRAINED`
    `ModelRegistryEntry`. Every `example.organization_id` must equal
    `organization_id` — this function never mixes tenants into one
    training run (milestone item 43); a mismatched example raises
    `ValueError` rather than silently pooling data across organizations.
    """
    if any(e.organization_id != organization_id for e in examples):
        raise ValueError(
            "train_baseline_model() received training examples from another organization -- "
            "a model is always trained on exactly one organization's own data (milestone item 43)."
        )

    split = chronological_split(examples)

    preprocessor = FeaturePreprocessor().fit([e.feature_vector for e in split.train])
    X_train = preprocessor.transform([e.feature_vector for e in split.train])
    y_train = [e.label for e in split.train]
    model = LogisticRegressionModel(l2=l2, learning_rate=learning_rate, epochs=epochs).fit(X_train, y_train)

    train_scores = [model.predict_proba(x) for x in X_train]
    validation_scores = [model.predict_proba(x) for x in preprocessor.transform([e.feature_vector for e in split.validation])]
    test_scores = [model.predict_proba(x) for x in preprocessor.transform([e.feature_vector for e in split.test])]

    metrics = {
        "train": _group_metrics(split.train, train_scores),
        "validation": _group_metrics(split.validation, validation_scores),
        "test": _group_metrics(split.test, test_scores),
    }

    parameters = {
        "preprocessor": preprocessor.to_params(),
        "model": model.to_params(),
    }

    return model_registry.create_model_entry(
        db,
        organization_id=organization_id,
        model_name=model_name,
        model_type=model.to_params()["model_type"],
        entity_type=PREDICTION_ENTITY_TYPE,
        prediction_target_version=PREDICTION_TARGET_VERSION,
        label_definition_version=LABEL_DEFINITION_VERSION,
        feature_set_version=FEATURE_SET_VERSION,
        training_data_version=TRAINING_DATA_VERSION,
        horizon_days=HORIZON_DAYS,
        training_period_start=split.train_period.start,
        training_period_end=split.train_period.end,
        validation_period_start=split.validation_period.start,
        validation_period_end=split.validation_period.end,
        test_period_start=split.test_period.start,
        test_period_end=split.test_period.end,
        hyperparameters={"l2": l2, "learning_rate": learning_rate, "epochs": epochs},
        metrics=metrics,
        parameters=parameters,
        notes=notes or PROTOTYPE_MODEL_LABEL,
        user_id=user_id,
    )
