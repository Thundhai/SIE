"""Prediction outcome tracking — Model Validation & Governance v0.1,
items 27-28.

    Prediction (outcome=PREDICTED, prediction_time, horizon_days)
        -> horizon matures (now >= prediction_time + horizon_days)
        -> app/predictions/labels.py::generate_label() -- the SAME
           canonical label definition training uses, not a second one
        -> PredictionOutcome(outcome_known=True, actual_label, outcome_event_ids)

**Never evaluated before the horizon completes (item 28's own
instruction, non-negotiable).** `evaluate_prediction_outcome()` returns
`None` — and persists nothing — for a prediction whose horizon has not
yet matured relative to `as_of_now`. There is no "early" or "partial"
outcome; a row only ever exists once the full horizon has passed.

**Reuses `generate_label()`, never a second target definition.** The
actual outcome for a prediction is computed by calling the exact same
function `app/predictions/dataset.py` calls to build a label during
training — `organization_id`/`site_id`/`as_of=prediction_time`/
`horizon_days=prediction.horizon_days` — so "did the model turn out to
be right" and "what would this example's label have been" are
guaranteed to mean the same thing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.models.prediction_outcome import PredictionOutcome
from app.predictions.enums import PredictionOutcome as PredictionOutcomeEnum
from app.predictions.labels import generate_label
from app.services.audit_service import AuditAction, audit_service


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def evaluate_prediction_outcome(
    db: Session, *, prediction_id: uuid.UUID, as_of_now: datetime | None = None, persist: bool = True
) -> PredictionOutcome | None:
    prediction = db.get(Prediction, prediction_id)
    if prediction is None:
        raise ValueError(f"No Prediction with id {prediction_id}.")
    if prediction.outcome != PredictionOutcomeEnum.PREDICTED.value:
        raise ValueError("Only a PREDICTED prediction has an outcome to evaluate -- this row is a NO_PREDICTION abstention.")

    as_of_now = as_of_now or datetime.now(timezone.utc)
    horizon_end = _as_utc(prediction.prediction_time) + timedelta(days=prediction.horizon_days)
    if _as_utc(as_of_now) < horizon_end:
        # Not yet due -- never fabricate an early/partial outcome.
        return None

    existing = db.execute(
        select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id)
    ).scalar_one_or_none()
    if existing is not None and existing.outcome_known:
        return existing

    label_result = generate_label(
        db,
        organization_id=prediction.organization_id,
        site_id=prediction.entity_id,
        as_of=prediction.prediction_time,
        horizon_days=prediction.horizon_days,
    )

    if existing is not None:
        outcome_row = existing
        outcome_row.outcome_known = True
        outcome_row.actual_label = label_result.label
        outcome_row.outcome_event_ids = [str(i) for i in label_result.supporting_event_ids]
        outcome_row.evaluated_at = as_of_now
    else:
        outcome_row = PredictionOutcome(
            organization_id=prediction.organization_id,
            prediction_id=prediction.id,
            outcome_known=True,
            actual_label=label_result.label,
            outcome_event_ids=[str(i) for i in label_result.supporting_event_ids],
            evaluated_at=as_of_now,
        )
        db.add(outcome_row)

    if persist:
        db.commit()
        db.refresh(outcome_row)
        audit_service.log(
            db,
            action=AuditAction.PREDICTION_OUTCOME_EVALUATED,
            resource_type="prediction_outcome",
            resource_id=outcome_row.id,
            organization_id=prediction.organization_id,
            metadata={
                "prediction_id": str(prediction.id),
                "actual_label": label_result.label,
                "predicted_risk_category": prediction.risk_category,
            },
        )
    return outcome_row


def evaluate_matured_outcomes(
    db: Session, *, organization_id: uuid.UUID, as_of_now: datetime | None = None
) -> list[PredictionOutcome]:
    """Finds every `PREDICTED` prediction for this organization whose
    horizon has matured and has no outcome recorded yet, and evaluates
    each — the batch entry point a scheduled job or an admin endpoint
    would call. Never retrains or redeploys anything; purely records
    what happened."""
    as_of_now = as_of_now or datetime.now(timezone.utc)
    already_evaluated_prediction_ids = {
        row[0]
        for row in db.execute(
            select(PredictionOutcome.prediction_id).where(
                PredictionOutcome.organization_id == organization_id, PredictionOutcome.outcome_known.is_(True)
            )
        ).all()
    }
    candidates = db.execute(
        select(Prediction).where(
            Prediction.organization_id == organization_id,
            Prediction.outcome == PredictionOutcomeEnum.PREDICTED.value,
        )
    ).scalars().all()

    results: list[PredictionOutcome] = []
    for prediction in candidates:
        if prediction.id in already_evaluated_prediction_ids:
            continue
        outcome = evaluate_prediction_outcome(db, prediction_id=prediction.id, as_of_now=as_of_now)
        if outcome is not None:
            results.append(outcome)
    return results


__all__ = ["evaluate_matured_outcomes", "evaluate_prediction_outcome"]
