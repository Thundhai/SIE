"""ModelReviewFlag — milestone items 31-32: the durable record of "this
deployed model's monitored performance/drift crossed a threshold and a
human needs to look at it."

**Never triggers automatic retraining (milestone item 32,
non-negotiable).** `app/predictions/drift.py::check_model_for_review()`
only ever creates a row here and audit-logs it — nothing in this
codebase reads a `ModelReviewFlag` and retrains, redeploys, or retires a
model on its own. A flag is closed by a human explicitly acknowledging
it (`status` moves `OPEN -> ACKNOWLEDGED`), typically alongside a
separate, manual retraining/governance decision outside this table
entirely.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow


class ModelReviewFlag(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "model_review_flags"

    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_registry_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )

    reason: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. PERFORMANCE_DRIFT, FEATURE_DRIFT, DATA_DRIFT
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    historical_value: Mapped[float | None] = mapped_column(nullable=True)
    current_value: Mapped[float | None] = mapped_column(nullable=True)
    detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")  # OPEN | ACKNOWLEDGED

    flagged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModelReviewFlag id={self.id!s} model_id={self.model_id!s} reason={self.reason!r} status={self.status!r}>"


__all__ = ["ModelReviewFlag"]
