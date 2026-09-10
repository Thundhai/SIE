"""Explainability — milestone item 28.

A hand-rolled logistic regression (`logistic_regression.py`) is linear in
its (standardized) inputs, so each feature's contribution to a single
prediction is exactly `weight_i * standardized_value_i` — no approximation,
no separate "explainer model" needed the way a black-box model would
require.

**Language discipline is the point of this module, not just the math.**
Every result here is described as a "contributing feature" with a
"model association" to the prediction — never as a *cause*. A logistic
regression coefficient describes a correlation the model found in
historical, possibly reporting-biased data (see
`app/predictions/spec.py`, item 5) — it is not a causal claim about the
real world, and nothing in this codebase is entitled to word it as one.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.predictions.logistic_regression import (
    FeaturePreprocessor,
    LogisticRegressionModel,
)

DEFAULT_TOP_N = 5

DIRECTION_LABELS = {
    "positive": "associated with higher modeled risk in this model",
    "negative": "associated with lower modeled risk in this model",
}


@dataclass
class FeatureContribution:
    feature_name: str
    contribution: float  # weight_i * standardized_value_i, this prediction only
    direction: str  # "positive" | "negative"
    raw_value: float | None  # the feature's own (un-standardized) value, for readability
    is_missing: bool  # True if this feature was imputed (see FeaturePreprocessor)
    association_note: str


@dataclass
class Explanation:
    top_positive: list[FeatureContribution]
    top_negative: list[FeatureContribution]
    method: str = "logistic-regression-coefficient-contribution"
    disclaimer: str = (
        "These are features the model statistically associated with elevated or reduced "
        "risk in its training data. They describe a model association, not a cause."
    )


def explain_prediction(
    model: LogisticRegressionModel,
    preprocessor: FeaturePreprocessor,
    feature_vector: dict[str, float | None],
    *,
    top_n: int = DEFAULT_TOP_N,
) -> Explanation:
    encoded_row = preprocessor.transform([feature_vector])[0]
    n_features = len(preprocessor.feature_names)

    contributions: list[FeatureContribution] = []
    for i, name in enumerate(preprocessor.feature_names):
        standardized_value = encoded_row[i]
        missing_flag = encoded_row[n_features + i]
        is_missing = bool(missing_flag)
        value_weight = model.weights[i] if i < len(model.weights) else 0.0
        missing_weight = model.weights[n_features + i] if n_features + i < len(model.weights) else 0.0
        # A feature's total effect on the score is both terms the
        # preprocessor produced for it: its (standardized, imputed-at-mean
        # when missing) value, AND the missingness-indicator column's own
        # weight -- a missing feature's *value* term is always exactly 0
        # (imputed at the training mean), but the model may still have
        # learned that missingness itself is informative; omitting the
        # second term would silently under-report a missing feature's
        # real contribution to the prediction.
        contribution = value_weight * standardized_value + missing_weight * missing_flag
        contributions.append(
            FeatureContribution(
                feature_name=name,
                contribution=round(contribution, 6),
                direction="positive" if contribution >= 0 else "negative",
                raw_value=feature_vector.get(name),
                is_missing=is_missing,
                association_note=DIRECTION_LABELS["positive" if contribution >= 0 else "negative"],
            )
        )

    positive = sorted((c for c in contributions if c.contribution > 0), key=lambda c: -c.contribution)
    negative = sorted((c for c in contributions if c.contribution < 0), key=lambda c: c.contribution)

    return Explanation(top_positive=positive[:top_n], top_negative=negative[:top_n])


__all__ = ["Explanation", "FeatureContribution", "explain_prediction"]
