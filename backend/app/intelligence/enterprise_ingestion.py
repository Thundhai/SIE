"""EnterpriseIngestionService — the orchestration layer behind
`POST /api/v1/data/ingestion` (Enterprise Data Ingestion & Validation
Foundation v0.1).

    RawSafetyEventPayload[] -> EnterpriseIngestionBatch (created)
        -> per record: SafetyEventIngestionService.ingest_event()  (UNCHANGED, item 8's
           validate -> normalize -> upsert pipeline, same savepoint-per-record safety)
        -> EnterpriseIngestionRecord (one row per input record, traceability)
        -> EnterpriseIngestionBatch (finalized: aggregate counts + status)

**This module does not implement ingestion — it wraps it.** Every
validation rule, normalization function, idempotency/version-conflict
decision, and canonical `SafetyEvent` write is the *exact* same call
(`app.intelligence.ingestion_service.safety_event_ingestion_service.ingest_event()`)
the pre-existing `POST /intelligence/events`/`/events/batch` endpoints
already use — this module adds nothing to that decision, only records
what it decided, the same "thin orchestration wrapper, business logic
lives one layer down" shape `app/api/v1/predictions.py` already uses
around `app/predictions/predictor.py`.

**The pre-existing `/intelligence/events`/`/events/batch` endpoints are
deliberately left untouched** by this module — they continue to write
`SafetyEvent` rows exactly as before, with no
`EnterpriseIngestionBatch`/`EnterpriseIngestionRecord` tracking. This is
a conscious scope boundary, not an oversight: retrofitting batch/record
tracking onto that already-well-tested, already-documented path would
have meant either changing its existing behavior (risking a regression
in 830+ passing tests) or duplicating this module's own logic there.
`POST /api/v1/data/ingestion` is the one, new, fully-tracked enterprise
entry point; the legacy routes remain available, backward compatible,
and simply untracked at the batch/record level — both write into the
exact same canonical `safety_events` table the existing intelligence
layer already consumes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.intelligence.adapters import GenericJSONAdapter
from app.intelligence.enums import DataQualityStatus, IngestionOutcome
from app.intelligence.ingestion_service import (
    IngestionRecordResult,
    _content_hash,
    safety_event_ingestion_service,
)
from app.intelligence.schemas import RawSafetyEventPayload
from app.models.enterprise_ingestion_batch import EnterpriseIngestionBatch
from app.models.enterprise_ingestion_record import EnterpriseIngestionRecord
from app.services.audit_service import AuditAction, audit_service

_MAX_SAMPLE_ISSUES = 20

_default_adapter = GenericJSONAdapter()


@dataclass
class EnterpriseIngestionResult:
    batch: EnterpriseIngestionBatch
    records: list[EnterpriseIngestionRecord] = field(default_factory=list)


class EnterpriseIngestionService:
    def ingest_batch(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        source_id: uuid.UUID | None,
        payloads: list[RawSafetyEventPayload],
        idempotency_key: str | None = None,
        adapter=None,
    ) -> EnterpriseIngestionResult:
        adapter = adapter or _default_adapter
        batch_id = uuid.uuid4()

        batch = EnterpriseIngestionBatch(
            id=batch_id,
            organization_id=organization_id,
            source_id=source_id,
            received_at=datetime.now(timezone.utc),
            status="RECEIVED",
            total_records=len(payloads),
            idempotency_key=idempotency_key,
        )
        db.add(batch)
        db.flush()

        records: list[EnterpriseIngestionRecord] = []
        seen_keys: set[tuple[str | None, str | None]] = set()
        duplicate_in_batch_count = 0
        stale_version_count = 0
        version_conflict_count = 0
        sample_issues: list[dict] = []

        for payload in payloads:
            key = (payload.source_system, payload.source_record_id)
            duplicate_in_batch = key in seen_keys and key != (None, None)
            seen_keys.add(key)
            if duplicate_in_batch:
                duplicate_in_batch_count += 1

            try:
                # Same per-record SAVEPOINT isolation
                # SafetyEventIngestionService.ingest_batch() already
                # established -- one malformed record can never corrupt
                # the rest of this batch or its tracking rows.
                with db.begin_nested():
                    result = safety_event_ingestion_service.ingest_event(
                        db,
                        organization_id=organization_id,
                        payload=payload,
                        adapter=adapter,
                        batch_id=batch_id,
                        ingestion_source_id=source_id,
                        audit=False,
                        commit=False,
                    )
            except Exception as exc:  # noqa: BLE001 - one bad record must never abort the batch
                result = IngestionRecordResult(
                    outcome=IngestionOutcome.REJECTED_INVALID,
                    event_id=None,
                    data_quality_status=None,
                    issues=[{"code": "INGESTION_ERROR", "message": str(exc), "blocking": True}],
                    source_system=payload.source_system,
                    source_record_id=payload.source_record_id,
                )

            record = EnterpriseIngestionRecord(
                batch_id=batch_id,
                organization_id=organization_id,
                external_record_id=result.source_record_id,
                source_record_version=result.source_record_version,
                correlation_id=payload.correlation_id,
                content_hash=_content_hash(payload.as_source_value()),
                duplicate_in_batch=duplicate_in_batch,
                outcome=result.outcome.value,
                quality_state=result.data_quality_status,
                rejection_reason=result.issues or None,
                canonical_event_id=result.event_id,
                # Only the one outcome with no canonical event to hold the
                # payload gets its own copy -- see this module's own
                # (model's own) docstring.
                payload=payload.as_source_value() if result.outcome == IngestionOutcome.REJECTED_INVALID else None,
            )
            db.add(record)
            records.append(record)

            if result.outcome == IngestionOutcome.SKIPPED_STALE_VERSION:
                stale_version_count += 1
            elif result.outcome == IngestionOutcome.REJECTED_VERSION_CONFLICT:
                version_conflict_count += 1
            if result.issues and len(sample_issues) < _MAX_SAMPLE_ISSUES:
                sample_issues.append(
                    {
                        "external_record_id": result.source_record_id,
                        "issues": result.issues,
                    }
                )

        batch.status = "COMPLETED"
        batch.accepted_records = sum(1 for r in records if r.quality_state == DataQualityStatus.VALID.value)
        batch.partial_records = sum(1 for r in records if r.quality_state == DataQualityStatus.PARTIAL.value)
        batch.quarantined_records = sum(1 for r in records if r.quality_state == DataQualityStatus.QUARANTINED.value)
        batch.rejected_records = sum(1 for r in records if r.outcome == IngestionOutcome.REJECTED_INVALID.value)
        batch.duplicate_records = sum(1 for r in records if r.outcome == IngestionOutcome.SKIPPED_IDEMPOTENT.value)

        error_summary: dict = {}
        if duplicate_in_batch_count:
            error_summary["duplicate_in_batch_count"] = duplicate_in_batch_count
        if stale_version_count:
            error_summary["stale_version_count"] = stale_version_count
        if version_conflict_count:
            error_summary["version_conflict_count"] = version_conflict_count
        if sample_issues:
            error_summary["sample_issues"] = sample_issues
        batch.error_summary = error_summary or None

        db.commit()
        db.refresh(batch)
        for record in records:
            db.refresh(record)

        self._audit_batch(db, organization_id=organization_id, batch=batch)
        return EnterpriseIngestionResult(batch=batch, records=records)

    def _audit_batch(self, db: Session, *, organization_id: uuid.UUID, batch: EnterpriseIngestionBatch) -> None:
        audit_service.log(
            db,
            action=AuditAction.ENTERPRISE_INGESTION_BATCH_COMPLETED,
            resource_type="EnterpriseIngestionBatch",
            resource_id=batch.id,
            organization_id=organization_id,
            metadata={
                "source_id": str(batch.source_id) if batch.source_id else None,
                "total_records": batch.total_records,
                "accepted_records": batch.accepted_records,
                "partial_records": batch.partial_records,
                "quarantined_records": batch.quarantined_records,
                "rejected_records": batch.rejected_records,
                "duplicate_records": batch.duplicate_records,
                # Deliberately nothing else here -- never a raw
                # description, raw attributes, or full payload; see
                # app/intelligence/privacy.py.
            },
        )


enterprise_ingestion_service = EnterpriseIngestionService()
