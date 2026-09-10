"""FeatureSnapshot — an immutable record of exactly what
`app/intelligence/features.py::compute_feature_set()` produced for one
entity, as of one timestamp, under one feature-set version (milestone
item 8).

This is the thing a trained model is actually allowed to see. Persisting
it (rather than recomputing on demand, as
`app/intelligence/analytics.py` does for live analytics) is what makes a
past prediction reproducible and auditable: `Prediction.feature_snapshot_id`
points at exactly the row that was fed into the model, forever, even if
the underlying `safety_events` later change or feature-calculation logic
is upgraded to a new `feature_set_version`.

`UniqueConstraint(organization_id, entity_type, entity_id, as_of,
feature_set_version)` makes snapshot generation idempotent — building the
"same" snapshot twice (e.g. once during training-dataset construction,
once during live prediction on the same as_of) reuses the existing row
rather than creating a duplicate.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class FeatureSnapshot(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "entity_type", "entity_id", "as_of", "feature_set_version",
            name="uq_feature_snapshots_entity_as_of_version",
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)

    # The exact point-in-time boundary every feature in this snapshot was
    # computed under -- see app/intelligence/temporal.py::events_as_of().
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    feature_set_version: Mapped[str] = mapped_column(String(20), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(20), nullable=False)

    # {feature_name: {value, data_quality, unavailable_reason,
    # source_event_ids, exposure_basis, ...}} -- the full FeatureValue
    # set, serialized. See app/predictions/feature_snapshot_service.py.
    features: Mapped[dict] = mapped_column(_JSONType, nullable=False)

    # Snapshot-level rollup -- app/intelligence/enums.py::DataSufficiency.
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)

    # Union of every feature's source_event_ids, capped -- milestone item 8.
    source_event_ids: Mapped[list] = mapped_column(_JSONType, nullable=False, default=list)
    exposure_basis: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<FeatureSnapshot id={self.id!s} entity_type={self.entity_type!r} "
            f"entity_id={self.entity_id!s} as_of={self.as_of!s}>"
        )
