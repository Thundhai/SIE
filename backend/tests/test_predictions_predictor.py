"""Prediction serving & abstention — milestone items 12-13, 27, 29-30,
32-34. DB-backed (SQLite) tests."""

from datetime import datetime, timedelta, timezone

from app.predictions import model_registry
from app.predictions.dataset import build_training_examples
from app.predictions.enums import AbstentionReason, ModelStatus, PredictionOutcome
from app.predictions.predictor import abstain_no_deployed_model, predict_as_of
from app.predictions.spec import (
    HORIZON_DAYS,
    MIN_HISTORICAL_DAYS,
    MIN_HISTORICAL_EVENT_COUNT,
)
from app.predictions.training import train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)
from tests.intelligence_test_helpers import make_org, make_reviewer_user, make_safety_event, make_site

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _deployed_model(db_session, *, seed=11):
    org, sites = seed_synthetic_organization(db_session, name="Predictor Org", site_names=["Site 1"], seed=seed)
    reviewer = make_reviewer_user(db_session)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)
    return org, sites[0], entry


def test_predict_as_of_abstains_with_cold_start_for_a_brand_new_site(db_session):
    org, _site, model = _deployed_model(db_session)
    new_site = make_site(db_session, org.id, name="Brand New Site")
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=new_site.id, as_of=AS_OF, model=model)
    assert prediction.outcome == PredictionOutcome.NO_PREDICTION.value
    assert prediction.abstention_reason == AbstentionReason.COLD_START.value
    assert prediction.risk_score is None


def test_predict_as_of_abstains_with_cold_start_when_history_is_shorter_than_the_minimum(db_session):
    org, _site, model = _deployed_model(db_session)
    site = make_site(db_session, org.id, name="Young Site")
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=AS_OF - timedelta(days=MIN_HISTORICAL_DAYS - 5),
            ingestion_time=AS_OF - timedelta(days=MIN_HISTORICAL_DAYS - 5),
        )
    )
    db_session.commit()
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF, model=model)
    assert prediction.abstention_reason == AbstentionReason.COLD_START.value


def test_predict_as_of_abstains_with_insufficient_historical_data_below_the_minimum_event_count(db_session):
    org, _site, model = _deployed_model(db_session)
    site = make_site(db_session, org.id, name="Sparse Site")
    assert MIN_HISTORICAL_EVENT_COUNT > 1
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=AS_OF - timedelta(days=MIN_HISTORICAL_DAYS + 5),
            ingestion_time=AS_OF - timedelta(days=MIN_HISTORICAL_DAYS + 5),
        )
    )
    db_session.commit()
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF, model=model)
    assert prediction.abstention_reason == AbstentionReason.INSUFFICIENT_HISTORICAL_DATA.value


def test_predict_as_of_abstains_with_stale_source_data(db_session):
    org, _site, model = _deployed_model(db_session)
    site = make_site(db_session, org.id, name="Stale Site")
    # Plenty of old history, but nothing recent -- source data is stale
    # relative to as_of.
    for d in range(120, 400, 10):
        db_session.add(
            make_safety_event(
                organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
                event_time=AS_OF - timedelta(days=d), ingestion_time=AS_OF - timedelta(days=d),
            )
        )
    db_session.commit()
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF, model=model)
    assert prediction.abstention_reason == AbstentionReason.STALE_SOURCE_DATA.value


def test_predict_as_of_abstains_when_the_model_is_not_deployed(db_session):
    org, site, model = _deployed_model(db_session)
    model_registry.retire(db_session, model)
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF, model=model)
    assert prediction.abstention_reason == AbstentionReason.MODEL_UNAVAILABLE.value


def test_predict_as_of_never_requires_deployed_when_used_for_internal_backtesting(db_session):
    """Milestone item 34: the same predict_as_of() function, called with
    require_deployed=False, is the internal backtesting mechanism -- it
    must be able to score against a merely TRAINED model."""
    org, sites = seed_synthetic_organization(db_session, name="Backtest Org", site_names=["Site 1"], seed=55)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    assert entry.status == ModelStatus.TRAINED.value

    prediction = predict_as_of(
        db_session, organization_id=org.id, site_id=sites[0].id, as_of=dates[-1], model=entry,
        require_deployed=False,
    )
    assert prediction.outcome == PredictionOutcome.PREDICTED.value


def test_a_successful_prediction_has_a_risk_score_and_category_but_no_fabricated_probability(db_session):
    org, sites = seed_synthetic_organization(db_session, name="Score Org", site_names=["Site 1"], seed=77)
    reviewer = make_reviewer_user(db_session)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)  # NOT calibrated
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)

    prediction = predict_as_of(db_session, organization_id=org.id, site_id=sites[0].id, as_of=dates[-1], model=entry)
    assert prediction.outcome == PredictionOutcome.PREDICTED.value
    assert prediction.risk_score is not None
    assert prediction.risk_category in ("ELEVATED", "MODERATE", "LOW")
    # calibration_validated=False -- never a fabricated probability.
    assert prediction.probability is None


def test_probability_is_populated_only_when_the_model_is_calibration_validated(db_session):
    org, sites = seed_synthetic_organization(db_session, name="Calibrated Org", site_names=["Site 1"], seed=88)
    reviewer = make_reviewer_user(db_session)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=True)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)

    prediction = predict_as_of(db_session, organization_id=org.id, site_id=sites[0].id, as_of=dates[-1], model=entry)
    assert prediction.probability is not None
    assert prediction.probability == prediction.risk_score


def test_prediction_provenance_chain_is_fully_inspectable(db_session):
    org, sites = seed_synthetic_organization(db_session, name="Provenance Org", site_names=["Site 1"], seed=66)
    reviewer = make_reviewer_user(db_session)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)

    prediction = predict_as_of(db_session, organization_id=org.id, site_id=sites[0].id, as_of=dates[-1], model=entry)
    assert prediction.model_id == entry.id
    assert prediction.feature_snapshot_id is not None
    # Prediction -> model_id -> ModelRegistryEntry, and
    # Prediction -> feature_snapshot_id -> FeatureSnapshot -- both foreign
    # keys resolve to real, inspectable rows.
    from app.models.feature_snapshot import FeatureSnapshot

    snapshot = db_session.get(FeatureSnapshot, prediction.feature_snapshot_id)
    assert snapshot is not None
    assert snapshot.organization_id == org.id


def test_explanation_is_present_only_on_a_predicted_outcome_never_on_an_abstention(db_session):
    org, _site, model = _deployed_model(db_session)
    new_site = make_site(db_session, org.id, name="Explanation Cold Start Site")
    abstained = predict_as_of(db_session, organization_id=org.id, site_id=new_site.id, as_of=AS_OF, model=model)
    assert abstained.explanation is None


def test_abstain_no_deployed_model_records_a_model_unavailable_abstention(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    prediction = abstain_no_deployed_model(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert prediction.outcome == PredictionOutcome.NO_PREDICTION.value
    assert prediction.abstention_reason == AbstentionReason.MODEL_UNAVAILABLE.value
    assert prediction.model_id is None


def test_abstention_still_records_the_horizon_and_entity(db_session):
    org, _site, model = _deployed_model(db_session)
    new_site = make_site(db_session, org.id, name="Yet Another New Site")
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=new_site.id, as_of=AS_OF, model=model)
    assert prediction.horizon_days == HORIZON_DAYS
    assert prediction.entity_id == new_site.id
    assert prediction.entity_type == "site"


def test_model_status_names_reflect_the_actual_governance_gap(db_session):
    """A merely-TRAINED model must abstain with MODEL_NOT_VALIDATED, not
    a generic reason -- the abstention reason should tell a caller
    exactly what governance step is missing."""
    org, sites = seed_synthetic_organization(db_session, name="Governance Org", site_names=["Site 1"], seed=44)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    trained_only = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    prediction = predict_as_of(
        db_session, organization_id=org.id, site_id=sites[0].id, as_of=dates[-1], model=trained_only
    )
    assert prediction.abstention_reason == AbstentionReason.MODEL_NOT_VALIDATED.value


def test_unsupported_entity_type_is_rejected(db_session):
    org, site, model = _deployed_model(db_session)
    model.entity_type = "worker"  # not a supported prediction unit
    db_session.commit()
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF, model=model)
    assert prediction.abstention_reason == AbstentionReason.UNSUPPORTED_ENTITY.value
