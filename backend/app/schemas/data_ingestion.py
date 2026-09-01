"""HTTP request/response shapes for `POST /api/v1/data/ingestion` and its
status endpoints (`app/api/v1/data_ingestion.py`) — Enterprise Data
Ingestion & Validation Foundation v0.1, item 2's generic enterprise
ingestion contract.

Distinct from `app/schemas/intelligence.py`'s `SafetyEventCreate` (the
older, narrower canonical-event shape `POST /intelligence/events` still
uses) — this is a superset: every field `SafetyEventCreate` has, plus the
new provenance/versioning fields item 2 asks for. Both ultimately build
the same internal `app.intelligence.schemas.RawSafetyEventPayload` and
flow through the exact same validate/normalize/upsert pipeline (see
`app/intelligence/enterprise_ingestion.py`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.intelligence import IngestionIssueRead


class EnterpriseIngestionRecordCreate(BaseModel):
    """One record in an enterprise ingestion submission — milestone item
    2's generic contract. Every field but the four identity fields
    (`event_type`, `event_time`, `source_system`, `source_record_id`) is
    optional; see `app/intelligence/validation.py` for exactly what
    happens when one is missing or malformed (never a 422 for a merely
    *questionable* value — the record is still accepted and
    quarantined/flagged, per item 4)."""

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
    # --- item 2's additional generic-contract fields ---------------------
    source_record_version: str | None = Field(
        default=None, description="The source system's own version/revision marker for this record, if any."
    )
    correlation_id: str | None = Field(
        default=None, description="Optional identifier linking this record to a related record or transaction."
    )
    source_schema_version: str | None = Field(
        default=None, description="The payload-shape version this specific record was sent under."
    )


class EnterpriseIngestionBatchCreate(BaseModel):
    """Body for `POST /api/v1/data/ingestion`. `source_id`, if given, must
    name a `DataSource` already registered in the authenticated machine
    client's own organization (never trusted from any other field) —
    see `app/api/v1/data_ingestion.py`."""

    source_id: uuid.UUID | None = None
    records: list[EnterpriseIngestionRecordCreate] = Field(..., min_length=1, max_length=1000)


class EnterpriseIngestionRecordRead(BaseModel):
    outcome: str = Field(
        description="CREATED | UPDATED | SKIPPED_IDEMPOTENT | REJECTED_INVALID | "
        "SKIPPED_STALE_VERSION | REJECTED_VERSION_CONFLICT"
    )
    canonical_event_id: uuid.UUID | None
    quality_state: str | None = Field(description="VALID | PARTIAL | QUARANTINED, or null for a rejected record")
    issues: list[IngestionIssueRead]
    duplicate_in_batch: bool = False
    external_record_id: str | None = None
    source_record_version: str | None = None
    content_hash: str | None = None


class EnterpriseIngestionBatchRead(BaseModel):
    batch_id: uuid.UUID
    source_id: uuid.UUID | None
    status: str = Field(description="RECEIVED | COMPLETED | FAILED")
    received_at: datetime
    total_records: int
    accepted_records: int
    partial_records: int
    quarantined_records: int
    rejected_records: int
    duplicate_records: int
    error_summary: dict[str, Any] | None
    records: list[EnterpriseIngestionRecordRead]


class EnterpriseIngestionBatchSummaryRead(BaseModel):
    """The list-view shape for `GET /api/v1/data/ingestion/batches` —
    every field `EnterpriseIngestionBatchRead` has except the full
    per-record breakdown, which stays a per-batch detail lookup
    (`GET .../batches/{batch_id}`) to keep a listing response bounded
    regardless of how large any one batch was."""

    batch_id: uuid.UUID
    source_id: uuid.UUID | None
    status: str
    received_at: datetime
    total_records: int
    accepted_records: int
    partial_records: int
    quarantined_records: int
    rejected_records: int
    duplicate_records: int
