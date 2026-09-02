"""HseExpertReview — Real Enterprise Dataset Validation Foundation v0.1,
item 8: a structured, persisted mechanism for a *future* human HSE
expert to review terminology mappings, quarantined records, unexpected
classifications, representative intelligence outputs, and risk
indicators this pipeline produced.

**An evaluation mechanism only — never an automated safety-approval
workflow.** Nothing in this codebase reads `HseExpertReview.outcome` and
changes ingestion, mapping, or intelligence behavior based on it; a row
here records a human's judgment for later reference, exactly the same
non-automation boundary `ModelReviewFlag` (Predictive Model Validation &
Governance v0.1) already draws for model-performance review — see that
model's own docstring for the identical reasoning applied to a different
target.

    target_type + target_reference  -- WHAT is being reviewed (never a
        strict foreign key: a terminology-mapping entry or an aggregate
        intelligence-output row is not always a database row with its
        own id)
    provenance                       -- a snapshot of the underlying
        record/output's own provenance *at review-creation time*, so the
        review stays meaningful even if the underlying data later changes
    outcome + reviewer_comment       -- the human's judgment, once given
        (CORRECT / INCORRECT / PARTIALLY_CORRECT / NOT_ENOUGH_INFORMATION)

`outcome` is nullable — a row is created the moment something is queued
for review (`outcome=None`, "pending") and updated once a reviewer
actually looks at it; this lets a caller build a review queue (every row
with `outcome IS NULL`) without a separate queue table.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")

#: `target_type` vocabulary (item 8's own list) — a plain string column,
#: not a DB-level enum, matching this codebase's existing convention for
#: this kind of small, reviewable vocabulary (see e.g. `ModelReviewFlag.reason`).
TARGET_TYPES = (
    "TERMINOLOGY_MAPPING",
    "QUARANTINED_RECORD",
    "CLASSIFICATION",
    "INTELLIGENCE_OUTPUT",
    "RISK_INDICATOR",
)

#: `outcome` vocabulary (item 8's own list).
REVIEW_OUTCOMES = ("CORRECT", "INCORRECT", "PARTIALLY_CORRECT", "NOT_ENOUGH_INFORMATION")


class HseExpertReview(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "hse_expert_reviews"

    target_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_reference: Mapped[str] = mapped_column(String(500), nullable=False)

    # A snapshot, not a live join -- e.g. {"batch_id": ..., "source_record_id": ...,
    # "content_hash": ...} for a quarantined record, or {"signal_type": ...,
    # "organization_id": ..., "as_of": ..., "window_days": ...} for an
    # intelligence output. Never a raw, full payload dump (see this
    # module's own security note in docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md).
    provenance: Mapped[dict[str, Any]] = mapped_column(_JSONType, nullable=False, default=dict)

    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)  # REVIEW_OUTCOMES, or None = pending
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship()  # noqa: F821
    reviewer: Mapped["User | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HseExpertReview id={self.id!s} target_type={self.target_type!r} "
            f"target_reference={self.target_reference!r} outcome={self.outcome!r}>"
        )


__all__ = ["REVIEW_OUTCOMES", "TARGET_TYPES", "HseExpertReview"]
