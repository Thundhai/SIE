"""Model card — Model Validation & Governance v0.1, item 33.

Both machine-readable (`ModelCard.to_dict()`, what
`GET /api/v1/intelligence/models/{id}/card` returns) and human-readable
(`render_markdown()`) from the same one source: `ModelRegistryEntry`
plus the versioned constants in `app/predictions/spec.py`. Nothing on a
model card is invented per-call — every field is either a stored column
on the registry row or one of this codebase's own fixed, already-reviewed
policy statements (prohibited use, reporting-bias note, safety-language
note).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.model_registry_entry import ModelRegistryEntry
from app.predictions.spec import HORIZON_DAYS, REPORTING_BIAS_NOTE, SAFETY_LANGUAGE_NOTE
from app.predictions.vectorization import FEATURE_NAMES

# Milestone item 33's own example list, verbatim.
PROHIBITED_USES: tuple[str, ...] = (
    "Employee disciplinary decisions",
    "Individual worker risk scoring",
    "Employment decisions",
    "Automatic permit rejection",
    "Automatic equipment shutdown",
)

INTENDED_USE = (
    "Advisory input for HSE managers assessing elevated safety-event risk at the site level, "
    "over a defined horizon, to help prioritize attention and resources. A model estimate, not "
    "a certainty -- see the disclaimer below. Requires human review before any operational "
    "action is taken."
)


@dataclass
class ModelCard:
    model_id: uuid.UUID
    model_name: str
    model_version: str
    model_type: str
    status: str
    prediction_target_version: str
    label_definition_version: str
    feature_set_version: str
    training_data_version: str
    entity_type: str
    horizon_days: int
    training_period: tuple[str, str]
    validation_period: tuple[str, str]
    test_period: tuple[str, str]
    features: list[str]
    metrics: dict
    calibration_validated: bool
    intended_use: str
    prohibited_uses: list[str]
    known_limitations: list[str]
    safety_language_note: str
    reporting_bias_note: str
    notes: str | None

    def to_dict(self) -> dict:
        return {
            "model_id": str(self.model_id),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": self.model_type,
            "status": self.status,
            "prediction_target_version": self.prediction_target_version,
            "label_definition_version": self.label_definition_version,
            "feature_set_version": self.feature_set_version,
            "training_data_version": self.training_data_version,
            "entity_type": self.entity_type,
            "horizon_days": self.horizon_days,
            "training_period": list(self.training_period),
            "validation_period": list(self.validation_period),
            "test_period": list(self.test_period),
            "features": self.features,
            "metrics": self.metrics,
            "calibration_validated": self.calibration_validated,
            "intended_use": self.intended_use,
            "prohibited_uses": self.prohibited_uses,
            "known_limitations": self.known_limitations,
            "safety_language_note": self.safety_language_note,
            "reporting_bias_note": self.reporting_bias_note,
            "notes": self.notes,
        }


def _known_limitations(model: ModelRegistryEntry) -> list[str]:
    limitations = [
        (
            "Deterministic thresholds (data-sufficiency, staleness, risk category) are documented "
            "initial defaults, not statistically validated against real-world outcomes."
        ),
        (
            "No model monitoring for drift/performance degradation runs automatically -- see "
            "app/predictions/drift.py and app/predictions/monitoring.py, both on-demand only."
        ),
    ]
    if model.notes and "Synthetic" in model.notes:
        limitations.insert(
            0,
            "Trained and evaluated on synthetic data only -- see this model's own `notes` field. "
            "No claim is made about real-world predictive performance.",
        )
    if not model.calibration_validated:
        limitations.append("This model's probability output has not passed calibration validation -- see `calibration_validated`.")
    return limitations


def build_model_card(model: ModelRegistryEntry) -> ModelCard:
    return ModelCard(
        model_id=model.id,
        model_name=model.model_name,
        model_version=model.model_version,
        model_type=model.model_type,
        status=model.status,
        prediction_target_version=model.prediction_target_version,
        label_definition_version=model.label_definition_version,
        feature_set_version=model.feature_set_version,
        training_data_version=model.training_data_version,
        entity_type=model.entity_type,
        horizon_days=model.horizon_days or HORIZON_DAYS,
        training_period=(model.training_period_start.isoformat(), model.training_period_end.isoformat()),
        validation_period=(model.validation_period_start.isoformat(), model.validation_period_end.isoformat()),
        test_period=(model.test_period_start.isoformat(), model.test_period_end.isoformat()),
        features=list(FEATURE_NAMES),
        metrics=model.metrics or {},
        calibration_validated=model.calibration_validated,
        intended_use=INTENDED_USE,
        prohibited_uses=list(PROHIBITED_USES),
        known_limitations=_known_limitations(model),
        safety_language_note=SAFETY_LANGUAGE_NOTE,
        reporting_bias_note=REPORTING_BIAS_NOTE,
        notes=model.notes,
    )


def render_markdown(card: ModelCard) -> str:
    lines = [
        f"# Model Card: {card.model_name} ({card.model_version})",
        "",
        f"**Status:** {card.status}  ",
        f"**Model type:** {card.model_type}  ",
        f"**Prediction target:** {card.prediction_target_version}  ",
        f"**Entity type:** {card.entity_type}  ",
        f"**Horizon:** {card.horizon_days} days  ",
        "",
        "## Training configuration",
        f"- Training period: {card.training_period[0]} -> {card.training_period[1]}",
        f"- Validation period: {card.validation_period[0]} -> {card.validation_period[1]}",
        f"- Test period: {card.test_period[0]} -> {card.test_period[1]}",
        f"- Feature set version: {card.feature_set_version}",
        f"- Label definition version: {card.label_definition_version}",
        f"- Training data version: {card.training_data_version}",
        "",
        "## Intended use",
        card.intended_use,
        "",
        "## Prohibited use",
    ]
    lines += [f"- {u}" for u in card.prohibited_uses]
    lines += [
        "",
        "## Known limitations",
    ]
    lines += [f"- {limitation}" for limitation in card.known_limitations]
    lines += [
        "",
        "## Calibration",
        f"`calibration_validated={card.calibration_validated}` -- {'a validated probability is exposed on predictions from this model.' if card.calibration_validated else 'only a categorical risk_category is exposed; no probability is shown.'}",
        "",
        "## Reporting bias",
        card.reporting_bias_note,
        "",
        "## Safety language",
        card.safety_language_note,
    ]
    return "\n".join(lines)


__all__ = ["INTENDED_USE", "PROHIBITED_USES", "ModelCard", "build_model_card", "render_markdown"]
