"""Hand-rolled logistic regression + preprocessor — milestone item 20.
Pure unit tests, no database."""

import math

from app.predictions.logistic_regression import (
    FeaturePreprocessor,
    LogisticRegressionModel,
)


def test_model_separates_a_trivially_linearly_separable_dataset():
    X = [[0.0], [0.1], [0.2], [5.0], [5.1], [5.2]]
    y = [0, 0, 0, 1, 1, 1]
    model = LogisticRegressionModel(epochs=300, learning_rate=0.5).fit(X, y)
    assert model.predict([0.1]) == 0
    assert model.predict([5.1]) == 1


def test_predict_proba_is_a_valid_probability():
    model = LogisticRegressionModel(epochs=50).fit([[0.0], [1.0]], [0, 1])
    p = model.predict_proba([0.5])
    assert 0.0 <= p <= 1.0


def test_fit_rejects_mismatched_lengths():
    import pytest

    with pytest.raises(ValueError):
        LogisticRegressionModel().fit([[0.0], [1.0]], [0])


def test_fit_rejects_empty_dataset():
    import pytest

    with pytest.raises(ValueError):
        LogisticRegressionModel().fit([], [])


def test_params_round_trip_reconstructs_an_identical_model():
    model = LogisticRegressionModel(epochs=50).fit([[0.0], [1.0], [2.0]], [0, 0, 1])
    restored = LogisticRegressionModel.from_params(model.to_params())
    for x in ([0.0], [0.5], [1.5], [3.0]):
        assert math.isclose(model.predict_proba(x), restored.predict_proba(x))


def test_preprocessor_imputes_missing_values_with_the_training_mean():
    rows = [{"a": 1.0}, {"a": 3.0}, {"a": None}]
    pre = FeaturePreprocessor(feature_names=("a",)).fit(rows)
    assert pre.means["a"] == 2.0
    transformed = pre.transform([{"a": None}])
    # standardized imputed value is always exactly 0 (mean - mean) / stdev
    assert transformed[0][0] == 0.0
    # and the companion missingness-indicator column is set
    assert transformed[0][1] == 1.0


def test_preprocessor_never_divides_by_zero_for_a_constant_feature():
    rows = [{"a": 5.0}, {"a": 5.0}, {"a": 5.0}]
    pre = FeaturePreprocessor(feature_names=("a",)).fit(rows)
    transformed = pre.transform([{"a": 5.0}])
    assert transformed[0][0] == 0.0  # (5 - 5) / 1.0 -- never a ZeroDivisionError


def test_preprocessor_statistics_come_only_from_the_fit_call_never_from_transform_input():
    train_rows = [{"a": 1.0}, {"a": 1.0}]
    pre = FeaturePreprocessor(feature_names=("a",)).fit(train_rows)
    # transforming wildly different data must not change the stored means/stdevs
    pre.transform([{"a": 1000.0}])
    assert pre.means["a"] == 1.0


def test_missing_flag_is_zero_when_value_is_present():
    pre = FeaturePreprocessor(feature_names=("a", "b")).fit([{"a": 1.0, "b": 2.0}])
    row = pre.transform([{"a": 1.0, "b": None}])[0]
    n = 2
    assert row[n + 0] == 0.0  # "a" present
    assert row[n + 1] == 1.0  # "b" missing
