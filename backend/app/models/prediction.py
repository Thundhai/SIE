"""Prediction — one row per prediction attempt (milestone item 27),
whether it succeeded or the system abstained
(`app/predictions/enums.py::PredictionOutcome`). An abstention is still
recorded: "we attempted to predict for this entity at this as_of and
declined, because X" is itself auditable information (milestone item
30), not a non-event.

    Prediction -> model_id -> ModelRegistryEntry
               -> feature_snapshot_id -> FeatureSnapshot
                                       -> features[*].source_event_ids -> SafetyEvent
                                                                        -> source_system / source_record_id

is the full provenance chain milestone item 33 requires — every step
inspectable via a foreign key, nothing summarized away.

**Never a fabricated probability (milestone items 18-19).** `risk_score`
is the model's raw output, always present when `outcome=PREDICTED`.
`probability` is populated **only** when the serving model's
`ModelRegistryEntry.calibration_validated` is `True` — otherwise it
stays `NULL`, and the response relies on `risk_category`
(`ELEVATED`/`MODERATE`/`LOW`/`INSUFFICIENT_DATA`) instead. Nothing in
this codebase presents an uncalibrated score as an interpretable
probability.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class Prediction(Base, UUIDPrimaryKeyMixin, OrganizationScopedMixin):
    __tablename__ = "predictions"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)

    prediction_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)

    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # PredictionOutcome
    abstention_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    risk_score: Mapped[float | None] = mapped_column(nullable=True)
    probability: Mapped[float | None] = mapped_column(nullable=True)
    risk_category: Mapped[str | None] = mapped_column(String(20), nullable=True)

    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    feature_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("feature_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )

    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)

    # {top_positive: [...], top_negative: [...], method, feature_set_version}
    # -- see app/predictions/explain.py. Never present for a NO_PREDICTION row.
    explanation: Mapped[dict | None] = mapped_column(_JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Prediction id={self.id!s} entity_id={self.entity_id!s} "
            f"outcome={self.outcome!r} risk_category={self.risk_category!r}>"
        )
