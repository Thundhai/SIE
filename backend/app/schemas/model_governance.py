"""HTTP request/response shapes for the model governance API
(`app/api/v1/model_governance.py`). Distinct from the internal domain
dataclasses in `app/predictions/*.py` — the same
internal-domain-object/API-schema split used throughout this codebase.

**Input security (milestone item 49).** Every request body here carries
only what an administrative reviewer legitimately decides — which
dataset/model type to train, whether to approve/reject/deploy, review
notes. There is no field anywhere in this file for a client-supplied
label, feature value, metric, risk score, or approval/deployment status
— every one of those is always computed or set server-side.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class TrainModelRequest(BaseModel):
    dataset_version_id: uuid.UUID
    model_type: Literal["logistic_regression", "gradient_boosting"] = "logistic_regression"
    model_name: str | None = None
    # Only the named hyperparameters app/predictions/training.py::train_model()
    # actually recognizes for the chosen model_type are accepted -- an
    # unrecognized key is rejected server-side (TypeError), never silently
    # ignored or used to smuggle in unrelated behavior.
    hyperparameters: dict[str, float] | None = None


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    model_name: str
    model_version: str
    model_type: str
    status: str
    entity_type: str
    prediction_target_version: str
    label_definition_version: str
    feature_set_version: str
    training_data_version: str
    dataset_version_id: uuid.UUID | None
    horizon_days: int
    training_period_start: date
    training_period_end: date
    validation_period_start: date
    validation_period_end: date
    test_period_start: date
    test_period_end: date
    hyperparameters: dict
    metrics: dict
    calibration_validated: bool
    notes: str | None
    created_at: datetime


class ApproveModelRequest(BaseModel):
    notes: str | None = None


class RejectModelRequest(BaseModel):
    reason: str


class ValidateDatasetRequest(BaseModel):
    dataset_id: str
    environment: Literal["SYNTHETIC", "REAL"]
    date_range_start: datetime
    date_range_end: datetime
    # Required (and validated non-empty) for REAL; defaults to a synthetic
    # fixture label for SYNTHETIC -- see app/api/v1/model_governance.py.
    source_systems: list[str] | None = None


class DatasetVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    dataset_id: str
    dataset_version: str
    environment: str
    source_systems: list[str]
    date_range_start: date
    date_range_end: date
    feature_set_version: str
    target_version: str
    prediction_horizon_days: int
    entity_type: str
    entity_count: int
    record_count: int
    quality_report: dict[str, Any]
    created_at: datetime
