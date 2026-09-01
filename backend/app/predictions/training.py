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
from app.predictions.calibration import validate_calibration
from app.predictions.dataset import TrainingExample
from app.predictions.gradient_boosting import (
    DEFAULT_LEARNING_RATE as GB_DEFAULT_LEARNING_RATE,
)
from app.predictions.gradient_boosting import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_N_ESTIMATORS,
    GradientBoostingModel,
)
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

SUPPORTED_MODEL_TYPES = ("logistic_regression", "gradient_boosting")

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


def train_model(
    db: Session,
    *,
    organization_id: uuid.UUID,
    examples: list[TrainingExample],
    model_type: str = "logistic_regression",
    model_name: str = DEFAULT_MODEL_NAME,
    dataset_version_id: uuid.UUID | None = None,
    hyperparameters: dict | None = None,
    notes: str | None = None,
    user_id: uuid.UUID | None = None,
):
    """Trains one model — Logistic Regression or Gradient Boosting
    (milestone items 8-9's two comparison candidates; `SUPPORTED_MODEL_TYPES`) —
    on `examples`, evaluates it on a chronological validation/test split,
    and registers it as a `TRAINED` `ModelRegistryEntry`. Every
    `example.organization_id` must equal `organization_id` — this
    function never mixes tenants into one training run (milestone item
    43); a mismatched example raises `ValueError` rather than silently
    pooling data across organizations.

    `hyperparameters` accepts only the named keyword this model type
    actually uses (`l2`/`learning_rate`/`epochs` for logistic regression;
    `n_estimators`/`max_depth`/`learning_rate` for gradient boosting) —
    an unrecognized key raises `TypeError` rather than being silently
    ignored.
    """
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise ValueError(f"Unsupported model_type {model_type!r} -- must be one of {SUPPORTED_MODEL_TYPES}.")
    if any(e.organization_id != organization_id for e in examples):
        raise ValueError(
            "train_model() received training examples from another organization -- "
            "a model is always trained on exactly one organization's own data (milestone item 43)."
        )

    split = chronological_split(examples)
    hyperparameters = dict(hyperparameters or {})

    preprocessor = FeaturePreprocessor().fit([e.feature_vector for e in split.train])
    X_train = preprocessor.transform([e.feature_vector for e in split.train])
    y_train = [e.label for e in split.train]

    if model_type == "gradient_boosting":
        chosen_hyperparameters = {
            "n_estimators": hyperparameters.pop("n_estimators", DEFAULT_N_ESTIMATORS),
            "max_depth": hyperparameters.pop("max_depth", DEFAULT_MAX_DEPTH),
            "learning_rate": hyperparameters.pop("learning_rate", GB_DEFAULT_LEARNING_RATE),
        }
        model = GradientBoostingModel(**chosen_hyperparameters)
    else:
        chosen_hyperparameters = {
            "l2": hyperparameters.pop("l2", DEFAULT_L2),
            "learning_rate": hyperparameters.pop("learning_rate", DEFAULT_LEARNING_RATE),
            "epochs": hyperparameters.pop("epochs", DEFAULT_EPOCHS),
        }
        model = LogisticRegressionModel(**chosen_hyperparameters)
    if hyperparameters:
        raise TypeError(f"Unrecognized hyperparameter(s) for {model_type}: {sorted(hyperparameters)}")
    model.fit(X_train, y_train)

    train_scores = [model.predict_proba(x) for x in X_train]
    validation_scores = [model.predict_proba(x) for x in preprocessor.transform([e.feature_vector for e in split.validation])]
    test_scores = [model.predict_proba(x) for x in preprocessor.transform([e.feature_vector for e in split.test])]

    # Calibration is checked here, once, on the held-out test split --
    # app/api/v1/model_governance.py's /validate endpoint reads this
    # stored status rather than needing the raw test scores again later
    # (milestone items 14-15).
    test_calibration = validate_calibration([e.label for e in split.test], test_scores)

    metrics = {
        "train": _group_metrics(split.train, train_scores),
        "validation": _group_metrics(split.validation, validation_scores),
        "test": _group_metrics(split.test, test_scores),
    }
    metrics["test"]["calibration"] = {
        "status": test_calibration.status,
        "expected_calibration_error": test_calibration.expected_calibration_error,
        "brier_score": test_calibration.brier_score,
        "sample_size": test_calibration.sample_size,
        "reason": test_calibration.reason,
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
        dataset_version_id=dataset_version_id,
        training_period_start=split.train_period.start,
        training_period_end=split.train_period.end,
        validation_period_start=split.validation_period.start,
        validation_period_end=split.validation_period.end,
        test_period_start=split.test_period.start,
        test_period_end=split.test_period.end,
        hyperparameters=chosen_hyperparameters,
        metrics=metrics,
        parameters=parameters,
        notes=notes or PROTOTYPE_MODEL_LABEL,
        user_id=user_id,
    )


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
    """Backward-compatible logistic-regression-only entry point — a thin
    wrapper over `train_model(model_type="logistic_regression")`. Kept
    because it is this package's original, still-used training call
    shape (Predictive Risk Modeling Specification v0.1, item 20)."""
    return train_model(
        db,
        organization_id=organization_id,
        examples=examples,
        model_type="logistic_regression",
        model_name=model_name,
        hyperparameters={"l2": l2, "learning_rate": learning_rate, "epochs": epochs},
        notes=notes,
        user_id=user_id,
    )
