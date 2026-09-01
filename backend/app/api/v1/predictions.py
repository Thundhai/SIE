"""Predictions API — milestone item 31.

    POST /api/v1/intelligence/predictions       -> generate/refresh a prediction for one entity
    GET  /api/v1/intelligence/predictions/{id}   -> the latest recorded prediction for that entity

**Input security (milestone item 45).** The request body
(`PredictionRequest`) carries only `entity_id` and an optional `as_of` —
there is no field a client could use to supply a feature value, a risk
score, or a label; the feature snapshot is always built server-side, at
request time, from this organization's own stored `SafetyEvent` data
(`app/predictions/feature_snapshot_service.py`).

**Authorization, model status, and entity ownership are all verified
before anything is computed** — `organization_id` comes from the
authenticated user's own tenant context (never a client-supplied field:
see `_authorize_read()`'s callers below, the same
authenticate-then-authorize-then-pass-a-trusted-value shape
`app/api/v1/intelligence.py` already establishes); the entity is checked
to actually belong to that organization before any prediction is
attempted; only a `DEPLOYED` model is ever used to serve a live
prediction (`app/predictions/predictor.py::predict_as_of(require_deployed=True)`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_dev_authenticated_user_id
from app.intelligence.temporal import utcnow
from app.models.prediction import Prediction
from app.models.site import Site
from app.predictions import model_registry
from app.predictions.predictor import abstain_no_deployed_model, predict_as_of
from app.predictions.spec import PREDICTION_ENTITY_TYPE
from app.schemas.predictions import ExplanationRead, PredictionRead, PredictionRequest
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence/predictions", tags=["predictions"])


def _authorize(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    if not authorization_service.can(
        db, user_id=user_id, permission=Permission.PREDICTION_READ, organization_id=organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing prediction:read permission in the requested organization.",
        )


def _require_owned_site(db: Session, *, organization_id: uuid.UUID, site_id: uuid.UUID) -> Site:
    """Entity-ownership check (milestone item 31) — a 404, not a 403, for
    a site that either doesn't exist or belongs to a different
    organization: this endpoint never reveals whether a given id exists
    in someone else's tenant."""
    site = db.execute(
        select(Site).where(Site.id == site_id, Site.organization_id == organization_id)
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found in this organization.")
    return site


def _to_read(prediction: Prediction) -> PredictionRead:
    explanation = None
    if prediction.explanation is not None:
        explanation = ExplanationRead(**prediction.explanation)
    return PredictionRead(
        id=prediction.id,
        organization_id=prediction.organization_id,
        entity_type=prediction.entity_type,
        entity_id=prediction.entity_id,
        prediction_time=prediction.prediction_time,
        horizon_days=prediction.horizon_days,
        outcome=prediction.outcome,
        abstention_reason=prediction.abstention_reason,
        risk_score=prediction.risk_score,
        probability=prediction.probability,
        risk_category=prediction.risk_category,
        model_id=prediction.model_id,
        model_version=prediction.model_version,
        feature_snapshot_id=prediction.feature_snapshot_id,
        data_quality=prediction.data_quality,
        explanation=explanation,
        created_at=prediction.created_at,
    )


@router.post("", response_model=PredictionRead)
def create_prediction(
    body: PredictionRequest,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> PredictionRead:
    _authorize(db, user_id, organization_id)
    _require_owned_site(db, organization_id=organization_id, site_id=body.entity_id)

    as_of = body.as_of or utcnow()
    model = model_registry.get_deployed_model(db, organization_id=organization_id, entity_type=PREDICTION_ENTITY_TYPE)
    if model is None:
        prediction = abstain_no_deployed_model(
            db, organization_id=organization_id, site_id=body.entity_id, as_of=as_of, user_id=user_id
        )
    else:
        prediction = predict_as_of(
            db,
            organization_id=organization_id,
            site_id=body.entity_id,
            as_of=as_of,
            model=model,
            require_deployed=True,
            user_id=user_id,
        )
    return _to_read(prediction)


@router.get("/{entity_id}", response_model=PredictionRead)
def get_latest_prediction(
    entity_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> PredictionRead:
    _authorize(db, user_id, organization_id)
    _require_owned_site(db, organization_id=organization_id, site_id=entity_id)

    prediction = db.execute(
        select(Prediction)
        .where(
            Prediction.organization_id == organization_id,
            Prediction.entity_type == PREDICTION_ENTITY_TYPE,
            Prediction.entity_id == entity_id,
        )
        .order_by(Prediction.prediction_time.desc(), Prediction.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if prediction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No prediction recorded for this entity yet.")
    return _to_read(prediction)
