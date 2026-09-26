"""Model Governance API — predictive-model dataset/training/validation/
approval/deployment lifecycle.

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** The entire
`app/predictions/` package this router orchestrated (dataset validation,
training, model registry, governance validation reports, monitoring) has
been extracted to the private Commercial Core repository. Every route is
preserved (path, method, permission requirement, authentication
dependency) but returns HTTP 501. See
docs/M43_IP_03_PUBLIC_EXTRACTION.md.

The underlying `DatasetVersion`/`ModelRegistryEntry`/`ModelApproval`/
`ModelReviewFlag` database models are not deleted -- same deferred
database-boundary rationale documented in `intelligence_decisions.py`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_dev_authenticated_user_id
from app.integrations.commercial_core import commercial_core_client
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["model-governance"])


def _authorize(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID, permission: Permission) -> None:
    if not authorization_service.can(db, user_id=user_id, permission=permission, organization_id=organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing {permission.value} permission in the requested organization.",
        )


def _unavailable():
    raise commercial_core_client.unavailable("Predictive-model governance")


@router.post("/datasets/validate", status_code=201)
def validate_dataset_endpoint(
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    _unavailable()


@router.get("/datasets")
def list_datasets_endpoint(
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    _unavailable()


@router.get("/datasets/{dataset_version_id}")
def get_dataset_endpoint(
    dataset_version_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    _unavailable()


@router.post("/models/train", status_code=201)
def train_model_endpoint(
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    _unavailable()


@router.get("/models")
def list_models_endpoint(
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    _unavailable()


@router.get("/models/{model_id}")
def get_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    _unavailable()


@router.post("/models/{model_id}/validate")
def validate_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    _unavailable()


@router.post("/models/{model_id}/approve")
def approve_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    _unavailable()


@router.post("/models/{model_id}/reject")
def reject_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    _unavailable()


@router.post("/models/{model_id}/deploy")
def deploy_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    _unavailable()


@router.post("/models/{model_id}/undeploy")
def undeploy_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    _unavailable()


@router.post("/models/{model_id}/retire")
def retire_model_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_MANAGE)
    _unavailable()


@router.get("/models/{model_id}/card")
def model_card_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    _unavailable()


@router.get("/models/{model_id}/validation-report")
def validation_report_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    _unavailable()


@router.get("/models/{model_id}/monitoring")
def model_monitoring_endpoint(
    model_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
):
    _authorize(db, user_id, organization_id, Permission.GOVERNANCE_READ)
    _unavailable()
