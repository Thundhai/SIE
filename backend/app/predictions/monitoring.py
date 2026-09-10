"""Prediction & model performance monitoring foundation — Model
Validation & Governance v0.1, items 26, 28.

**A simple service/API foundation, not a full MLOps platform** (item
26's own instruction) — every function here is a read-only query over
`predictions`/`prediction_outcomes` plus the existing
`app/predictions/metrics.py`/`calibration.py`, computed on demand.
Nothing here runs continuously, stores a rolling window in memory, or
introduces new infrastructure.

    compute_prediction_monitoring()      -- live serving health: volume,
                                             coverage, abstention, score
                                             distributions (item 26)
    compute_model_performance_monitoring() -- realized accuracy once
                                             outcomes have matured
                                             (item 28) -- see
                                             app/predictions/outcome_tracking.py
                                             for how outcomes get recorded;
                                             this only ever reads already-
                                             matured PredictionOutcome rows,
                                             never evaluates early itself.
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.models.prediction_outcome import PredictionOutcome
from app.predictions.calibration import CalibrationResult, validate_calibration
from app.predictions.enums import PredictionOutcome as PredictionOutcomeEnum
from app.predictions.metrics import EvaluationResult, evaluate
from app.predictions.threshold import DEFAULT_DECISION_THRESHOLD


@dataclass
class DistributionSummary:
    count: int
    mean: float | None
    stdev: float | None
    minimum: float | None
    maximum: float | None


def _distribution(values: list[float]) -> DistributionSummary:
    return DistributionSummary(
        count=len(values),
        mean=statistics.fmean(values) if values else None,
        stdev=statistics.pstdev(values) if len(values) > 1 else (0.0 if values else None),
        minimum=min(values) if values else None,
        maximum=max(values) if values else None,
    )


@dataclass
class PredictionMonitoringSummary:
    total_predictions: int
    predicted_count: int
    abstained_count: int
    abstention_rate: float | None
    abstention_reason_counts: dict[str, int] = field(default_factory=dict)
    data_quality_distribution: dict[str, int] = field(default_factory=dict)
    risk_category_distribution: dict[str, int] = field(default_factory=dict)
    risk_score_distribution: DistributionSummary | None = None
    probability_distribution: DistributionSummary | None = None
    model_version_counts: dict[str, int] = field(default_factory=dict)


def compute_prediction_monitoring(
    db: Session,
    *,
    organization_id: uuid.UUID,
    model_id: uuid.UUID | None = None,
    since: datetime | None = None,
) -> PredictionMonitoringSummary:
    query = select(Prediction).where(Prediction.organization_id == organization_id)
    if model_id is not None:
        query = query.where(Prediction.model_id == model_id)
    if since is not None:
        query = query.where(Prediction.prediction_time >= since)
    predictions = list(db.execute(query).scalars().all())

    total = len(predictions)
    predicted = [p for p in predictions if p.outcome == PredictionOutcomeEnum.PREDICTED.value]
    abstained = [p for p in predictions if p.outcome == PredictionOutcomeEnum.NO_PREDICTION.value]

    return PredictionMonitoringSummary(
        total_predictions=total,
        predicted_count=len(predicted),
        abstained_count=len(abstained),
        abstention_rate=(len(abstained) / total) if total else None,
        abstention_reason_counts=dict(Counter(p.abstention_reason for p in abstained if p.abstention_reason)),
        data_quality_distribution=dict(Counter(p.data_quality for p in predictions)),
        risk_category_distribution=dict(Counter(p.risk_category for p in predicted if p.risk_category)),
        risk_score_distribution=_distribution([p.risk_score for p in predicted if p.risk_score is not None]),
        probability_distribution=_distribution([p.probability for p in predicted if p.probability is not None]),
        model_version_counts=dict(Counter(p.model_version for p in predictions if p.model_version)),
    )


@dataclass
class ModelPerformanceMonitoringSummary:
    model_id: uuid.UUID
    matured_outcome_count: int
    metrics: EvaluationResult | None
    calibration: CalibrationResult | None
    missing_data_rate: float | None  # fraction of matured predictions whose data_quality was not GOOD


def compute_model_performance_monitoring(
    db: Session,
    *,
    organization_id: uuid.UUID,
    model_id: uuid.UUID,
    threshold: float = DEFAULT_DECISION_THRESHOLD,
) -> ModelPerformanceMonitoringSummary:
    """Reads only *already matured* outcomes (`PredictionOutcome.outcome_known
    == True`) — this function never itself decides a horizon has passed;
    see `app/predictions/outcome_tracking.py::evaluate_prediction_outcome()`
    for the one place that determination is made (milestone item 28: "do
    not evaluate a prediction before its outcome horizon has completed")."""
    rows = db.execute(
        select(PredictionOutcome, Prediction)
        .join(Prediction, PredictionOutcome.prediction_id == Prediction.id)
        .where(
            PredictionOutcome.organization_id == organization_id,
            PredictionOutcome.outcome_known.is_(True),
            Prediction.model_id == model_id,
        )
    ).all()

    if not rows:
        return ModelPerformanceMonitoringSummary(
            model_id=model_id, matured_outcome_count=0, metrics=None, calibration=None, missing_data_rate=None,
        )

    y_true = [outcome.actual_label for outcome, _prediction in rows]
    y_scores = [prediction.risk_score for _outcome, prediction in rows]
    data_qualities = [prediction.data_quality for _outcome, prediction in rows]

    return ModelPerformanceMonitoringSummary(
        model_id=model_id,
        matured_outcome_count=len(rows),
        metrics=evaluate(y_true, y_scores, threshold=threshold),
        calibration=validate_calibration(y_true, y_scores),
        missing_data_rate=sum(1 for q in data_qualities if q != "GOOD") / len(data_qualities),
    )


__all__ = [
    "DistributionSummary",
    "ModelPerformanceMonitoringSummary",
    "PredictionMonitoringSummary",
    "compute_model_performance_monitoring",
    "compute_prediction_monitoring",
]
