"""Gradient Boosting comparison baseline — Model Validation & Governance
v0.1, items 8-9.

**A deliberate, milestone-directed exception to the rest of this
codebase's no-heavy-ML-dependency policy** (the Logistic Regression
baseline, `app/predictions/logistic_regression.py`, stays hand-rolled,
pure Python — this milestone's own instruction is the opposite for
Gradient Boosting: "prefer established, well-maintained libraries over
hand-rolling complex ML algorithms"). `scikit-learn`'s
`GradientBoostingClassifier` is exactly that — a small, well-understood,
widely-used implementation; nothing here reimplements gradient-boosted
trees from scratch, and nothing here reaches for a heavier
training/serving platform (see item 52's "do not overbuild").

**Same preprocessing as the Logistic Regression baseline
(`app/predictions/logistic_regression.py::FeaturePreprocessor`)** — same
mean-imputation-plus-missingness-indicator treatment for a missing
feature, same training-split-only statistics — so Model A and Model B
are compared on identical inputs (milestone item 8: "use the same
feature set... for both"), not two different missing-data policies.

**Serialization.** A fitted `GradientBoostingClassifier` is a tree
ensemble, not a small list of floats — there is no honest, lossless
JSON-native representation of it the way `LogisticRegressionModel.to_params()`
has for a handful of weights. `to_params()`/`from_params()` therefore
pickle the fitted estimator and store it base64-encoded inside the same
JSON `parameters` column `ModelRegistryEntry.parameters` already uses —
documented here as the honest trade-off it is, not hidden: the model is
still fully reproducible from this row, but its internals are not
directly human-readable the way the logistic regression's coefficients
are (see `explain_gradient_boosting()` below for what *is* exposed).
"""

from __future__ import annotations

import base64
import pickle
from dataclasses import dataclass, field

from sklearn.ensemble import GradientBoostingClassifier

from app.predictions.logistic_regression import FeaturePreprocessor
from app.predictions.vectorization import FEATURE_NAMES

MODEL_TYPE = "gradient_boosting"
MODEL_IMPLEMENTATION_VERSION = "sklearn-gradient-boosting-classifier-v1"

DEFAULT_N_ESTIMATORS = 100
DEFAULT_MAX_DEPTH = 3
DEFAULT_LEARNING_RATE = 0.1
DEFAULT_RANDOM_STATE = 42


@dataclass
class GradientBoostingModel:
    n_estimators: int = DEFAULT_N_ESTIMATORS
    max_depth: int = DEFAULT_MAX_DEPTH
    learning_rate: float = DEFAULT_LEARNING_RATE
    random_state: int = DEFAULT_RANDOM_STATE
    fitted: bool = False
    _estimator: GradientBoostingClassifier | None = field(default=None, repr=False)

    def fit(self, X: list[list[float]], y: list[int]) -> GradientBoostingModel:
        if not X:
            raise ValueError("Cannot fit a model on zero training examples.")
        if len(X) != len(y):
            raise ValueError("X and y must have the same length.")
        if len(set(y)) < 2:
            raise ValueError("Cannot fit a classifier on a single-class training set.")
        self._estimator = GradientBoostingClassifier(
            n_estimators=self.n_estimators, max_depth=self.max_depth,
            learning_rate=self.learning_rate, random_state=self.random_state,
        )
        self._estimator.fit(X, y)
        self.fitted = True
        return self

    def predict_proba(self, x: list[float]) -> float:
        if not self.fitted or self._estimator is None:
            raise RuntimeError("GradientBoostingModel.predict_proba() called before fit()")
        # [:, 1] -- probability of the positive class (label=1).
        return float(self._estimator.predict_proba([x])[0][1])

    def predict(self, x: list[float], *, threshold: float = 0.5) -> int:
        return 1 if self.predict_proba(x) >= threshold else 0

    @property
    def feature_importances(self) -> list[float] | None:
        if not self.fitted or self._estimator is None:
            return None
        return list(self._estimator.feature_importances_)

    def to_params(self) -> dict:
        return {
            "model_type": MODEL_TYPE,
            "implementation_version": MODEL_IMPLEMENTATION_VERSION,
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "learning_rate": self.learning_rate,
            "random_state": self.random_state,
            # See module docstring on this trade-off.
            "estimator_pickle_b64": base64.b64encode(pickle.dumps(self._estimator)).decode("ascii"),
        }

    @classmethod
    def from_params(cls, params: dict) -> GradientBoostingModel:
        estimator = pickle.loads(base64.b64decode(params["estimator_pickle_b64"]))
        return cls(
            n_estimators=params.get("n_estimators", DEFAULT_N_ESTIMATORS),
            max_depth=params.get("max_depth", DEFAULT_MAX_DEPTH),
            learning_rate=params.get("learning_rate", DEFAULT_LEARNING_RATE),
            random_state=params.get("random_state", DEFAULT_RANDOM_STATE),
            fitted=True,
            _estimator=estimator,
        )


@dataclass
class FeatureImportance:
    feature_name: str
    importance: float


def explain_gradient_boosting(model: GradientBoostingModel, preprocessor: FeaturePreprocessor, *, top_n: int = 5) -> list[FeatureImportance]:
    """**Global**, not per-prediction, feature importance (milestone item
    39: "provide a suitable feature-importance/explanation mechanism" for
    Gradient Boosting) — `GradientBoostingClassifier.feature_importances_`
    reflects how much each input (each standardized value column, each
    missingness-indicator column) reduced impurity across the whole
    trained ensemble, not this one prediction's own drivers the way
    `app/predictions/explain.py`'s logistic-regression contributions do.
    **Never described as causal** — same discipline as the Logistic
    Regression explainer."""
    importances = model.feature_importances
    if importances is None:
        return []
    n_features = len(preprocessor.feature_names)
    # The first n_features columns are standardized values; the next
    # n_features are missingness indicators (see FeaturePreprocessor) --
    # combine both into one importance per named feature so the report
    # reads the same shape as the logistic regression's per-feature list.
    combined: dict[str, float] = {}
    for i, name in enumerate(preprocessor.feature_names):
        value_importance = importances[i] if i < len(importances) else 0.0
        missing_importance = importances[n_features + i] if n_features + i < len(importances) else 0.0
        combined[name] = value_importance + missing_importance

    ranked = sorted(combined.items(), key=lambda kv: -kv[1])[:top_n]
    return [FeatureImportance(feature_name=name, importance=round(score, 6)) for name, score in ranked]


__all__ = [
    "FEATURE_NAMES",
    "FeatureImportance",
    "GradientBoostingModel",
    "explain_gradient_boosting",
]
