"""Outcome tracking and prediction/model performance monitoring — Model
Validation & Governance v0.1, items 26-28. DB-backed (SQLite) tests."""

from datetime import timedelta

import pytest

from app.predictions import model_registry
from app.predictions.dataset import build_training_examples
from app.predictions.enums import PredictionOutcome as PredictionOutcomeEnum
from app.predictions.monitoring import (
    compute_model_performance_monitoring,
    compute_prediction_monitoring,
)
from app.predictions.outcome_tracking import (
    evaluate_matured_outcomes,
    evaluate_prediction_outcome,
)
from app.predictions.predictor import predict_as_of
from app.predictions.training import train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)
from tests.intelligence_test_helpers import make_reviewer_user, make_site


def _deployed_model(db_session, *, seed=600):
    org, sites = seed_synthetic_organization(db_session, name="Monitoring Org", site_names=["S1"], seed=seed)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)
    return org, sites[0], entry, dates


def test_evaluate_prediction_outcome_refuses_to_evaluate_before_the_horizon_matures(db_session):
    org, site, model, dates = _deployed_model(db_session)
    as_of = dates[len(dates) // 2]
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=as_of, model=model)
    assert prediction.outcome == PredictionOutcomeEnum.PREDICTED.value

    outcome = evaluate_prediction_outcome(db_session, prediction_id=prediction.id, as_of_now=prediction.prediction_time)
    assert outcome is None  # not yet due -- never fabricated early

    partway = prediction.prediction_time + timedelta(days=prediction.horizon_days - 1)
    still_none = evaluate_prediction_outcome(db_session, prediction_id=prediction.id, as_of_now=partway)
    assert still_none is None


def test_evaluate_prediction_outcome_records_the_actual_label_once_matured(db_session):
    org, site, model, dates = _deployed_model(db_session)
    as_of = dates[len(dates) // 2]
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=as_of, model=model)

    matured_at = prediction.prediction_time + timedelta(days=prediction.horizon_days + 1)
    outcome = evaluate_prediction_outcome(db_session, prediction_id=prediction.id, as_of_now=matured_at)
    assert outcome.outcome_known is True
    assert outcome.actual_label in (0, 1)
    assert outcome.evaluated_at is not None


def test_evaluate_prediction_outcome_rejects_an_abstained_prediction(db_session):
    from app.predictions.predictor import abstain_no_deployed_model
    from tests.intelligence_test_helpers import make_org

    org = make_org(db_session)
    site = make_site(db_session, org.id)
    abstained = abstain_no_deployed_model(db_session, organization_id=org.id, site_id=site.id, as_of=as_of_dates()[0])
    with pytest.raises(ValueError):
        evaluate_prediction_outcome(db_session, prediction_id=abstained.id)


def test_evaluate_matured_outcomes_batches_every_due_prediction(db_session):
    org, site, model, dates = _deployed_model(db_session)
    # A prediction early enough in the dataset's span that its horizon
    # matures well before the dataset's own last date.
    as_of = dates[2]
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=as_of, model=model)
    matured_at = prediction.prediction_time + timedelta(days=prediction.horizon_days + 1)

    results = evaluate_matured_outcomes(db_session, organization_id=org.id, as_of_now=matured_at)
    assert len(results) == 1
    assert results[0].prediction_id == prediction.id

    # Calling again must not re-evaluate (already recorded) or duplicate rows.
    again = evaluate_matured_outcomes(db_session, organization_id=org.id, as_of_now=matured_at)
    assert again == []


def test_prediction_monitoring_reports_coverage_and_abstention(db_session):
    org, site, model, dates = _deployed_model(db_session)
    predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=dates[-1], model=model)

    new_site = make_site(db_session, org.id, name="Cold Site")
    predict_as_of(db_session, organization_id=org.id, site_id=new_site.id, as_of=dates[-1], model=model)

    summary = compute_prediction_monitoring(db_session, organization_id=org.id)
    assert summary.total_predictions == 2
    assert summary.predicted_count == 1
    assert summary.abstained_count == 1
    assert summary.abstention_rate == 0.5
    assert "COLD_START" in summary.abstention_reason_counts


def test_model_performance_monitoring_is_empty_until_outcomes_mature(db_session):
    org, site, model, dates = _deployed_model(db_session)
    predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=dates[-1], model=model)

    summary = compute_model_performance_monitoring(db_session, organization_id=org.id, model_id=model.id)
    assert summary.matured_outcome_count == 0
    assert summary.metrics is None


def test_model_performance_monitoring_reports_real_metrics_once_outcomes_are_recorded(db_session):
    org, site, model, dates = _deployed_model(db_session)
    as_of = dates[2]
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=as_of, model=model)
    matured_at = prediction.prediction_time + timedelta(days=prediction.horizon_days + 1)
    evaluate_prediction_outcome(db_session, prediction_id=prediction.id, as_of_now=matured_at)

    summary = compute_model_performance_monitoring(db_session, organization_id=org.id, model_id=model.id)
    assert summary.matured_outcome_count == 1
    assert summary.metrics is not None
    assert summary.metrics.sample_size == 1
