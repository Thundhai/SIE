"""ModelRegistryEntry — the minimal model registry (milestone item 24).
Not MLflow, not a general ML-infrastructure product — one table
recording everything needed to reproduce, audit, and govern one trained
model version.

**Named `ModelRegistryEntry`, not `PredictiveModel`**, specifically to
avoid colliding with `app.intelligence.predictive_model.PredictiveModel`
— that is the abstract `Protocol` documenting the eventual model
interface (`fit`/`predict`/`explain`); this is the concrete database row
one trained instance of a model implementing it is registered under. See
`app/predictions/logistic_regression.py` for the one concrete model this
milestone actually trains.

**Tenant-safe by construction (milestone item 43).** `organization_id`
is required (`OrganizationScopedMixin`) — a model is always trained on,
and only ever serves, one organization's own data. There is no
cross-tenant/shared model in this milestone; training a pooled model
across organizations would require a new, explicitly-designed and
authorized mechanism, not an accidental side effect of this table's
shape.

**Status lifecycle (milestone items 25-26)** —
`app/predictions/enums.py::ModelStatus` — `TRAINED -> VALIDATED ->
APPROVED -> DEPLOYED`, with `RETIRED`/`REJECTED` as terminal states.
Training itself only ever produces a `TRAINED` row; every later
transition is a deliberate, separate, audited call
(`app/predictions/model_registry.py`) — nothing in this codebase
auto-promotes a model to `APPROVED`/`DEPLOYED`.

**Never overwritten.** A new training run always creates a new row (a
new `model_version`); historical rows are retained (`RETIRED`, not
deleted) so a past prediction's `model_id` always still resolves to the
exact model that produced it.
"""

from datetime import date

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import Date, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class ModelRegistryEntry(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "model_registry_entries"
    __table_args__ = (
        UniqueConstraint("organization_id", "model_name", "model_version", name="uq_model_registry_name_version"),
    )

    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "logistic_regression"
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "site" for v0.1
    prediction_target_version: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. "elevated-safety-event-risk-v1"
    label_definition_version: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. "incident-target-v1"
    feature_set_version: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. "predictive-features-v1"
    training_data_version: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. "safety-risk-v1"
    horizon_days: Mapped[int] = mapped_column(nullable=False)

    training_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    training_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    validation_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    validation_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    test_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    test_period_end: Mapped[date] = mapped_column(Date, nullable=False)

    hyperparameters: Mapped[dict] = mapped_column(_JSONType, nullable=False, default=dict)

    # {train: {...}, validation: {...}, test: {...}} -- see
    # app/predictions/metrics.py. Precision/recall/PR-AUC/ROC-AUC/F1/
    # calibration, reported separately for sufficient- vs limited-data
    # entities (milestone item 41) -- never one combined "accuracy".
    metrics: Mapped[dict] = mapped_column(_JSONType, nullable=False, default=dict)

    # Trained parameters, persisted so this row alone can reconstruct
    # the model for prediction/explanation without re-training --
    # {feature_names, coefficients, intercept, feature_means, feature_stds}.
    # See app/predictions/logistic_regression.py.
    parameters: Mapped[dict] = mapped_column(_JSONType, nullable=False, default=dict)

    # Whether app/predictions/metrics.py's calibration check passed --
    # gates whether Prediction.probability may ever be populated for
    # this model (milestone items 18-19: no fake probabilities).
    calibration_validated: Mapped[bool] = mapped_column(nullable=False, default=False)

    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ModelRegistryEntry id={self.id!s} model_name={self.model_name!r} "
            f"model_version={self.model_version!r} status={self.status!r}>"
        )
