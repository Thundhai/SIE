"""EnterpriseIngestionBatch — one submission/import operation through the
new enterprise ingestion API (`POST /api/v1/data/ingestion`), Enterprise
Data Ingestion & Validation Foundation v0.1, item 3.

**Distinct from, and additive to, the pre-existing `ingestion_batch_id`
UUID already stamped on every `SafetyEvent` row** (see that model's own
docstring for why that column is a plain UUID, not a foreign key to a
table — it predates this milestone and stays exactly as it was). This
table's own primary key `id` is minted as *that same UUID value* for
every batch this router creates, so every `SafetyEvent` written through
`POST /api/v1/data/ingestion` is trivially joinable to its
`EnterpriseIngestionBatch` (`SafetyEvent.ingestion_batch_id ==
EnterpriseIngestionBatch.id`) without a schema change to `SafetyEvent`
itself. A batch submitted through the older, still-supported
`/intelligence/events/batch` endpoint has no row here at all — that path
was deliberately left untouched (see
`app/intelligence/enterprise_ingestion.py`'s own docstring) — and that is
not an error condition; it simply predates this milestone's tracking
layer.

Because processing is synchronous (item 13: "keep processing
deterministic and synchronous where practical... create an explicit
extension seam for future asynchronous processing"), `status` is
`RECEIVED` only for the instant between the row being constructed and
the batch actually finishing, and is always `COMPLETED` or `FAILED` by
the time this row is committed and visible to any reader — `RECEIVED` is
the seam a future asynchronous/background implementation would use (a
row created immediately, updated to its terminal status once real
background processing finishes), not a state any synchronous caller can
currently observe.

Per-outcome counts mirror `IngestionOutcome`'s vocabulary (see
`app/intelligence/enums.py`) but are named for what an external system
actually needs to know, not this codebase's internal enum spelling:
`accepted_records` (created or updated with `VALID` quality),
`partial_records` (`PARTIAL` quality), `quarantined_records`
(`QUARANTINED` quality), `rejected_records` (validation-level rejection —
no canonical event created), `duplicate_records` (an exact,
content-identical replay — `SKIPPED_IDEMPOTENT`). The two new
source-record-version outcomes this milestone introduces
(`SKIPPED_STALE_VERSION`, `REJECTED_VERSION_CONFLICT`) are deliberately
*not* given their own top-level columns — the milestone's own required
column list is exactly the six above — and are instead reported inside
`error_summary` (see that column's own note below), keeping this row's
required-columns shape stable while still surfacing the new cases.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class EnterpriseIngestionBatch(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "enterprise_ingestion_batches"

    # Nullable + ON DELETE SET NULL: a batch's own history must survive
    # even if the DataSource describing where it came from is later
    # deleted -- mirrors SafetyEvent.ingestion_source_id's exact reasoning.
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # RECEIVED | COMPLETED | FAILED

    total_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Echoes the HTTP Idempotency-Key header, when supplied -- distinct
    # from app/core/idempotency.py's own IdempotencyKey table (that one
    # replays the whole HTTP response transport-side, before this row is
    # ever created; this column is purely descriptive, so a human
    # inspecting a batch can see which client-supplied key produced it).
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # {"stale_version_count": N, "version_conflict_count": M,
    #  "sample_issues": [...]} -- never a raw payload, never a full
    # per-record dump (see app/intelligence/enterprise_ingestion.py).
    error_summary: Mapped[dict[str, Any] | None] = mapped_column(_JSONType, nullable=True)

    organization: Mapped["Organization"] = relationship()  # noqa: F821
    source: Mapped["DataSource | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<EnterpriseIngestionBatch id={self.id!s} organization_id={self.organization_id!s} "
            f"status={self.status!r} total_records={self.total_records}>"
        )
