"""EnterpriseIngestionRecord — one individual source record within an
`EnterpriseIngestionBatch`, Enterprise Data Ingestion & Validation
Foundation v0.1, item 3's "Ingestion record... when necessary for
traceability."

**Payload storage — deliberately not duplicated for the common case.**
When a record successfully produces or updates a canonical `SafetyEvent`
(`CREATED`/`UPDATED`/`QUARANTINED` — every outcome that has a
`canonical_event_id`), that event's own `source_value` column already
holds the exact payload; storing it again here would be exactly the
"unnecessary duplication of large payloads in PostgreSQL" the milestone
spec warns against. `payload` on this row is populated **only** when no
canonical event exists to hold it — a validation-level rejection
(`REJECTED_INVALID`) — since that is the one outcome where this row is
the *only* place the original content is ever recorded. This is a
plain JSONB column, the same pattern `SafetyEvent.source_value` already
uses elsewhere in this codebase, not a filesystem/object-storage
reference: the spec's "design a clear storage abstraction rather than
coupling to local filesystem storage" caveat applies to large binary
files (see `app/ingestion/storage.py`), not small structured JSON
records, so no new storage abstraction was introduced for this.
"""

import uuid
from typing import Any

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class EnterpriseIngestionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "enterprise_ingestion_records"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enterprise_ingestion_batches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Denormalized (also reachable via batch_id -> batch.organization_id)
    # so a tenant-scoped query never needs a join -- the same choice
    # AuditLog already makes for its own organization_id.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    external_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_record_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Same key (source_system, source_record_id) appeared more than once
    # within this one batch -- still processed via the same idempotent
    # upsert logic, never treated as an error (mirrors
    # BatchIngestionResult.duplicate_in_batch_count's existing meaning,
    # distinct from `outcome == SKIPPED_IDEMPOTENT`, which means "matches
    # a row already persisted from a *previous* submission").
    duplicate_in_batch: Mapped[bool] = mapped_column(nullable=False, default=False)

    # IngestionOutcome value (CREATED | UPDATED | SKIPPED_IDEMPOTENT |
    # REJECTED_INVALID | SKIPPED_STALE_VERSION | REJECTED_VERSION_CONFLICT)
    # -- see app/intelligence/enums.py. Named `outcome`, not
    # `validation_state`, because it reports what *happened to this
    # submission*, which is a strict superset of the record's own
    # DataQualityStatus (quality_state below) -- the same
    # outcome/quality-status distinction IngestionRecordResult already
    # draws.
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    # DataQualityStatus value (VALID | PARTIAL | QUARANTINED), or NULL for
    # REJECTED_INVALID (no row was ever classified, since none was
    # stored) -- the existing, reused vocabulary; see
    # app/intelligence/enums.py::DataQualityStatus's own docstring for why
    # this milestone introduces no second one.
    quality_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rejection_reason: Mapped[list[dict[str, Any]] | None] = mapped_column(_JSONType, nullable=True)

    canonical_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("safety_events.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Populated only for REJECTED_INVALID -- see module docstring.
    payload: Mapped[dict[str, Any] | None] = mapped_column(_JSONType, nullable=True)

    batch: Mapped["EnterpriseIngestionBatch"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<EnterpriseIngestionRecord id={self.id!s} batch_id={self.batch_id!s} "
            f"outcome={self.outcome!r} external_record_id={self.external_record_id!r}>"
        )
