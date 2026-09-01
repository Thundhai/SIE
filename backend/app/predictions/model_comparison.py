"""Controlled model comparison — Model Validation & Governance v0.1,
items 8-10, 45-46.

    TrainingExample[] (one dataset)
        -> chronological_split()                              -- computed ONCE
        -> Model A: LogisticRegressionModel.fit(train)         -- same train split
        -> Model B: GradientBoostingModel.fit(train)           -- same train split
        -> evaluate both on the same validation/test splits
        -> ModelComparisonReport (never a winner -- see below)

**Both models see the identical feature set, labels, training/validation/
test windows, temporal split, and evaluation methodology (item 8).**
`compare_models()` calls `chronological_split()` exactly once and reuses
its `train`/`validation`/`test` partitions for both models — there is no
code path in this module where Model A and Model B are compared against
different data.

**Never automatically selects the model with the highest single metric
(items 10, 45-46).** `compare_models()` returns a report: a metrics
table, false positive/negative counts, calibration, stability, and
(item 41-style) sufficient/limited-data breakdowns for each model side by
side — and stops there. There is no `pick_best_model()` function in this
codebase. `app/predictions/governance.py::generate_validation_report()`
turns *one* model's evidence into an APPROVE/REJECT/REVIEW
recommendation for a human reviewer to weigh — comparing two candidates
and choosing between them is a human decision this module deliberately
does not make.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.predictions.calibration import CalibrationResult, validate_calibration
from app.predictions.dataset import TrainingExample
from app.predictions.error_analysis import ErrorAnalysisReport, analyze_errors
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
from app.predictions.metrics import (
    EvaluationResult,
    GroupedEvaluationResult,
    evaluate_by_data_quality,
)
from app.predictions.stability import (
    StabilityReport,
    analyze_stability_by_data_quality,
    analyze_stability_by_site,
    analyze_stability_over_time,
)
from app.predictions.temporal_split import TemporalSplit, chronological_split
from app.predictions.threshold import DEFAULT_DECISION_THRESHOLD


@dataclass
class ModelEvaluationSummary:
    model_type: str
    validation_metrics: GroupedEvaluationResult
    test_metrics: GroupedEvaluationResult
    calibration: CalibrationResult
    error_analysis: ErrorAnalysisReport
    stability_over_time: StabilityReport
    stability_by_site: StabilityReport
    stability_by_data_quality: StabilityReport
    sufficient_data_coverage: float  # fraction of test examples with SUFFICIENT_DATA quality -- see module docstring caveat
    preprocessor_params: dict
    model_params: dict


@dataclass
class ModelComparisonReport:
    split: TemporalSplit
    logistic_regression: ModelEvaluationSummary
    gradient_boosting: ModelEvaluationSummary
    threshold_used: float


def _sufficient_data_coverage(examples: list[TrainingExample]) -> float:
    if not examples:
        return 0.0
    return sum(1 for e in examples if e.data_quality == "SUFFICIENT_DATA") / len(examples)


def _evaluate_model(
    *, model_type: str, examples_validation: list[TrainingExample], scores_validation: list[float],
    examples_test: list[TrainingExample], scores_test: list[float], model_version: str, threshold: float,
    preprocessor_params: dict, model_params: dict,
) -> ModelEvaluationSummary:
    y_validation = [e.label for e in examples_validation]
    y_test = [e.label for e in examples_test]

    return ModelEvaluationSummary(
        model_type=model_type,
        validation_metrics=evaluate_by_data_quality(
            y_validation, scores_validation, [e.data_quality for e in examples_validation], threshold=threshold
        ),
        test_metrics=evaluate_by_data_quality(
            y_test, scores_test, [e.data_quality for e in examples_test], threshold=threshold
        ),
        calibration=validate_calibration(y_test, scores_test),
        error_analysis=analyze_errors(examples_test, scores_test, model_version=model_version, threshold=threshold),
        stability_over_time=analyze_stability_over_time(examples_test, scores_test),
        stability_by_site=analyze_stability_by_site(examples_test, scores_test),
        stability_by_data_quality=analyze_stability_by_data_quality(examples_test, scores_test),
        sufficient_data_coverage=_sufficient_data_coverage(examples_test),
        preprocessor_params=preprocessor_params,
        model_params=model_params,
    )


def compare_models(
    examples: list[TrainingExample],
    *,
    threshold: float = DEFAULT_DECISION_THRESHOLD,
    lr_l2: float = DEFAULT_L2,
    lr_learning_rate: float = DEFAULT_LEARNING_RATE,
    lr_epochs: int = DEFAULT_EPOCHS,
    gb_n_estimators: int = DEFAULT_N_ESTIMATORS,
    gb_max_depth: int = DEFAULT_MAX_DEPTH,
    gb_learning_rate: float = GB_DEFAULT_LEARNING_RATE,
) -> ModelComparisonReport:
    """Fits both Model A (Logistic Regression) and Model B (Gradient
    Boosting) on one `chronological_split()` of `examples` and evaluates
    both on the identical validation/test partitions — see module
    docstring for why this is the only comparison shape this codebase
    implements."""
    split = chronological_split(examples)

    preprocessor = FeaturePreprocessor().fit([e.feature_vector for e in split.train])
    X_train = preprocessor.transform([e.feature_vector for e in split.train])
    X_validation = preprocessor.transform([e.feature_vector for e in split.validation])
    X_test = preprocessor.transform([e.feature_vector for e in split.test])
    y_train = [e.label for e in split.train]

    lr_model = LogisticRegressionModel(l2=lr_l2, learning_rate=lr_learning_rate, epochs=lr_epochs).fit(X_train, y_train)
    lr_summary = _evaluate_model(
        model_type="logistic_regression",
        examples_validation=split.validation, scores_validation=[lr_model.predict_proba(x) for x in X_validation],
        examples_test=split.test, scores_test=[lr_model.predict_proba(x) for x in X_test],
        model_version="comparison-candidate", threshold=threshold,
        preprocessor_params=preprocessor.to_params(), model_params=lr_model.to_params(),
    )

    gb_model = GradientBoostingModel(n_estimators=gb_n_estimators, max_depth=gb_max_depth, learning_rate=gb_learning_rate).fit(X_train, y_train)
    gb_summary = _evaluate_model(
        model_type="gradient_boosting",
        examples_validation=split.validation, scores_validation=[gb_model.predict_proba(x) for x in X_validation],
        examples_test=split.test, scores_test=[gb_model.predict_proba(x) for x in X_test],
        model_version="comparison-candidate", threshold=threshold,
        preprocessor_params=preprocessor.to_params(), model_params=gb_model.to_params(),
    )

    return ModelComparisonReport(
        split=split, logistic_regression=lr_summary, gradient_boosting=gb_summary, threshold_used=threshold,
    )


def comparison_table(report: ModelComparisonReport) -> list[dict]:
    """The milestone's own example table shape (item 10) — one row per
    model, test-split `overall` metrics only; the full breakdown
    (sufficient/limited-data, calibration, stability, errors) stays on
    `ModelComparisonReport` itself for a reviewer who wants it."""
    rows = []
    for summary in (report.logistic_regression, report.gradient_boosting):
        overall: EvaluationResult = summary.test_metrics.overall
        rows.append(
            {
                "model": summary.model_type,
                "precision": overall.precision,
                "recall": overall.recall,
                "pr_auc": overall.pr_auc,
                "roc_auc": overall.roc_auc,
                "false_positives": overall.confusion.false_positive,
                "false_negatives": overall.confusion.false_negative,
                "calibration_status": summary.calibration.status,
                "sufficient_data_coverage": summary.sufficient_data_coverage,
            }
        )
    return rows


__all__ = ["ModelComparisonReport", "ModelEvaluationSummary", "compare_models", "comparison_table"]
