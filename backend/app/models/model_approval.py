"""ModelApproval — milestone item 23: the human-approval record.

**The model can never approve itself.** `app/predictions/model_registry.py::approve()`
requires a `reviewer_user_id` and refuses to proceed without one — this
row is the durable evidence of who approved what, when, and on the basis
of which validation report; it is written in the same call that
transitions a `ModelRegistryEntry` from `VALIDATED` to `APPROVED` (never
separately, so an `APPROVED` model can never exist without a matching
approval record).
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class ModelApproval(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "model_approvals"

    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_registry_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)

    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # APPROVE | REJECT
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # A snapshot of app/predictions/governance.py::generate_validation_report()
    # at the moment of this decision -- never recomputed retroactively, so
    # a past approval remains explainable even if later data changes what
    # the report would say today.
    validation_report: Mapped[dict] = mapped_column(_JSONType, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModelApproval id={self.id!s} model_id={self.model_id!s} decision={self.decision!r}>"


__all__ = ["ModelApproval"]
