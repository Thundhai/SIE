"""HTTP request/response shapes for the intelligence & predictive
analytics API (`app/api/v1/intelligence.py`, `app/api/v1/api_clients.py`).
Distinct from `app/intelligence/schemas.py` (internal ingestion
dataclasses) and `app/intelligence/*.py`'s own result dataclasses (the
same internal-domain-object/API-schema split used throughout this
codebase).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- Ingestion --------------------------------------------------------------------


class SafetyEventCreate(BaseModel):
    """Milestone item 6's canonical event shape, as an HTTP request body.
    Every field but the four identity fields (`event_type`,
    `source_system`, `source_record_id`, `event_time`) is optional — see
    `app/intelligence/validation.py` for exactly what happens when one is
    missing or malformed (never a 422 for a merely *questionable* value;
    the record is still accepted and quarantined/flagged)."""

    event_type: str | None = None
    event_subtype: str | None = None
    event_time: str | None = None
    period_end: str | None = None
    reported_time: str | None = None
    site_id: uuid.UUID | None = None
    location: str | None = None
    project: str | None = None
    department: str | None = None
    contractor: str | None = None
    activity: str | None = None
    severity: str | None = None
    potential_severity: str | None = None
    status: str | None = None
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_system: str | None = None
    source_record_id: str | None = None


class SafetyEventBatchCreate(BaseModel):
    events: list[SafetyEventCreate] = Field(..., min_length=1, max_length=1000)


class IngestionIssueRead(BaseModel):
    code: str
    message: str
    blocking: bool


class IngestionRecordRead(BaseModel):
    outcome: str
    event_id: uuid.UUID | None
    data_quality_status: str | None
    issues: list[IngestionIssueRead]
    duplicate_in_batch: bool = False
    source_system: str | None = None
    source_record_id: str | None = None


class BatchIngestionRead(BaseModel):
    batch_id: uuid.UUID
    record_count: int
    created_count: int
    updated_count: int
    skipped_idempotent_count: int
    rejected_count: int
    duplicate_in_batch_count: int
    records: list[IngestionRecordRead]


# --- Analytics ----------------------------------------------------------------------


class FeatureValueRead(BaseModel):
    name: str
    value: float | int | None
    window_days: int
    as_of: datetime
    entity_type: str
    entity_id: uuid.UUID | None
    source_event_ids: list[uuid.UUID]
    calculation_version: str
    data_quality: str
    exposure_basis: float | None = None
    unavailable_reason: str | None = None


class IndicatorValueRead(BaseModel):
    name: str
    category: str
    feature: FeatureValueRead


class RiskSignalRead(BaseModel):
    signal_type: str
    severity: str
    observed_period_start: datetime
    observed_period_end: datetime
    entity_type: str
    entity_id: uuid.UUID | None
    supporting_features: dict[str, float | int | None]
    supporting_event_ids: list[uuid.UUID]
    data_quality: str
    calculation_version: str


class SourceReliabilityRead(BaseModel):
    source_system: str
    record_count: int
    valid_count: int
    partial_count: int
    invalid_count: int
    quarantined_count: int
    latest_event_time: datetime | None
    latest_ingestion_time: datetime | None
    is_stale: bool
    freshness_threshold_days: int


class AnalyticsSummaryRead(BaseModel):
    organization_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    event_count: int
    data_sufficiency: str
    features: dict[str, FeatureValueRead]
    indicators: list[IndicatorValueRead]
    signals: list[RiskSignalRead]
    source_reliability: list[SourceReliabilityRead]


class TrendPeriodRead(BaseModel):
    period_start: datetime
    period_end: datetime
    value: float | None


class TrendResultRead(BaseModel):
    metric: str
    direction: str
    periods: list[TrendPeriodRead]
    slope: float | None
    relative_slope: float | None
    calculation_version: str
    method: str


class FeaturesRead(BaseModel):
    organization_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    features: dict[str, FeatureValueRead]


# --- Machine-client (API client) management -----------------------------------------


class ApiClientCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    # Least privilege by default (Intelligence Platform Integration v0.1,
    # item 6) -- each value must be a real app.services.permissions.Permission
    # value or app/services/api_client_service.py::ApiClientService.create()
    # rejects the whole request (422); there is no way to grant a scope
    # that does not correspond to a real, reviewable capability.
    scopes: list[str] = Field(..., min_length=1)
    # Optional (item 25's "expiration where appropriate") -- omit for a
    # credential that does not expire.
    expires_at: datetime | None = None


class ApiClientRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    client_id: str
    secret_prefix: str
    scopes: list[str]
    status: str
    created_at: datetime
    last_used_at: datetime | None
    rotated_at: datetime | None
    revoked_at: datetime | None
    expires_at: datetime | None


class ApiClientCreatedRead(ApiClientRead):
    """Only ever returned from the create/rotate endpoints — the one
    response that includes the raw secret, exactly once."""

    secret: str
