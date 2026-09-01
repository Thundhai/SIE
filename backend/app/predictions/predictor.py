"""Prediction serving — milestone items 12-13, 27, 29-30, 32-34.

    predict_as_of(organization_id, site_id, as_of, model)
        -> entity/model-governance checks       -> abstain, or continue
        -> historical profile (cold start check) -> abstain, or continue
        -> staleness check                       -> abstain, or continue
        -> feature_snapshot_service.get_or_build_feature_snapshot(as_of)
        -> data-sufficiency check on the snapshot -> abstain, or continue
        -> reconstruct model + preprocessor from ModelRegistryEntry.parameters
        -> risk_score, risk_category, (probability iff calibration_validated)
        -> explain.explain_prediction()
        -> Prediction(outcome=PREDICTED, ...)

**Never forces a prediction (milestone item 30).** Every abstention path
below still returns (and, if `persist=True`, still stores) a `Prediction`
row with `outcome=NO_PREDICTION` and a specific `AbstentionReason` — an
abstention is a real, auditable outcome, not an exception the caller has
to catch.

**`predict_as_of()` is also the internal backtesting mechanism (item
34).** It takes `as_of` as an explicit parameter and never reads
"now" — the exact same function trusted for live serving, called with a
historical `as_of`, is what a backtest replays. `require_deployed=False`
is available *only* for that internal, non-serving use — the live
Predictions API (`app/api/v1/predictions.py`) always calls this with
`require_deployed=True` (item 32: only a `DEPLOYED` model may serve a
live prediction).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.intelligence.temporal import events_as_of
from app.models.model_registry_entry import ModelRegistryEntry
from app.models.prediction import Prediction
from app.predictions.enums import (
    AbstentionReason,
    ModelStatus,
    PredictionDataQuality,
    PredictionOutcome,
    RiskCategory,
)
from app.predictions.explain import explain_prediction
from app.predictions.feature_snapshot_service import get_or_build_feature_snapshot
from app.predictions.logistic_regression import (
    FeaturePreprocessor,
    LogisticRegressionModel,
)
from app.predictions.spec import (
    ELEVATED_RISK_THRESHOLD,
    HORIZON_DAYS,
    MAX_SOURCE_DATA_STALENESS_DAYS,
    MIN_HISTORICAL_DAYS,
    MIN_HISTORICAL_EVENT_COUNT,
    MODERATE_RISK_THRESHOLD,
    PREDICTION_ENTITY_TYPE,
)
from app.predictions.vectorization import vectorize
from app.services.audit_service import AuditAction, audit_service

_DATA_QUALITY_MAP = {
    "SUFFICIENT_DATA": PredictionDataQuality.GOOD.value,
    "LIMITED_DATA": PredictionDataQuality.LIMITED.value,
    "INSUFFICIENT_DATA": PredictionDataQuality.INSUFFICIENT.value,
}

# Abstentions raised before a feature snapshot is even attempted (entity/
# model-governance checks) have no data-quality verdict to report --
# INSUFFICIENT is the honest default (never GOOD/LIMITED, which would
# imply data was actually assessed).
_UNASSESSED_DATA_QUALITY = PredictionDataQuality.INSUFFICIENT.value

def _as_utc(value: datetime) -> datetime:
    """SQLite (the test database — see tests/conftest.py) does not
    persist `tzinfo`; PostgreSQL does. A naive value read back from
    SQLite is always UTC in this codebase (every write goes through
    `app.intelligence.normalization`, which stamps UTC), so this is a
    safe, not a guessed, normalization — mirrors
    `app/intelligence/reliability.py::_as_utc()`."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


_MODEL_NOT_READY_REASONS = {
    ModelStatus.TRAINED.value: AbstentionReason.MODEL_NOT_VALIDATED,
    ModelStatus.VALIDATED.value: AbstentionReason.MODEL_NOT_APPROVED,
    ModelStatus.APPROVED.value: AbstentionReason.MODEL_NOT_APPROVED,
    ModelStatus.REJECTED.value: AbstentionReason.MODEL_UNAVAILABLE,
    ModelStatus.RETIRED.value: AbstentionReason.MODEL_UNAVAILABLE,
}


def _risk_category(score: float) -> str:
    if score >= ELEVATED_RISK_THRESHOLD:
        return RiskCategory.ELEVATED.value
    if score >= MODERATE_RISK_THRESHOLD:
        return RiskCategory.MODERATE.value
    return RiskCategory.LOW.value


def _abstain(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    as_of: datetime,
    horizon_days: int,
    reason: AbstentionReason,
    model: ModelRegistryEntry | None,
    data_quality: str = _UNASSESSED_DATA_QUALITY,
    persist: bool,
    user_id: uuid.UUID | None,
) -> Prediction:
    prediction = Prediction(
        organization_id=organization_id,
        entity_type=PREDICTION_ENTITY_TYPE,
        entity_id=site_id,
        prediction_time=as_of,
        horizon_days=horizon_days,
        outcome=PredictionOutcome.NO_PREDICTION.value,
        abstention_reason=reason.value,
        risk_score=None,
        probability=None,
        risk_category=None,
        model_id=model.id if model is not None else None,
        model_version=model.model_version if model is not None else None,
        feature_snapshot_id=None,
        data_quality=data_quality,
        explanation=None,
    )
    if persist:
        db.add(prediction)
        db.commit()
        db.refresh(prediction)
        audit_service.log(
            db,
            action=AuditAction.PREDICTION_ABSTAINED,
            resource_type="prediction",
            resource_id=prediction.id,
            organization_id=organization_id,
            user_id=user_id,
            metadata={"entity_id": str(site_id), "abstention_reason": reason.value},
        )
    return prediction


def abstain_no_deployed_model(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    as_of: datetime,
    horizon_days: int | None = None,
    persist: bool = True,
    user_id: uuid.UUID | None = None,
) -> Prediction:
    """The one abstention case `predict_as_of()` itself cannot produce —
    there is no `ModelRegistryEntry` to call it with at all (nothing has
    ever been deployed for this organization/entity type). Used by
    `app/api/v1/predictions.py` when `model_registry.get_deployed_model()`
    returns `None`."""
    return _abstain(
        db, organization_id=organization_id, site_id=site_id, as_of=as_of,
        horizon_days=horizon_days if horizon_days is not None else HORIZON_DAYS,
        reason=AbstentionReason.MODEL_UNAVAILABLE, model=None, persist=persist, user_id=user_id,
    )


def predict_as_of(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    as_of: datetime,
    model: ModelRegistryEntry,
    horizon_days: int | None = None,
    require_deployed: bool = True,
    persist: bool = True,
    user_id: uuid.UUID | None = None,
) -> Prediction:
    horizon_days = horizon_days if horizon_days is not None else HORIZON_DAYS

    # --- Entity support -------------------------------------------------
    if model.entity_type != PREDICTION_ENTITY_TYPE:
        return _abstain(
            db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days,
            reason=AbstentionReason.UNSUPPORTED_ENTITY, model=model, persist=persist, user_id=user_id,
        )

    # --- Model governance (item 32) --------------------------------------
    if require_deployed and model.status != ModelStatus.DEPLOYED.value:
        reason = _MODEL_NOT_READY_REASONS.get(model.status, AbstentionReason.MODEL_UNAVAILABLE)
        return _abstain(
            db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days,
            reason=reason, model=model, persist=persist, user_id=user_id,
        )

    # --- Cold start / historical sufficiency (items 12-13) ----------------
    history = list(
        db.execute(events_as_of(organization_id=organization_id, as_of=as_of, site_id=site_id)).scalars().all()
    )
    if not history:
        return _abstain(
            db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days,
            reason=AbstentionReason.COLD_START, model=model, persist=persist, user_id=user_id,
        )
    earliest = min(_as_utc(e.event_time) for e in history)
    latest = min(as_of, max(_as_utc(e.event_time) for e in history))
    history_days = (as_of - earliest).days
    if history_days < MIN_HISTORICAL_DAYS:
        return _abstain(
            db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days,
            reason=AbstentionReason.COLD_START, model=model, persist=persist, user_id=user_id,
        )
    if len(history) < MIN_HISTORICAL_EVENT_COUNT:
        return _abstain(
            db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days,
            reason=AbstentionReason.INSUFFICIENT_HISTORICAL_DATA, model=model, persist=persist, user_id=user_id,
        )

    # --- Staleness (item 30) ----------------------------------------------
    staleness_days = (as_of - latest).days
    if staleness_days > MAX_SOURCE_DATA_STALENESS_DAYS:
        return _abstain(
            db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days,
            reason=AbstentionReason.STALE_SOURCE_DATA, model=model,
            data_quality=PredictionDataQuality.STALE.value, persist=persist, user_id=user_id,
        )

    # --- Feature snapshot (items 8-10) -------------------------------------
    snapshot = get_or_build_feature_snapshot(db, organization_id=organization_id, site_id=site_id, as_of=as_of)
    if snapshot.data_quality == "INSUFFICIENT_DATA":
        return _abstain(
            db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days,
            reason=AbstentionReason.REQUIRED_FEATURES_MISSING, model=model,
            data_quality=_DATA_QUALITY_MAP[snapshot.data_quality], persist=persist, user_id=user_id,
        )

    # --- Scoring -------------------------------------------------------------
    feature_vector = vectorize(snapshot.features)
    preprocessor = FeaturePreprocessor.from_params(model.parameters["preprocessor"])
    lr_model = LogisticRegressionModel.from_params(model.parameters["model"])
    encoded_row = preprocessor.transform([feature_vector])[0]
    risk_score = lr_model.predict_proba(encoded_row)

    explanation = explain_prediction(lr_model, preprocessor, feature_vector)

    prediction = Prediction(
        organization_id=organization_id,
        entity_type=PREDICTION_ENTITY_TYPE,
        entity_id=site_id,
        prediction_time=as_of,
        horizon_days=horizon_days,
        outcome=PredictionOutcome.PREDICTED.value,
        abstention_reason=None,
        risk_score=risk_score,
        # Never a fabricated probability -- only when this model's
        # calibration has actually been checked and passed (milestone
        # items 18-19; see model_registry.py::mark_validated()).
        probability=risk_score if model.calibration_validated else None,
        risk_category=_risk_category(risk_score),
        model_id=model.id,
        model_version=model.model_version,
        feature_snapshot_id=snapshot.id,
        data_quality=_DATA_QUALITY_MAP[snapshot.data_quality],
        explanation={
            "top_positive": [asdict(c) for c in explanation.top_positive],
            "top_negative": [asdict(c) for c in explanation.top_negative],
            "method": explanation.method,
            "disclaimer": explanation.disclaimer,
        },
    )
    if persist:
        db.add(prediction)
        db.commit()
        db.refresh(prediction)
        audit_service.log(
            db,
            action=AuditAction.PREDICTION_GENERATED,
            resource_type="prediction",
            resource_id=prediction.id,
            organization_id=organization_id,
            user_id=user_id,
            metadata={"entity_id": str(site_id), "risk_category": prediction.risk_category, "model_id": str(model.id)},
        )
    return prediction


__all__ = ["abstain_no_deployed_model", "predict_as_of"]
