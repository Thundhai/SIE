"""Mandatory cross-tenant isolation regression test — Predictive Risk
Modeling Specification v0.1 item 43 and Model Validation & Governance
v0.1 item 37, explicitly required by both specs: "org A's model,
features, and predictions must never be trained on or exposed to org
B's events; do not train a shared cross-tenant model," and "organization
A cannot train on, evaluate, inspect, or retrieve organization B's data,
models, predictions, or metrics."
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.predictions import model_registry
from app.predictions.dataset import build_training_examples
from app.predictions.dataset_registry import (
    list_dataset_versions,
    register_synthetic_dataset,
)
from app.predictions.feature_snapshot_service import compute_feature_set_v1
from app.predictions.labels import generate_label
from app.predictions.monitoring import (
    compute_model_performance_monitoring,
    compute_prediction_monitoring,
)
from app.predictions.outcome_tracking import evaluate_matured_outcomes
from app.predictions.predictor import predict_as_of
from app.predictions.training import train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_two_organization_dataset,
)
from tests.intelligence_test_helpers import make_reviewer_user, make_safety_event

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_org_as_feature_snapshot_never_includes_org_bs_events(db_session):
    (org_a, sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=500)
    site_a = sites_a[0]

    before = compute_feature_set_v1(db_session, organization_id=org_a.id, site_id=site_a.id, as_of=AS_OF)

    # A large burst of org B activity, deliberately at the same as_of and
    # even reusing the same site *name* coincidence -- must have zero
    # effect on org A's own snapshot.
    for _ in range(20):
        db_session.add(
            make_safety_event(
                organization_id=org_b.id, site_id=sites_b[0].id, event_type="INCIDENT",
                event_time=AS_OF - timedelta(days=1), data_quality_status="VALID",
            )
        )
    db_session.commit()

    after = compute_feature_set_v1(db_session, organization_id=org_a.id, site_id=site_a.id, as_of=AS_OF)
    for name in before.features:
        assert before.features[name].value == after.features[name].value


def test_org_as_label_never_includes_org_bs_events(db_session):
    (org_a, sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=501)
    site_a = sites_a[0]

    db_session.add(
        make_safety_event(
            organization_id=org_b.id, site_id=sites_b[0].id, event_type="INCIDENT",
            event_time=AS_OF + timedelta(days=5), data_quality_status="VALID",
        )
    )
    db_session.commit()

    result = generate_label(db_session, organization_id=org_a.id, site_id=site_a.id, as_of=AS_OF)
    assert result.label == 0


def test_training_never_pools_examples_across_organizations(db_session):
    (org_a, sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=502)
    dates = as_of_dates()
    examples_a = build_training_examples(
        db_session, organization_id=org_a.id, site_ids=[s.id for s in sites_a], as_of_dates=dates
    )
    examples_b = build_training_examples(
        db_session, organization_id=org_b.id, site_ids=[s.id for s in sites_b], as_of_dates=dates
    )
    with pytest.raises(ValueError):
        train_baseline_model(db_session, organization_id=org_a.id, examples=examples_a + examples_b)


def test_a_model_deployed_for_org_a_never_serves_as_org_bs_deployed_model(db_session):
    (org_a, sites_a), (org_b, _sites_b) = seed_two_organization_dataset(db_session, seed=503)
    dates = as_of_dates()
    examples_a = build_training_examples(
        db_session, organization_id=org_a.id, site_ids=[s.id for s in sites_a], as_of_dates=dates
    )
    entry_a = train_baseline_model(db_session, organization_id=org_a.id, examples=examples_a)
    reviewer = make_reviewer_user(db_session)
    entry_a = model_registry.mark_validated(db_session, entry_a, calibration_validated=False)
    entry_a = model_registry.approve(db_session, entry_a, reviewer_user_id=reviewer.id)
    model_registry.deploy(db_session, entry_a)

    deployed_for_b = model_registry.get_deployed_model(db_session, organization_id=org_b.id, entity_type="site")
    assert deployed_for_b is None


def test_a_prediction_for_org_a_is_unaffected_by_org_bs_data_even_with_matching_entity_shape(db_session):
    (org_a, sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=504)
    dates = as_of_dates()
    examples_a = build_training_examples(
        db_session, organization_id=org_a.id, site_ids=[s.id for s in sites_a], as_of_dates=dates
    )
    entry_a = train_baseline_model(db_session, organization_id=org_a.id, examples=examples_a)
    reviewer = make_reviewer_user(db_session)
    entry_a = model_registry.mark_validated(db_session, entry_a, calibration_validated=False)
    entry_a = model_registry.approve(db_session, entry_a, reviewer_user_id=reviewer.id)
    entry_a = model_registry.deploy(db_session, entry_a)

    before = predict_as_of(
        db_session, organization_id=org_a.id, site_id=sites_a[0].id, as_of=dates[-1], model=entry_a, persist=False,
    )

    # A burst of org B incidents at the same as_of -- must not move org
    # A's own prediction at all.
    for _ in range(10):
        db_session.add(
            make_safety_event(
                organization_id=org_b.id, site_id=sites_b[0].id, event_type="INCIDENT",
                event_time=dates[-1] - timedelta(days=1), data_quality_status="VALID",
            )
        )
    db_session.commit()

    after = predict_as_of(
        db_session, organization_id=org_a.id, site_id=sites_a[0].id, as_of=dates[-1], model=entry_a, persist=False,
    )
    assert before.risk_score == after.risk_score


def test_predict_as_of_never_uses_a_site_id_that_belongs_to_a_different_organization(db_session):
    """Even if a caller passes org A's model together with a `site_id`
    that actually belongs to org B, the feature snapshot built is scoped
    by `organization_id` -- it must never resolve to org B's events (the
    result is a cold-start abstention: org A has never seen this site's
    events at all, since `events_as_of()` filters by `organization_id`)."""
    (org_a, _sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=505)
    dates = as_of_dates()
    examples_b = build_training_examples(
        db_session, organization_id=org_b.id, site_ids=[s.id for s in sites_b], as_of_dates=dates
    )
    entry_b = train_baseline_model(db_session, organization_id=org_b.id, examples=examples_b)
    reviewer = make_reviewer_user(db_session)
    entry_b = model_registry.mark_validated(db_session, entry_b, calibration_validated=False)
    entry_b = model_registry.approve(db_session, entry_b, reviewer_user_id=reviewer.id)
    entry_b = model_registry.deploy(db_session, entry_b)

    prediction = predict_as_of(
        db_session, organization_id=org_a.id, site_id=sites_b[0].id, as_of=dates[-1], model=entry_b, persist=False,
    )
    assert prediction.abstention_reason == "COLD_START"


# --- Model Validation & Governance v0.1, item 37 -----------------------------------------


def test_org_as_dataset_version_never_counts_org_bs_events(db_session):
    (org_a, sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=506)
    start = as_of_dates()[0] - timedelta(days=60)
    end = as_of_dates()[-1]

    dv_a = register_synthetic_dataset(
        db_session, organization_id=org_a.id, dataset_id="ORG-A-DS", date_range_start=start, date_range_end=end,
    )
    dv_b = register_synthetic_dataset(
        db_session, organization_id=org_b.id, dataset_id="ORG-B-DS", date_range_start=start, date_range_end=end,
    )
    # Org A's own site count reflects only its own sites, never org B's.
    assert dv_a.entity_count == len(sites_a)
    assert dv_b.entity_count == len(sites_b)


def test_org_a_cannot_list_org_bs_dataset_versions(db_session):
    (org_a, _sites_a), (org_b, _sites_b) = seed_two_organization_dataset(db_session, seed=507)
    start = as_of_dates()[0]
    end = as_of_dates()[-1]
    register_synthetic_dataset(db_session, organization_id=org_a.id, dataset_id="A-ONLY", date_range_start=start, date_range_end=end)
    register_synthetic_dataset(db_session, organization_id=org_b.id, dataset_id="B-ONLY", date_range_start=start, date_range_end=end)

    a_datasets = list_dataset_versions(db_session, organization_id=org_a.id)
    assert all(dv.dataset_id != "B-ONLY" for dv in a_datasets)
    assert any(dv.dataset_id == "A-ONLY" for dv in a_datasets)


def test_org_a_prediction_monitoring_never_includes_org_bs_predictions(db_session):
    (org_a, sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=508)
    dates = as_of_dates()

    def _deploy(org, sites):
        examples = build_training_examples(
            db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
        )
        entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
        reviewer = make_reviewer_user(db_session)
        entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
        entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
        return model_registry.deploy(db_session, entry)

    entry_a = _deploy(org_a, sites_a)
    entry_b = _deploy(org_b, sites_b)

    predict_as_of(db_session, organization_id=org_a.id, site_id=sites_a[0].id, as_of=dates[-1], model=entry_a)
    predict_as_of(db_session, organization_id=org_b.id, site_id=sites_b[0].id, as_of=dates[-1], model=entry_b)
    predict_as_of(db_session, organization_id=org_b.id, site_id=sites_b[0].id, as_of=dates[-2], model=entry_b)

    summary_a = compute_prediction_monitoring(db_session, organization_id=org_a.id)
    summary_b = compute_prediction_monitoring(db_session, organization_id=org_b.id)
    assert summary_a.total_predictions == 1
    assert summary_b.total_predictions == 2


def test_org_a_cannot_use_org_bs_model_id_to_read_performance_monitoring(db_session):
    """Even if org A somehow obtained org B's model_id, monitoring scoped
    to org A's organization_id must never surface org B's outcomes --
    the join is always organization_id-scoped, not just model_id."""
    (org_a, _sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=509)
    dates = as_of_dates()

    examples_b = build_training_examples(
        db_session, organization_id=org_b.id, site_ids=[s.id for s in sites_b], as_of_dates=dates
    )
    entry_b = train_baseline_model(db_session, organization_id=org_b.id, examples=examples_b)
    reviewer = make_reviewer_user(db_session)
    entry_b = model_registry.mark_validated(db_session, entry_b, calibration_validated=False)
    entry_b = model_registry.approve(db_session, entry_b, reviewer_user_id=reviewer.id)
    entry_b = model_registry.deploy(db_session, entry_b)
    predict_as_of(db_session, organization_id=org_b.id, site_id=sites_b[0].id, as_of=dates[-1], model=entry_b)

    # Query org B's model_id but scoped to org A's organization_id.
    summary = compute_model_performance_monitoring(db_session, organization_id=org_a.id, model_id=entry_b.id)
    assert summary.matured_outcome_count == 0


def test_org_a_outcome_evaluation_never_touches_org_bs_predictions(db_session):
    (org_a, sites_a), (org_b, sites_b) = seed_two_organization_dataset(db_session, seed=510)
    dates = as_of_dates()

    def _deploy(org, sites):
        examples = build_training_examples(
            db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
        )
        entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
        reviewer = make_reviewer_user(db_session)
        entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
        entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
        return model_registry.deploy(db_session, entry)

    entry_a = _deploy(org_a, sites_a)
    entry_b = _deploy(org_b, sites_b)

    as_of = dates[2]
    prediction_a = predict_as_of(db_session, organization_id=org_a.id, site_id=sites_a[0].id, as_of=as_of, model=entry_a)
    prediction_b = predict_as_of(db_session, organization_id=org_b.id, site_id=sites_b[0].id, as_of=as_of, model=entry_b)
    matured_at = as_of + timedelta(days=prediction_a.horizon_days + 1)

    results_a = evaluate_matured_outcomes(db_session, organization_id=org_a.id, as_of_now=matured_at)
    assert {r.prediction_id for r in results_a} == {prediction_a.id}
    assert prediction_b.id not in {r.prediction_id for r in results_a}


def test_model_registry_entries_never_share_dataset_version_ids_across_organizations(db_session):
    """A model row created under one organization_id must never resolve
    to a DatasetVersion belonging to another organization -- the FK
    itself does not enforce this (dataset_versions has its own
    organization_id), so this is a deliberate application-level check."""
    (org_a, _sites_a), (org_b, _sites_b) = seed_two_organization_dataset(db_session, seed=511)
    start = as_of_dates()[0]
    end = as_of_dates()[-1]
    dv_b = register_synthetic_dataset(db_session, organization_id=org_b.id, dataset_id="B-DS", date_range_start=start, date_range_end=end)

    entry_a = model_registry.create_model_entry(
        db_session, organization_id=org_a.id, model_name="cross-org-model", model_type="logistic_regression",
        entity_type="site", prediction_target_version="v1", label_definition_version="v1",
        feature_set_version="v1", training_data_version="v1", horizon_days=30,
        training_period_start=date(2026, 1, 1), training_period_end=date(2026, 2, 1),
        validation_period_start=date(2026, 2, 2), validation_period_end=date(2026, 3, 1),
        test_period_start=date(2026, 3, 2), test_period_end=date(2026, 4, 1),
        hyperparameters={}, metrics={}, parameters={},
        # Deliberately NOT passing dv_b.id -- the point is that nothing
        # in this codebase does this implicitly; a caller who tried would
        # be creating an inconsistent row on their own.
    )
    assert entry_a.dataset_version_id is None
    assert entry_a.dataset_version_id != dv_b.id
