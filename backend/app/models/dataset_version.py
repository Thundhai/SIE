"""DatasetVersion — milestone items 4, 20 (Model Validation & Governance
v0.1): the identity and reproducibility record for one predictive
training/evaluation dataset.

**Environment is the load-bearing field (milestone item 3).** Every
dataset is tagged `SYNTHETIC` or `REAL` — `app/predictions/enums.py::DatasetEnvironment`
— and nothing in this codebase mixes them silently: a dataset built from
`tests/fixtures/predictions/synthetic_training_dataset.py` is always
`SYNTHETIC`; a dataset built from an organization's real ingested
`SafetyEvent` rows via `app/predictions/dataset_registry.py::register_real_dataset()`
is always `REAL`. Every evaluation result that references a dataset
carries this tag through to the model card and validation report, so a
synthetic result can never be presented as real-world performance.

**Reproducibility.** `dataset_id`/`dataset_version` together with
`feature_set_version`/`target_version`/`prediction_horizon_days` and the
`date_range` are what `app/predictions/model_registry.py` links a trained
model back to (`ModelRegistryEntry.dataset_version_id`) — enough to
reconstruct exactly what data a model was trained/validated/tested
against.

**`quality_report` is never fabricated.** Populated only by
`app/predictions/data_validation.py::validate_dataset()` — see that
module's own docstring for what it checks and why it never silently
repairs questionable data.
"""

from datetime import date, datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class DatasetVersion(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "dataset_id", "dataset_version", name="uq_dataset_versions_id_version"),
    )

    dataset_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # human-chosen label, e.g. "ORG-A-SAFETY"
    dataset_version: Mapped[str] = mapped_column(String(20), nullable=False)  # "v1", "v2", ...

    environment: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # SYNTHETIC | REAL

    source_systems: Mapped[list] = mapped_column(_JSONType, nullable=False, default=list)
    date_range_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_range_end: Mapped[date] = mapped_column(Date, nullable=False)

    feature_set_version: Mapped[str] = mapped_column(String(30), nullable=False)
    target_version: Mapped[str] = mapped_column(String(30), nullable=False)
    prediction_horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "site" for v0.1
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # See app/predictions/data_validation.py::DatasetQualityReport --
    # never a single collapsed score; structured completeness/
    # consistency/duplicate/temporal/freshness/distribution detail.
    quality_report: Mapped[dict] = mapped_column(_JSONType, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DatasetVersion id={self.id!s} dataset_id={self.dataset_id!r} "
            f"dataset_version={self.dataset_version!r} environment={self.environment!r}>"
        )


__all__ = ["DatasetVersion"]
