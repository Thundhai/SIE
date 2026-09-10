"""Enterprise Data Ingestion API — Enterprise Data Ingestion & Validation
Foundation v0.1.

    external system -> Authorization: Bearer <client_id>:<secret>
        -> require_scope(SAFETY_DATA_WRITE) -> [rate limit] -> [Idempotency-Key]
        -> POST /api/v1/data/ingestion
        -> EnterpriseIngestionService -> SafetyEventIngestionService (UNCHANGED)
        -> EnterpriseIngestionBatch + EnterpriseIngestionRecord rows (new tracking layer)
        -> canonical SafetyEvent rows (existing intelligence layer consumes these unchanged)

    human OR machine caller -> RequestContext -> authorize_context(SAFETY_DATA_READ, organization_id)
        -> GET .../batches | GET .../batches/{batch_id}

**Why `/data/ingestion`, not `/ingestion`.** `/api/v1/ingestion` already
exists (`app/api/v1/ingestion.py`) for the Universal Knowledge & Data
Ingestion Engine's *document* uploads (PDF/DOCX/XLSX/...) — a completely
different pipeline (`app/ingestion/`, unstructured file ingestion into
the knowledge base). This router is deliberately named to avoid any path
collision or reader confusion with that one.

**Machine-only write, mirroring `POST /intelligence/events`
exactly.** This is system-to-system integration (milestone item 7's
"machine: integrations, automated ingestion... never dev auth as
production auth") — the same `require_scope(Permission.SAFETY_DATA_WRITE)`
dependency `app/api/v1/intelligence.py` already uses, not a second,
different auth mechanism.

**Tenant isolation (item 10).** `organization_id` for a write is always
`MachineClientContext.organization_id` — the authenticated credential's
own, pinned organization — there is no field anywhere in
`EnterpriseIngestionBatchCreate` a client could use to name a different
one. `source_id`, if supplied, is verified to belong to that same
organization before use (404, not 403, for a source that either doesn't
exist or belongs to someone else — never revealing which). Reads
(`GET .../batches*`) require `organization_id` as an explicit, authorized
query parameter, resolved through `app.api.deps_context.authorize_context()`
— always organization-scoped; there is no GLOBAL concept for ingestion
batches at all, so the class of bug closed in `app/api/deps_context.py`
last milestone (a machine client bypassing scope on a GLOBAL-shaped
request) has no surface to reappear on here.

**Idempotency (item 12).** An optional `Idempotency-Key` header on the
write endpoint works exactly like `POST /intelligence/predictions`
already does (`app/core/idempotency.py`) — a retried request with the
same key and the same body replays the first attempt's recorded batch
response rather than re-ingesting a second time; a reused key with a
different body is `409 IDEMPOTENCY_CONFLICT`. This is in addition to,
never a replacement for, the domain-level per-record idempotency
`SafetyEventIngestionService` already provides (see
`app/intelligence/enterprise_ingestion.py`'s own docstring): the
HTTP-level key protects the *whole batch submission* against a network
retry; per-record content-hash matching protects each *individual
record* regardless of whether a key was ever used.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.api.deps_machine_auth import MachineClientContext, require_scope
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.intelligence.enterprise_ingestion import enterprise_ingestion_service
from app.intelligence.schemas import RawSafetyEventPayload
from app.models.data_source import DataSource
from app.models.enterprise_ingestion_batch import EnterpriseIngestionBatch
from app.models.enterprise_ingestion_record import EnterpriseIngestionRecord
from app.schemas.data_ingestion import (
    EnterpriseIngestionBatchCreate,
    EnterpriseIngestionBatchRead,
    EnterpriseIngestionBatchSummaryRead,
    EnterpriseIngestionRecordCreate,
    EnterpriseIngestionRecordRead,
)
from app.schemas.intelligence import IngestionIssueRead
from app.services.permissions import Permission

router = APIRouter(prefix="/data/ingestion", tags=["enterprise-ingestion"])

_ENDPOINT_CREATE = "POST /data/ingestion"


def _to_raw_payload(record: EnterpriseIngestionRecordCreate) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type=record.event_type,
        event_subtype=record.event_subtype,
        event_time=record.event_time,
        period_end=record.period_end,
        reported_time=record.reported_time,
        site_id=record.site_id,
        location=record.location,
        project=record.project,
        department=record.department,
        contractor=record.contractor,
        activity=record.activity,
        severity=record.severity,
        potential_severity=record.potential_severity,
        status=record.status,
        description=record.description,
        attributes=record.attributes,
        source_system=record.source_system,
        source_record_id=record.source_record_id,
        source_record_version=record.source_record_version,
        correlation_id=record.correlation_id,
        source_schema_version=record.source_schema_version,
    )


def _require_owned_source(db: Session, *, organization_id: uuid.UUID, source_id: uuid.UUID) -> None:
    source = db.execute(
        select(DataSource).where(DataSource.id == source_id, DataSource.organization_id == organization_id)
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source_id not found in this organization.")


def _to_record_read(record: EnterpriseIngestionRecord) -> EnterpriseIngestionRecordRead:
    issues = [IngestionIssueRead(**issue) for issue in (record.rejection_reason or [])]
    return EnterpriseIngestionRecordRead(
        outcome=record.outcome,
        canonical_event_id=record.canonical_event_id,
        quality_state=record.quality_state,
        issues=issues,
        duplicate_in_batch=record.duplicate_in_batch,
        external_record_id=record.external_record_id,
        source_record_version=record.source_record_version,
        content_hash=record.content_hash,
    )


def _to_batch_read(
    batch: EnterpriseIngestionBatch, records: list[EnterpriseIngestionRecord]
) -> EnterpriseIngestionBatchRead:
    return EnterpriseIngestionBatchRead(
        batch_id=batch.id,
        source_id=batch.source_id,
        status=batch.status,
        received_at=batch.received_at,
        total_records=batch.total_records,
        accepted_records=batch.accepted_records,
        partial_records=batch.partial_records,
        quarantined_records=batch.quarantined_records,
        rejected_records=batch.rejected_records,
        duplicate_records=batch.duplicate_records,
        error_summary=batch.error_summary,
        records=[_to_record_read(r) for r in records],
    )


def _to_batch_summary_read(batch: EnterpriseIngestionBatch) -> EnterpriseIngestionBatchSummaryRead:
    return EnterpriseIngestionBatchSummaryRead(
        batch_id=batch.id,
        source_id=batch.source_id,
        status=batch.status,
        received_at=batch.received_at,
        total_records=batch.total_records,
        accepted_records=batch.accepted_records,
        partial_records=batch.partial_records,
        quarantined_records=batch.quarantined_records,
        rejected_records=batch.rejected_records,
        duplicate_records=batch.duplicate_records,
    )


@router.post(
    "",
    response_model=EnterpriseIngestionBatchRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def ingest_enterprise_data(
    body: EnterpriseIngestionBatchCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: MachineClientContext = Depends(require_scope(Permission.SAFETY_DATA_WRITE)),
    db: Session = Depends(get_db),
) -> EnterpriseIngestionBatchRead:
    if body.source_id is not None:
        _require_owned_source(db, organization_id=context.organization_id, source_id=body.source_id)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=context.organization_id,
        api_client_id=context.api_client_id,
    )
    if lookup.is_replay:
        return EnterpriseIngestionBatchRead.model_validate(lookup.response_body)

    result = enterprise_ingestion_service.ingest_batch(
        db,
        organization_id=context.organization_id,
        source_id=body.source_id,
        payloads=[_to_raw_payload(r) for r in body.records],
        idempotency_key=idempotency_key,
    )
    response = _to_batch_read(result.batch, result.records)
    store_response(
        db,
        endpoint=_ENDPOINT_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status_code=status.HTTP_201_CREATED,
        response_body=response.model_dump(mode="json"),
        organization_id=context.organization_id,
        api_client_id=context.api_client_id,
    )
    return response


@router.get(
    "/batches",
    response_model=list[EnterpriseIngestionBatchSummaryRead],
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_enterprise_ingestion_batches(
    organization_id: uuid.UUID = Query(...),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    context: RequestContext = Depends(require_context_permission(Permission.SAFETY_DATA_READ)),
    db: Session = Depends(get_db),
) -> list[EnterpriseIngestionBatchSummaryRead]:
    batches = db.execute(
        select(EnterpriseIngestionBatch)
        .where(EnterpriseIngestionBatch.organization_id == organization_id)
        .order_by(EnterpriseIngestionBatch.received_at.desc())
        .offset(skip)
        .limit(limit)
    ).scalars().all()
    return [_to_batch_summary_read(b) for b in batches]


@router.get(
    "/batches/{batch_id}",
    response_model=EnterpriseIngestionBatchRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_enterprise_ingestion_batch(
    batch_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.SAFETY_DATA_READ)),
    db: Session = Depends(get_db),
) -> EnterpriseIngestionBatchRead:
    batch = db.execute(
        select(EnterpriseIngestionBatch).where(
            EnterpriseIngestionBatch.id == batch_id, EnterpriseIngestionBatch.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion batch not found.")

    records = db.execute(
        select(EnterpriseIngestionRecord)
        .where(EnterpriseIngestionRecord.batch_id == batch_id)
        .order_by(EnterpriseIngestionRecord.created_at)
    ).scalars().all()
    return _to_batch_read(batch, records)
