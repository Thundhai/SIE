"""Model governance API — Model Validation & Governance v0.1, item 48.

    POST /api/v1/intelligence/datasets/validate    -> register + validate a dataset (SYNTHETIC or REAL)
    GET  /api/v1/intelligence/datasets             -> list this organization's dataset versions
    GET  /api/v1/intelligence/datasets/{id}        -> one dataset version, with its full quality report

    POST /api/v1/intelligence/models/train         -> train one model (logistic_regression | gradient_boosting)
    POST /api/v1/intelligence/models/{id}/validate -> TRAINED -> VALIDATED (calibration checked server-side)
    GET  /api/v1/intelligence/models               -> list this organization's models
    GET  /api/v1/intelligence/models/{id}          -> one model's full record
    POST /api/v1/intelligence/models/{id}/approve  -> VALIDATED -> APPROVED (reviewer = the authenticated caller)
    POST /api/v1/intelligence/models/{id}/reject   -> -> REJECTED
    POST /api/v1/intelligence/models/{id}/deploy   -> APPROVED -> DEPLOYED
    POST /api/v1/intelligence/models/{id}/undeploy -> DEPLOYED -> APPROVED
    POST /api/v1/intelligence/models/{id}/retire   -> DEPLOYED -> RETIRED
    GET  /api/v1/intelligence/models/{id}/card              -> the model card (item 33)
    GET  /api/v1/intelligence/models/{id}/monitoring        -> prediction + performance monitoring (items 26, 28)
    GET  /api/v1/intelligence/models/{id}/validation-report -> a freshly-generated governance report (items 34-35)

**Restricted to authorized administrative users (milestone item 48's own
instruction) — never exposed to normal users.** Every mutating endpoint
(train/validate/approve/reject/deploy/undeploy/retire, dataset validate)
requires `governance:manage`; every read endpoint requires
`governance:read`. Neither permission is granted by default to the
`VIEWER`/`HSE_USER` roles — see `app/services/permissions.py::ROLE_PERMISSIONS`.

**Training data security (milestone item 49).** No request body in this
file has a field for a label, a feature value, a risk score, a metric, or
an approval/deployment decision's outcome — every one of those is always
computed or decided server-side. `approve()`/`reject()` always use the
*authenticated caller's own* user id as the reviewer — a client can never
name a different reviewer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_dev_authenticated_user_id
from app.models.dataset_version import DatasetVersion
from app.models.model_registry_entry import ModelRegistryEntry
from app.predictions import dataset_registry, model_registry
from app.predictions.data_requirements import check_minimum_requirements
from app.predictions.enums import DatasetEnvironment, ModelValidationStatus
from app.predictions.governance import (
    generate_validation_report,
    record_validation_report,
)
from app.predictions.model_card import build_model_card
from app.predictions.monitoring import (
    compute_model_performance_monitoring,
    compute_prediction_monitoring,
)
from app.predictions.training import train_model
from app.schemas.model_governance import (
    ApproveModelRequest,
    DatasetVersionRead,
    ModelRead,
    RejectModelRequest,
    TrainModelRequest,
    ValidateDatasetRequest,
)
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["model-governance"])


def _authorize(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID, permission: Permission) -> None:
    if not authorization_service.can(db, user_id=user_id, permission=permission, organization_id=organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing {permission.value} permission in the requested organization.",
        )


def _require_owned_dataset_version(db: Session, *, organization_id: uuid.UUID, dataset_version_id: uuid.UUID) -> DatasetVersion:
    dv = dataset_registry.get_dataset_version(db, organization_id=organization_id, dataset_version_id=dataset_version_id)
    if dv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found in this organization.")
    return dv


def _require_owned_model(db: Session, *, organization_id: uuid.UUID, model_id: uuid.UUID) -> ModelRegistryEntry:
    model = db.execute(
        select(ModelRegistryEntry).where(
            ModelRegistryEntry.id == model_id, ModelRegistryEntry.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found in this organization.")
    return model


def _governance_report_for(db: Session, model: ModelRegistryEntry):
    dataset_version = None
    if model.dataset_version_id is not None:
        dataset_version = dataset_registry.get_dataset_version(
            db, organization_id=model.organization_id, dataset_version_id=model.dataset_version_id
        )
    return generate_validation_report(model=model, dataset_version=dataset_version)


# --- Datasets --------------------------------------------------------------------------


@router.post("/datasets/validate", response_model=DatasetVersionRead)
def validate_dataset_endpoint(
    body: ValidateDatasetRequest,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> DatasetVersionRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)

    environment = DatasetEnvironment(body.environment)
    if environment == DatasetEnvironment.REAL:
        if not body.source_systems:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="source_systems is required and must be non-empty for a REAL dataset.",
            )
        dv = dataset_registry.register_real_dataset(
            db, organization_id=organization_id, dataset_id=body.dataset_id,
            date_range_start=body.date_range_start, date_range_end=body.date_range_end,
            source_systems=body.source_systems, user_id=user_id,
        )
    else:
        dv = dataset_registry.register_synthetic_dataset(
            db, organization_id=organization_id, dataset_id=body.dataset_id,
            date_range_start=body.date_range_start, date_range_end=body.date_range_end,
            source_systems=body.source_systems, user_id=user_id,
        )
    return DatasetVersionRead.model_validate(dv)


@router.get("/datasets", response_model=list[DatasetVersionRead])
def list_datasets_endpoint(
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> list[DatasetVersionRead]:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    return [DatasetVersionRead.model_validate(dv) for dv in dataset_registry.list_dataset_versions(db, organization_id=organization_id)]


@router.get("/datasets/{dataset_version_id}", response_model=DatasetVersionRead)
def get_dataset_endpoint(
    dataset_version_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> DatasetVersionRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    dv = _require_owned_dataset_version(db, organization_id=organization_id, dataset_version_id=dataset_version_id)
    return DatasetVersionRead.model_validate(dv)


# --- Models ------------------------------------------------------------------------------


@router.post("/models/train", response_model=ModelRead)
def train_model_endpoint(
    body: TrainModelRequest,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> ModelRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    dv = _require_owned_dataset_version(db, organization_id=organization_id, dataset_version_id=body.dataset_version_id)

    examples = dataset_registry.build_training_examples_for_dataset_version(db, dv)
    # thresholds=None -> check_minimum_requirements() falls back to its own
    # DataSufficiencyThresholds() default (an INITIAL GOVERNANCE DEFAULT,
    # not a universal industry threshold -- see data_requirements.py).
    requirements = check_minimum_requirements(dataset_version=dv, examples=examples, thresholds=None)
    if requirements.status == ModelValidationStatus.INSUFFICIENT_DATA.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "MODEL_VALIDATION_STATUS=INSUFFICIENT_DATA -- this dataset does not meet the minimum "
                "data requirements for training.",
                "failed_checks": [c.name for c in requirements.failed_checks],
            },
        )

    try:
        entry = train_model(
            db, organization_id=organization_id, examples=examples, model_type=body.model_type,
            model_name=body.model_name or "site-elevated-risk-baseline", dataset_version_id=dv.id,
            hyperparameters=body.hyperparameters, user_id=user_id,
        )
    except TypeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ModelRead.model_validate(entry)


@router.get("/models", response_model=list[ModelRead])
def list_models_endpoint(
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> list[ModelRead]:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    models = db.execute(
        select(ModelRegistryEntry)
        .where(ModelRegistryEntry.organization_id == organization_id)
        .order_by(ModelRegistryEntry.created_at.desc())
    ).scalars().all()
    return [ModelRead.model_validate(m) for m in models]


@router.get("/models/{model_id}", response_model=ModelRead)
def get_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> ModelRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    return ModelRead.model_validate(model)


def _transition_or_400(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except model_registry.InvalidModelTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/models/{model_id}/validate", response_model=ModelRead)
def validate_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> ModelRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)

    calibration_status = (model.metrics or {}).get("test", {}).get("calibration", {}).get("status")
    calibration_validated = calibration_status == "CALIBRATED"

    model = _transition_or_400(
        model_registry.mark_validated, db, model, calibration_validated=calibration_validated, user_id=user_id
    )
    report = _governance_report_for(db, model)
    record_validation_report(db, model, report)
    return ModelRead.model_validate(model)


@router.post("/models/{model_id}/approve", response_model=ModelRead)
def approve_model_endpoint(
    model_id: uuid.UUID,
    body: ApproveModelRequest,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> ModelRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    report = _governance_report_for(db, model)
    model = _transition_or_400(
        model_registry.approve, db, model, reviewer_user_id=user_id, validation_report=report.to_dict(), notes=body.notes,
    )
    return ModelRead.model_validate(model)


@router.post("/models/{model_id}/reject", response_model=ModelRead)
def reject_model_endpoint(
    model_id: uuid.UUID,
    body: RejectModelRequest,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> ModelRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    report = _governance_report_for(db, model)
    model = _transition_or_400(
        model_registry.reject, db, model, reviewer_user_id=user_id, reason=body.reason, validation_report=report.to_dict(),
    )
    return ModelRead.model_validate(model)


@router.post("/models/{model_id}/deploy", response_model=ModelRead)
def deploy_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> ModelRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    model = _transition_or_400(model_registry.deploy, db, model, user_id=user_id)
    return ModelRead.model_validate(model)


@router.post("/models/{model_id}/undeploy", response_model=ModelRead)
def undeploy_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> ModelRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    model = _transition_or_400(model_registry.undeploy, db, model, user_id=user_id)
    return ModelRead.model_validate(model)


@router.post("/models/{model_id}/retire", response_model=ModelRead)
def retire_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> ModelRead:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    model = _transition_or_400(model_registry.retire, db, model, user_id=user_id)
    return ModelRead.model_validate(model)


@router.get("/models/{model_id}/card")
def model_card_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    return build_model_card(model).to_dict()


@router.get("/models/{model_id}/validation-report")
def validation_report_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    return _governance_report_for(db, model).to_dict()


@router.get("/models/{model_id}/monitoring")
def model_monitoring_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    since: datetime | None = Query(default=None),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict:
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    model = _require_owned_model(db, organization_id=organization_id, model_id=model_id)
    prediction_summary = compute_prediction_monitoring(db, organization_id=organization_id, model_id=model.id, since=since)
    performance_summary = compute_model_performance_monitoring(db, organization_id=organization_id, model_id=model.id)
    return {
        "prediction_monitoring": {
            "total_predictions": prediction_summary.total_predictions,
            "predicted_count": prediction_summary.predicted_count,
            "abstained_count": prediction_summary.abstained_count,
            "abstention_rate": prediction_summary.abstention_rate,
            "abstention_reason_counts": prediction_summary.abstention_reason_counts,
            "data_quality_distribution": prediction_summary.data_quality_distribution,
            "risk_category_distribution": prediction_summary.risk_category_distribution,
            "risk_score_distribution": vars(prediction_summary.risk_score_distribution) if prediction_summary.risk_score_distribution else None,
            "probability_distribution": vars(prediction_summary.probability_distribution) if prediction_summary.probability_distribution else None,
        },
        "performance_monitoring": {
            "matured_outcome_count": performance_summary.matured_outcome_count,
            "missing_data_rate": performance_summary.missing_data_rate,
            "metrics": (
                {
                    "sample_size": performance_summary.metrics.sample_size,
                    "positive_count": performance_summary.metrics.positive_count,
                    "precision": performance_summary.metrics.precision,
                    "recall": performance_summary.metrics.recall,
                    "f1": performance_summary.metrics.f1,
                    "pr_auc": performance_summary.metrics.pr_auc,
                    "roc_auc": performance_summary.metrics.roc_auc,
                }
                if performance_summary.metrics
                else None
            ),
            "calibration_status": performance_summary.calibration.status if performance_summary.calibration else None,
        },
    }
