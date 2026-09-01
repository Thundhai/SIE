"""Gradient Boosting comparison baseline — Model Validation & Governance
v0.1, items 8-9, 39. Pure unit tests, no database."""

import random

import pytest

from app.predictions.gradient_boosting import (
    GradientBoostingModel,
    explain_gradient_boosting,
)
from app.predictions.logistic_regression import FeaturePreprocessor
from app.predictions.vectorization import FEATURE_NAMES


def _toy_dataset():
    random.seed(0)
    rows, labels = [], []
    for _ in range(150):
        x = {name: random.random() * 10 for name in FEATURE_NAMES}
        y = 1 if x[FEATURE_NAMES[0]] > 5 else 0
        rows.append(x)
        labels.append(y)
    return rows, labels


def test_gradient_boosting_model_fits_and_scores():
    rows, labels = _toy_dataset()
    pre = FeaturePreprocessor().fit(rows)
    X = pre.transform(rows)
    model = GradientBoostingModel(n_estimators=50).fit(X, labels)
    proba = model.predict_proba(X[0])
    assert 0.0 <= proba <= 1.0


def test_gradient_boosting_rejects_a_single_class_training_set():
    rows, _ = _toy_dataset()
    pre = FeaturePreprocessor().fit(rows)
    X = pre.transform(rows)
    with pytest.raises(ValueError):
        GradientBoostingModel().fit(X, [0] * len(X))


def test_gradient_boosting_params_round_trip_reconstructs_an_identical_model():
    rows, labels = _toy_dataset()
    pre = FeaturePreprocessor().fit(rows)
    X = pre.transform(rows)
    model = GradientBoostingModel(n_estimators=30).fit(X, labels)
    restored = GradientBoostingModel.from_params(model.to_params())
    for x in X[:5]:
        assert model.predict_proba(x) == pytest.approx(restored.predict_proba(x))


def test_gradient_boosting_explanation_is_global_not_per_prediction():
    """Milestone item 39: a suitable explanation mechanism for Gradient
    Boosting -- global feature importance, explicitly not a
    per-prediction breakdown the way logistic regression's is."""
    rows, labels = _toy_dataset()
    pre = FeaturePreprocessor().fit(rows)
    X = pre.transform(rows)
    model = GradientBoostingModel(n_estimators=50).fit(X, labels)
    importances = explain_gradient_boosting(model, pre, top_n=5)
    assert len(importances) <= 5
    # The one genuinely informative feature should dominate.
    assert importances[0].feature_name == FEATURE_NAMES[0]
    assert importances[0].importance > 0


def test_gradient_boosting_explanation_never_uses_causal_language():
    import inspect

    import app.predictions.gradient_boosting as gb_module

    source = inspect.getsource(gb_module.explain_gradient_boosting)
    assert "causes" not in source.lower()
    assert "never described as causal" in inspect.getsource(gb_module).lower()
