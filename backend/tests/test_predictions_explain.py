"""Explainability — milestone item 28. Pure unit tests over
`explain_prediction()`, no database."""

from app.predictions.explain import explain_prediction
from app.predictions.logistic_regression import (
    FeaturePreprocessor,
    LogisticRegressionModel,
)


def _fit_toy_model():
    rows = [{"risk_feature": v, "safe_feature": 10 - v} for v in range(20)]
    labels = [1 if v >= 10 else 0 for v in range(20)]
    pre = FeaturePreprocessor(feature_names=("risk_feature", "safe_feature")).fit(rows)
    X = pre.transform(rows)
    model = LogisticRegressionModel(epochs=300, learning_rate=0.3).fit(X, labels)
    return model, pre


def test_top_positive_and_top_negative_contributions_are_returned():
    model, pre = _fit_toy_model()
    explanation = explain_prediction(model, pre, {"risk_feature": 15.0, "safe_feature": 0.0}, top_n=2)
    assert len(explanation.top_positive) <= 2
    assert len(explanation.top_negative) <= 2
    for c in explanation.top_positive:
        assert c.contribution > 0
    for c in explanation.top_negative:
        assert c.contribution < 0


def test_explanation_language_never_claims_causation():
    model, pre = _fit_toy_model()
    explanation = explain_prediction(model, pre, {"risk_feature": 15.0, "safe_feature": 0.0})
    # The disclaimer explicitly *disclaims* causation ("not a cause") --
    # that is the required phrasing, not an accidental appearance of the
    # word. It must never make an affirmative causal claim.
    assert "not a cause" in explanation.disclaimer.lower()
    assert "causes" not in explanation.disclaimer.lower()
    for c in explanation.top_positive + explanation.top_negative:
        assert "causes" not in c.association_note.lower()
        assert "association" in c.association_note.lower() or "associated" in c.association_note.lower()


def test_missingness_is_reflected_in_the_contribution():
    # Missingness itself must be informative in training for a missing
    # feature's contribution to be non-zero (a missingness-indicator
    # weight the model never saw vary during training stays at its
    # initial 0 -- see FeaturePreprocessor's own docstring on why a
    # feature imputed exactly at the training mean contributes nothing
    # from its *value* term alone).
    rows = [{"risk_feature": None if i % 2 == 0 else 1.0, "safe_feature": 1.0} for i in range(20)]
    labels = [1 if i % 2 == 0 else 0 for i in range(20)]  # missing -> elevated risk, by construction
    pre = FeaturePreprocessor(feature_names=("risk_feature", "safe_feature")).fit(rows)
    X = pre.transform(rows)
    model = LogisticRegressionModel(epochs=300, learning_rate=0.3).fit(X, labels)

    explanation = explain_prediction(model, pre, {"risk_feature": None, "safe_feature": 1.0})
    contributions = {c.feature_name: c for c in explanation.top_positive + explanation.top_negative}
    assert contributions["risk_feature"].is_missing is True
    assert contributions["risk_feature"].raw_value is None
    assert contributions["risk_feature"].contribution > 0  # the model learned missingness is elevated-risk here
