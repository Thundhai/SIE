"""DataSource model — an external/internal system SIE ingests data from.

**Reused, not duplicated, as the "ingestion source" concept (Enterprise
Data Ingestion & Validation Foundation v0.1, item 3).** This model
already existed, tenant-scoped, with `name`/`source_type`/`status` — the
inspection for this milestone found it was the exact concept the
milestone's own "Ingestion source" spec describes, just missing a few
fields and, more importantly, missing authentication entirely (see
`app/api/v1/data_sources.py`'s own docstring — a second zero-auth gap in
the same shape as the one closed in `knowledge.py` last milestone).
Extended here, in place, rather than introducing a second, parallel
`IngestionSource` table:

  * `system_identifier` — the external system's own stable id/hostname
    for itself (e.g. `"sap-prod-us1"`), distinct from `name` (a
    human-chosen label) and from `SafetyEvent.source_system` (the string
    every ingested record is tagged with — `system_identifier`, when
    set, is the value a real integration is expected to send as
    `source_system`, but that link is a convention, not an enforced FK,
    since `source_system` predates this field and many rows will never
    reference a registered source at all).
  * `schema_version` — the version of *this source's own* payload shape
    it currently sends (distinct from `SafetyEvent.source_schema_version`,
    which is recorded per-record — this column is the source's current/
    expected version; a record's own value is what it actually sent).
  * `config_metadata` — free-form JSON for source-specific configuration
    (e.g. expected timezone, a field-mapping hint for a future adapter).
    Never a credential or secret — see below.
  * `api_client_id` — optional link to the `ApiClient` credential that
    authenticates this source's submissions. **No plaintext secret is
    ever stored here or anywhere on this model** — authentication
    continues to flow entirely through the existing `ApiClient`/
    `app/api/deps_machine_auth.py` machinery; this column exists purely
    so a human managing sources can see which credential a given source
    is expected to authenticate with. `ON DELETE SET NULL`: revoking or
    deleting a credential must never delete the source record describing
    where the data came from.

Ingestion logic itself (validation/normalization/upsert) remains in
`app/intelligence/`, untouched by this model — see
`app/intelligence/enterprise_ingestion.py` for how a `DataSource` row is
used (as an optional, tenant-verified association on an ingestion batch),
never as a second place authorization is decided.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class DataSource(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Enterprise Data Ingestion & Validation Foundation v0.1 additions ---
    system_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    config_metadata: Mapped[dict[str, Any]] = mapped_column(_JSONType, nullable=False, default=dict)
    api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True, index=True
    )

    organization: Mapped["Organization"] = relationship(back_populates="data_sources")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DataSource id={self.id!s} organization_id={self.organization_id!s} "
            f"name={self.name!r} source_type={self.source_type!r}>"
        )
