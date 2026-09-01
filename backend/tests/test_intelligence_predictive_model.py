"""Future predictive-model interface — milestone items 42-44. Proves the
interface is wired and testable without fabricating any prediction.
"""

import pytest

from app.intelligence.predictive_model import NullPredictiveModel, Prediction, PredictiveModel


def test_null_predictive_model_satisfies_the_protocol():
    model = NullPredictiveModel()
    assert isinstance(model, PredictiveModel)


def test_predict_raises_not_implemented_rather_than_fabricating_a_score():
    """Milestone item 29: no fake probabilities."""
    model = NullPredictiveModel()
    with pytest.raises(NotImplementedError):
        model.predict({"incident_count": 3})


def test_fit_raises_not_implemented():
    model = NullPredictiveModel()
    with pytest.raises(NotImplementedError):
        model.fit(training_data=[])


def test_explain_raises_not_implemented():
    model = NullPredictiveModel()
    with pytest.raises(NotImplementedError):
        model.explain(Prediction(entity_type="organization", entity_id=None, prediction_time=None, horizon_days=30))


def test_prediction_dataclass_defaults_never_populate_a_risk_score_or_probability():
    prediction = Prediction(entity_type="organization", entity_id=None, prediction_time=None, horizon_days=30)
    assert prediction.risk_score is None
    assert prediction.probability is None


def test_no_api_route_imports_or_calls_the_predictive_model_module():
    """Milestone items 29/42: nothing in this codebase should be wired
    to actually produce a prediction from any HTTP endpoint yet."""
    import inspect

    from app.api.v1 import intelligence as intelligence_api

    source = inspect.getsource(intelligence_api)
    assert "predictive_model" not in source
    assert "PredictiveModel" not in source
