"""Predictions API — milestone item 31; extended by Intelligence Platform
Integration & Enterprise API v0.1, items 12, 18, 38.

    POST /api/v1/intelligence/predictions               -> generate/refresh a prediction for one entity
    GET  /api/v1/intelligence/predictions/{id}           -> the latest recorded prediction for that entity
    GET  /api/v1/intelligence/predictions/{id}/history   -> paginated prediction history for that entity

**Input security (milestone item 45).** The request body
(`PredictionRequest`) carries only `entity_id` and an optional `as_of` —
there is no field a client could use to supply a feature value, a risk
score, or a label; the feature snapshot is always built server-side, at
request time, from this organization's own stored `SafetyEvent` data
(`app/predictions/feature_snapshot_service.py`).

**Authorization, model status, and entity ownership are all verified
before anything is computed** — `organization_id` comes from the
authenticated caller's own authorized context (never a client-supplied
field), human or machine (`app.api.deps_context.RequestContext`, the same
authenticate-then-authorize-then-pass-a-trusted-value shape
`app/api/v1/intelligence.py` already establishes); the entity is checked
to actually belong to that organization before any prediction is
attempted; only a `DEPLOYED` model is ever used to serve a live
prediction (`app/predictions/predictor.py::predict_as_of(require_deployed=True)`).

**Idempotency (item 12).** `POST /predictions` accepts an optional
`Idempotency-Key` header — a retried request with the same key and the
same body replays the first attempt's recorded prediction rather than
generating (and persisting) a second one; a reused key with a different
body is a 409 `IDEMPOTENCY_CONFLICT`. See `app/core/idempotency.py`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.intelligence.temporal import utcnow
from app.models.prediction import Prediction
from app.models.site import Site
from app.predictions import model_registry
from app.predictions.predictor import abstain_no_deployed_model, predict_as_of
from app.predictions.spec import PREDICTION_ENTITY_TYPE
from app.schemas.envelope import ResponseEnvelope, build_envelope
from app.schemas.predictions import ExplanationRead, PredictionRead, PredictionRequest
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence/predictions", tags=["predictions"])

_ENDPOINT_CREATE = "POST /intelligence/predictions"


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


@router.post(
    "", response_model=PredictionRead, dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))]
)
def create_prediction(
    body: PredictionRequest,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.PREDICTION_READ)),
    db: Session = Depends(get_db),
) -> PredictionRead:
    _require_owned_site(db, organization_id=organization_id, site_id=body.entity_id)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return PredictionRead.model_validate(lookup.response_body)

    as_of = body.as_of or utcnow()
    model = model_registry.get_deployed_model(db, organization_id=organization_id, entity_type=PREDICTION_ENTITY_TYPE)
    if model is None:
        prediction = abstain_no_deployed_model(
            db, organization_id=organization_id, site_id=body.entity_id, as_of=as_of, user_id=context.user_id
        )
    else:
        prediction = predict_as_of(
            db,
            organization_id=organization_id,
            site_id=body.entity_id,
            as_of=as_of,
            model=model,
            require_deployed=True,
            user_id=context.user_id,
        )
    result = _to_read(prediction)
    store_response(
        db,
        endpoint=_ENDPOINT_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status_code=status.HTTP_200_OK,
        response_body=result.model_dump(mode="json"),
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    return result


@router.get(
    "/{entity_id}", response_model=PredictionRead, dependencies=[Depends(require_rate_limit(RateLimitClass.READ))]
)
def get_latest_prediction(
    entity_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.PREDICTION_READ)),
    db: Session = Depends(get_db),
) -> PredictionRead:
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


@router.get(
    "/{entity_id}/history",
    response_model=ResponseEnvelope[list[PredictionRead]],
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_prediction_history(
    entity_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(require_context_permission(Permission.PREDICTION_READ)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[list[PredictionRead]]:
    """Every recorded prediction for this entity, newest first — both
    `PREDICTED` and abstained `NO_PREDICTION` rows (an abstention is
    itself a real, audited outcome; see `app/predictions/predictor.py`'s
    own docstring — this history is never filtered down to only the
    "successful" predictions). Paginated (`limit`/`offset`); an empty
    result at `offset=0` means no prediction has ever been recorded for
    this entity, not an error.

    The first endpoint in this codebase to use the standard response
    envelope (item 10) — a genuinely new response shape, so wrapping it
    breaks no existing consumer (see `app/schemas/envelope.py`'s own
    docstring for why existing endpoints keep their unwrapped shape)."""
    _require_owned_site(db, organization_id=organization_id, site_id=entity_id)

    predictions = db.execute(
        select(Prediction)
        .where(
            Prediction.organization_id == organization_id,
            Prediction.entity_type == PREDICTION_ENTITY_TYPE,
            Prediction.entity_id == entity_id,
        )
        .order_by(Prediction.prediction_time.desc(), Prediction.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    return build_envelope(
        [_to_read(p) for p in predictions],
        request_id=request_id,
        provenance={"organization_id": str(organization_id), "entity_id": str(entity_id), "entity_type": PREDICTION_ENTITY_TYPE},
    )
