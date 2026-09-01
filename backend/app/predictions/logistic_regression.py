"""Hand-rolled, pure-Python logistic regression — milestone item 20.

**Deliberately not scikit-learn/numpy**, even though both happen to be
importable in this sandbox: neither is a declared dependency of this
project (see `requirements.txt`), and every prior milestone in this
codebase has consistently avoided adding a heavy ML/numeric dependency
where a small, auditable, pure-Python implementation suffices (the
hashing embedding provider over `sentence-transformers`, the fake LLM
provider over a commercial SDK). A hand-rolled model is also the more
"auditable" choice the milestone explicitly asks for: every line of the
gradient-descent loop below is inspectable, not a call into an opaque
optimized routine.

**Deliberately not a neural network, LSTM, transformer, or large
ensemble** — milestone item 20 rules those out explicitly. Logistic
regression is linear-in-its-inputs and its coefficients are directly
interpretable, which is what makes `explain.py`'s "contributing feature"
output honest.

    FeaturePreprocessor.fit(training feature dicts)
        -> per-feature training-set mean/stdev (imputation + standardization
           statistics, computed on the *training* split only -- see
           `fit()`'s own docstring on leakage)
    FeaturePreprocessor.transform(feature dicts)
        -> list[list[float]] -- one standardized, imputed value column per
           feature name, plus one missingness-indicator column per
           feature name (never silently pretending an imputed value was
           observed)
    LogisticRegressionModel.fit(X, y) -> gradient descent with L2 regularization
    LogisticRegressionModel.predict_proba(x) -> sigmoid(w . x + b)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.predictions.vectorization import FEATURE_NAMES

MODEL_TYPE = "logistic_regression"
MODEL_IMPLEMENTATION_VERSION = "hand-rolled-logistic-regression-v1"

DEFAULT_L2 = 1.0
DEFAULT_LEARNING_RATE = 0.1
DEFAULT_EPOCHS = 500


@dataclass
class FeaturePreprocessor:
    """Imputation + standardization, fit on a training split only.

    **Never replaces a missing value with a fabricated `0.0` silently**
    (milestone item 10's "no fabricated feature values" extended to the
    model input, not just the stored snapshot): a missing feature is
    imputed with the *training set's own mean* for that feature (a
    standard, defensible choice for a linear model — the imputed value
    contributes nothing beyond the population average) **and** a
    companion missingness-indicator column is added so the model can
    still learn from the fact that the value was unavailable, rather
    than have that information silently disappear. The persisted
    `FeatureSnapshot.features` is never touched by this — it keeps its
    true `value=None`; this imputation exists only inside the transient
    numeric array a model actually consumes.
    """

    feature_names: tuple[str, ...] = FEATURE_NAMES
    means: dict[str, float] = field(default_factory=dict)
    stdevs: dict[str, float] = field(default_factory=dict)
    fitted: bool = False

    def fit(self, feature_dicts: list[dict[str, float | None]]) -> FeaturePreprocessor:
        """Statistics are computed **only** from `feature_dicts`
        (intended to be the training split) — never from validation/test
        data, which would leak future-partition information into how
        training examples themselves are standardized."""
        for name in self.feature_names:
            values = [d.get(name) for d in feature_dicts if d.get(name) is not None]
            if values:
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                stdev = math.sqrt(variance)
            else:
                mean, stdev = 0.0, 0.0
            self.means[name] = mean
            self.stdevs[name] = stdev if stdev > 1e-9 else 1.0  # a constant/all-missing column never divides by 0
        self.fitted = True
        return self

    def transform(self, feature_dicts: list[dict[str, float | None]]) -> list[list[float]]:
        if not self.fitted:
            raise RuntimeError("FeaturePreprocessor.transform() called before fit()")
        rows: list[list[float]] = []
        for d in feature_dicts:
            values: list[float] = []
            missing_flags: list[float] = []
            for name in self.feature_names:
                raw = d.get(name)
                if raw is None:
                    values.append(0.0)  # standardized imputed value -- (mean - mean) / stdev == 0
                    missing_flags.append(1.0)
                else:
                    values.append((raw - self.means[name]) / self.stdevs[name])
                    missing_flags.append(0.0)
            rows.append(values + missing_flags)
        return rows

    @property
    def input_dimension(self) -> int:
        return len(self.feature_names) * 2

    def to_params(self) -> dict:
        return {
            "feature_names": list(self.feature_names),
            "means": self.means,
            "stdevs": self.stdevs,
        }

    @classmethod
    def from_params(cls, params: dict) -> FeaturePreprocessor:
        return cls(
            feature_names=tuple(params["feature_names"]),
            means=dict(params["means"]),
            stdevs=dict(params["stdevs"]),
            fitted=True,
        )


def _sigmoid(z: float) -> float:
    # Clip to avoid OverflowError on math.exp() for very large |z|.
    z = max(-60.0, min(60.0, z))
    return 1.0 / (1.0 + math.exp(-z))


@dataclass
class LogisticRegressionModel:
    weights: list[float] = field(default_factory=list)
    bias: float = 0.0
    l2: float = DEFAULT_L2
    learning_rate: float = DEFAULT_LEARNING_RATE
    epochs: int = DEFAULT_EPOCHS
    fitted: bool = False

    def fit(self, X: list[list[float]], y: list[int]) -> LogisticRegressionModel:
        if not X:
            raise ValueError("Cannot fit a model on zero training examples.")
        if len(X) != len(y):
            raise ValueError("X and y must have the same length.")
        n, d = len(X), len(X[0])
        self.weights = [0.0] * d
        self.bias = 0.0

        for _ in range(self.epochs):
            grad_w = [0.0] * d
            grad_b = 0.0
            for xi, yi in zip(X, y):
                pred = _sigmoid(sum(w * x for w, x in zip(self.weights, xi)) + self.bias)
                error = pred - yi
                for j in range(d):
                    grad_w[j] += error * xi[j]
                grad_b += error
            for j in range(d):
                # L2 regularization on the weights only, never the bias.
                grad_w[j] = grad_w[j] / n + (self.l2 / n) * self.weights[j]
                self.weights[j] -= self.learning_rate * grad_w[j]
            self.bias -= self.learning_rate * (grad_b / n)

        self.fitted = True
        return self

    def predict_proba(self, x: list[float]) -> float:
        if not self.fitted:
            raise RuntimeError("LogisticRegressionModel.predict_proba() called before fit()")
        return _sigmoid(sum(w * xi for w, xi in zip(self.weights, x)) + self.bias)

    def predict(self, x: list[float], *, threshold: float = 0.5) -> int:
        return 1 if self.predict_proba(x) >= threshold else 0

    def to_params(self) -> dict:
        return {
            "model_type": MODEL_TYPE,
            "implementation_version": MODEL_IMPLEMENTATION_VERSION,
            "weights": list(self.weights),
            "bias": self.bias,
            "l2": self.l2,
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
        }

    @classmethod
    def from_params(cls, params: dict) -> LogisticRegressionModel:
        return cls(
            weights=list(params["weights"]),
            bias=params["bias"],
            l2=params.get("l2", DEFAULT_L2),
            learning_rate=params.get("learning_rate", DEFAULT_LEARNING_RATE),
            epochs=params.get("epochs", DEFAULT_EPOCHS),
            fitted=True,
        )
