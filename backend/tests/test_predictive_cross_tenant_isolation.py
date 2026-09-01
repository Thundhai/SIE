"""Mandatory cross-tenant isolation regression test — milestone item 43,
explicitly required by the spec: "org A's model, features, and
predictions must never be trained on or exposed to org B's events; do
not train a shared cross-tenant model."
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.predictions import model_registry
from app.predictions.dataset import build_training_examples
from app.predictions.feature_snapshot_service import compute_feature_set_v1
from app.predictions.labels import generate_label
from app.predictions.predictor import predict_as_of
from app.predictions.training import train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_two_organization_dataset,
)
from tests.intelligence_test_helpers import make_safety_event

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
    entry_a = model_registry.mark_validated(db_session, entry_a, calibration_validated=False)
    entry_a = model_registry.approve(db_session, entry_a)
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
    entry_a = model_registry.mark_validated(db_session, entry_a, calibration_validated=False)
    entry_a = model_registry.approve(db_session, entry_a)
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
    entry_b = model_registry.mark_validated(db_session, entry_b, calibration_validated=False)
    entry_b = model_registry.approve(db_session, entry_b)
    entry_b = model_registry.deploy(db_session, entry_b)

    prediction = predict_as_of(
        db_session, organization_id=org_a.id, site_id=sites_b[0].id, as_of=dates[-1], model=entry_b, persist=False,
    )
    assert prediction.abstention_reason == "COLD_START"
