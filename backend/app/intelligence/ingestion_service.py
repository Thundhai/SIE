"""SafetyEventIngestionService — the DB-facing orchestration layer every
`DataSourceAdapter.ingest()` delegates to (milestone items 8, 11, 38).

    RawSafetyEventPayload -> adapter.validate() -> adapter.normalize()
        -> adapter.transform() -> _upsert() (idempotency + provenance) -> SafetyEvent row

**Idempotency (milestone item 11).** A record's identity is
`(organization_id, source_system, source_record_id)` — the exact
`UniqueConstraint` on `SafetyEvent` (see that model's docstring). A
resend of the same record is detected by comparing
`source_content_hash` (sha256 of the normalized payload's
`source_value`, the same `app.ingestion.hashing.sha256_hex` used
elsewhere in this codebase): unchanged content ->
`IngestionOutcome.SKIPPED_IDEMPOTENT` (no write at all, not even an
`updated_at` bump); changed content -> `IngestionOutcome.UPDATED` (the
existing row is updated in place, never duplicated).

**Batch ingestion (milestone item 38).** `ingest_batch()` processes each
record inside its own `db.begin_nested()` savepoint, so one malformed or
DB-constraint-violating record rolls back *only itself* — it can never
abort or corrupt the rest of the batch. Every record in a batch shares
one `ingestion_batch_id` (a fresh UUID, not a separate table — see
`app/models/safety_event.py`'s docstring for why), and a record that
repeats an earlier `(source_system, source_record_id)` pair *within the
same batch* is flagged `duplicate_in_batch=True` on its result (still
processed via the same idempotent upsert logic, not treated as an
error).

**Audit (milestone item 46).** Every ingestion call is recorded via the
existing `AuditService` — outcome counts and identifiers only, never the
raw `description` or full `source_value` payload (see
`app/intelligence/privacy.py`).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.enums import IngestionOutcome
from app.intelligence.normalization import NORMALIZATION_VERSION
from app.intelligence.schemas import NormalizedSafetyEvent, RawSafetyEventPayload, ValidationResult
from app.models.safety_event import SafetyEvent
from app.services.audit_service import AuditAction, audit_service

SCHEMA_VERSION = "schema-v1"
"""The canonical event schema version this service writes -- bumped
alongside a genuine shape change to `SafetyEvent`/`NormalizedSafetyEvent`,
independent of `NORMALIZATION_VERSION` (which tracks the *field-level*
transformation logic in app/intelligence/normalization.py). Both are
recorded per row (milestone item 7 — "transformation version" and "data
schema/version" are named as two distinct things)."""


def _content_hash(source_value: dict) -> str:
    canonical = json.dumps(source_value, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class IngestionRecordResult:
    outcome: IngestionOutcome
    event_id: uuid.UUID | None
    data_quality_status: str | None
    issues: list[dict] = field(default_factory=list)
    duplicate_in_batch: bool = False
    source_system: str | None = None
    source_record_id: str | None = None


@dataclass
class BatchIngestionResult:
    batch_id: uuid.UUID
    records: list[IngestionRecordResult] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        return sum(1 for r in self.records if r.outcome == IngestionOutcome.CREATED)

    @property
    def updated_count(self) -> int:
        return sum(1 for r in self.records if r.outcome == IngestionOutcome.UPDATED)

    @property
    def skipped_idempotent_count(self) -> int:
        return sum(1 for r in self.records if r.outcome == IngestionOutcome.SKIPPED_IDEMPOTENT)

    @property
    def rejected_count(self) -> int:
        return sum(1 for r in self.records if r.outcome == IngestionOutcome.REJECTED_INVALID)

    @property
    def duplicate_in_batch_count(self) -> int:
        return sum(1 for r in self.records if r.duplicate_in_batch)


class SafetyEventIngestionService:
    def ingest_event(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        payload: RawSafetyEventPayload,
        adapter,
        batch_id: uuid.UUID | None = None,
        audit: bool = True,
        commit: bool = True,
    ) -> IngestionRecordResult:
        # audit=False and commit=False are used only by ingest_batch()
        # below. commit=False matters specifically because each batch
        # record runs inside its own db.begin_nested() (SAVEPOINT) --
        # Session.commit() always commits and ends the *entire*
        # transaction, not just the savepoint, which would break the
        # "one bad record can't corrupt the rest of the batch" guarantee.
        # ingest_batch() flushes each record instead and commits once,
        # after the whole batch (including its own audit log write) has
        # been processed.
        batch_id = batch_id or uuid.uuid4()
        validation = adapter.validate(payload)
        if validation.status == "REJECTED":
            result = IngestionRecordResult(
                outcome=IngestionOutcome.REJECTED_INVALID,
                event_id=None,
                data_quality_status=None,
                issues=[_issue_dict(i) for i in validation.issues],
                source_system=payload.source_system,
                source_record_id=payload.source_record_id,
            )
        else:
            normalized = adapter.normalize(payload, organization_id=organization_id)
            normalized = adapter.transform(normalized)
            result = self._upsert(db, normalized=normalized, validation=validation, batch_id=batch_id, commit=commit)

        if audit:
            self._audit_event(db, organization_id=organization_id, result=result)
        return result

    def ingest_batch(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        payloads: list[RawSafetyEventPayload],
        adapter,
    ) -> BatchIngestionResult:
        batch_id = uuid.uuid4()
        seen_keys: set[tuple[str | None, str | None]] = set()
        records: list[IngestionRecordResult] = []

        for payload in payloads:
            key = (payload.source_system, payload.source_record_id)
            duplicate_in_batch = key in seen_keys and key != (None, None)
            seen_keys.add(key)

            try:
                with db.begin_nested():
                    result = self.ingest_event(
                        db,
                        organization_id=organization_id,
                        payload=payload,
                        adapter=adapter,
                        batch_id=batch_id,
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
            result.duplicate_in_batch = duplicate_in_batch
            records.append(result)

        batch_result = BatchIngestionResult(batch_id=batch_id, records=records)
        # _audit_batch()'s own AuditService.log() call commits -- that
        # one commit finalizes the whole batch's flushed-but-uncommitted
        # records together with the audit entry itself (see
        # ingest_event()'s own docstring on commit=False).
        self._audit_batch(db, organization_id=organization_id, batch_result=batch_result)
        return batch_result

    def _upsert(
        self,
        db: Session,
        *,
        normalized: NormalizedSafetyEvent,
        validation: ValidationResult,
        batch_id: uuid.UUID,
        commit: bool = True,
    ) -> IngestionRecordResult:
        content_hash = _content_hash(normalized.source_value)

        existing = db.execute(
            select(SafetyEvent).where(
                SafetyEvent.organization_id == normalized.organization_id,
                SafetyEvent.source_system == normalized.source_system,
                SafetyEvent.source_record_id == normalized.source_record_id,
            )
        ).scalar_one_or_none()

        issues_json = [_issue_dict(i) for i in validation.issues] or None

        if existing is not None and existing.source_content_hash == content_hash:
            return IngestionRecordResult(
                outcome=IngestionOutcome.SKIPPED_IDEMPOTENT,
                event_id=existing.id,
                data_quality_status=existing.data_quality_status,
                issues=issues_json or [],
                source_system=normalized.source_system,
                source_record_id=normalized.source_record_id,
            )

        if existing is not None:
            self._apply(existing, normalized, content_hash, validation.status, issues_json, batch_id)
            outcome = IngestionOutcome.UPDATED
            event = existing
        else:
            event = SafetyEvent(organization_id=normalized.organization_id)
            self._apply(event, normalized, content_hash, validation.status, issues_json, batch_id)
            db.add(event)
            outcome = IngestionOutcome.CREATED

        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(event)
        return IngestionRecordResult(
            outcome=outcome,
            event_id=event.id,
            data_quality_status=event.data_quality_status,
            issues=issues_json or [],
            source_system=normalized.source_system,
            source_record_id=normalized.source_record_id,
        )

    def _apply(
        self,
        event: SafetyEvent,
        normalized: NormalizedSafetyEvent,
        content_hash: str,
        quality_status: str,
        issues_json: list[dict] | None,
        batch_id: uuid.UUID,
    ) -> None:
        event.site_id = normalized.site_id
        event.event_type = normalized.event_type
        event.event_subtype = normalized.event_subtype
        event.event_time = normalized.event_time
        event.period_end = normalized.period_end
        event.reported_time = normalized.reported_time
        event.ingestion_time = datetime.now(timezone.utc)
        event.location = normalized.location
        event.project = normalized.project
        event.department = normalized.department
        event.contractor = normalized.contractor
        event.activity = normalized.activity
        event.severity = normalized.severity
        event.potential_severity = normalized.potential_severity
        event.status = normalized.status
        event.description = normalized.description
        event.attributes = normalized.attributes
        event.source_system = normalized.source_system
        event.source_record_id = normalized.source_record_id
        event.source_value = normalized.source_value
        event.source_content_hash = content_hash
        event.normalization_version = NORMALIZATION_VERSION
        event.schema_version = SCHEMA_VERSION
        event.ingestion_batch_id = batch_id
        event.data_quality_status = quality_status
        event.data_quality_issues = issues_json

    def _audit_event(
        self, db: Session, *, organization_id: uuid.UUID, result: IngestionRecordResult
    ) -> None:
        audit_service.log(
            db,
            action=AuditAction.SAFETY_EVENT_INGESTED,
            resource_type="SafetyEvent",
            resource_id=result.event_id,
            organization_id=organization_id,
            metadata={
                "outcome": result.outcome.value,
                "data_quality_status": result.data_quality_status,
                "issue_count": len(result.issues),
                "source_system": result.source_system,
                "source_record_id": result.source_record_id,
            },
        )

    def _audit_batch(
        self, db: Session, *, organization_id: uuid.UUID, batch_result: BatchIngestionResult
    ) -> None:
        audit_service.log(
            db,
            action=AuditAction.SAFETY_EVENT_BATCH_INGESTED,
            resource_type="SafetyEventBatch",
            resource_id=batch_result.batch_id,
            organization_id=organization_id,
            metadata={
                "record_count": len(batch_result.records),
                "created_count": batch_result.created_count,
                "updated_count": batch_result.updated_count,
                "skipped_idempotent_count": batch_result.skipped_idempotent_count,
                "rejected_count": batch_result.rejected_count,
                "duplicate_in_batch_count": batch_result.duplicate_in_batch_count,
                # Deliberately nothing else: never a raw description, raw
                # attributes, or full source_value here -- see
                # app/intelligence/privacy.py, which governs what
                # feature/signal output may include instead.
            },
        )


def _issue_dict(issue) -> dict:
    return {"code": issue.code, "message": issue.message, "blocking": issue.blocking}


safety_event_ingestion_service = SafetyEventIngestionService()
