"""PredictionOutcome — milestone item 27: links a served `Prediction` to
what actually happened once its horizon has passed.

    Prediction (prediction_time, horizon_days)
        -> horizon matures (now >= prediction_time + horizon_days)
        -> app/predictions/outcome_tracking.py::evaluate_prediction_outcome()
        -> PredictionOutcome(outcome_known=True, actual_label, outcome_event_ids)

**Never evaluated before the horizon completes** (milestone item 28) —
`evaluate_prediction_outcome()` itself refuses to run early; a row with
`outcome_known=False` (or no row at all) means "not yet due," never "no
incident." One row per `Prediction` (`prediction_id` is unique) — this
table is purely additive bookkeeping over data `app/predictions/labels.py`
already knows how to compute; it never recomputes the label definition
itself, only reuses it against the specific prediction being scored.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class PredictionOutcome(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "prediction_outcomes"

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    outcome_known: Mapped[bool] = mapped_column(nullable=False, default=False)
    actual_label: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 | 1, null until known
    outcome_event_ids: Mapped[list] = mapped_column(_JSONType, nullable=False, default=list)

    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PredictionOutcome id={self.id!s} prediction_id={self.prediction_id!s} outcome_known={self.outcome_known}>"


__all__ = ["PredictionOutcome"]
