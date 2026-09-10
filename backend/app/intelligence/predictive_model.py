"""Future predictive-model interface — milestone items 42-44. An
abstraction only: **no sophisticated predictive model is trained or
implemented in this milestone**, and nothing in this codebase calls
`PredictiveModel.predict()` from any API route. This module exists so a
future milestone (logistic regression, gradient boosting, a time-series
model, ...) has a stable interface to implement, and so this milestone's
own architecture can be reviewed against what predictions from it will
eventually have to look like — without fabricating a probability today
(milestone item 29).

    Prediction
        -> model / model_version
        -> feature_snapshot   (app/intelligence/features.py's FeatureValue set)
        -> supporting_signals (app/intelligence/signals.py's RiskSignal list)
        -> explanation
        -> Feature -> Source events -> Source system -> Original record

This is the explainability chain milestone item 44 requires end to end.
`NullPredictiveModel` is the one concrete implementation in this
codebase — it deliberately raises `NotImplementedError` from `predict()`,
proving the interface is wired and testable without ever producing a
number that could be mistaken for a real prediction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class Prediction:
    """The eventual target output structure (milestone item 43) —
    documented here, never populated with a fabricated value by this
    milestone. `risk_score`/`probability` stay `None` until a real,
    validated model exists to compute them."""

    entity_type: str
    entity_id: uuid.UUID | None
    prediction_time: datetime
    horizon_days: int
    risk_score: float | None = None
    probability: float | None = None
    model_name: str = ""
    model_version: str = ""
    feature_snapshot: dict[str, Any] = field(default_factory=dict)
    explanation: dict[str, Any] | None = None
    data_quality: str = ""
    supporting_signals: list[Any] = field(default_factory=list)


@runtime_checkable
class PredictiveModel(Protocol):
    """The interface a future model implements — logistic regression,
    gradient boosting, random forest, a time-series model, or otherwise
    (milestone item 42). Not implemented against real training data by
    this milestone."""

    model_name: str
    model_version: str

    def fit(self, training_data: Any) -> None: ...

    def predict(self, feature_snapshot: dict[str, Any]) -> Prediction: ...

    def explain(self, prediction: Prediction) -> dict[str, Any]: ...


class NullPredictiveModel:
    """Proves the `PredictiveModel` interface is usable and testable
    without implementing any actual prediction logic — see module
    docstring. Never wired into any API route."""

    model_name = "null-predictive-model"
    model_version = "unimplemented"

    def fit(self, training_data: Any) -> None:
        raise NotImplementedError(
            "No predictive model has been trained in this milestone -- "
            "see app/intelligence/predictive_model.py's module docstring."
        )

    def predict(self, feature_snapshot: dict[str, Any]) -> Prediction:
        raise NotImplementedError(
            "No predictive model exists yet. This milestone establishes the "
            "data/feature foundation a future predictive model will use -- "
            "it does not fabricate a risk_score or probability. See "
            "app/intelligence/predictive_model.py's module docstring."
        )

    def explain(self, prediction: Prediction) -> dict[str, Any]:
        raise NotImplementedError("No predictive model exists yet -- see predict().")
