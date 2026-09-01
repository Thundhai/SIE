"""Mandatory temporal-leakage regression tests — milestone item 42,
explicitly required by the spec. Each of the four cases below is a
distinct way future information could leak into a feature, a label, or a
served prediction; each is a real regression test, not a restatement of
`app/intelligence/temporal.py`'s own existing coverage (this package
composes that module, and needs its own leakage tests at the predictive
layer: labels, dataset construction, and served predictions).
"""

from datetime import datetime, timedelta, timezone

from app.predictions import model_registry
from app.predictions.dataset import build_training_examples
from app.predictions.feature_snapshot_service import compute_feature_set_v1
from app.predictions.labels import generate_label
from app.predictions.predictor import predict_as_of
from app.predictions.spec import HORIZON_DAYS
from app.predictions.training import train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_case_1_a_future_incident_does_not_change_a_feature_snapshot_built_at_an_earlier_as_of(db_session):
    """The milestone's own worked example: 'if predicting risk for
    2026-06-01, a feature must not include an incident that happened
    2026-06-15.'"""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=AS_OF - timedelta(days=5), ingestion_time=AS_OF - timedelta(days=5),
        )
    )
    db_session.commit()
    before = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)

    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF + timedelta(days=14), data_quality_status="VALID",
        )
    )
    db_session.commit()
    after = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)

    assert before.features["incident_count_30d"].value == after.features["incident_count_30d"].value == 0


def test_case_2_a_backdated_report_is_excluded_when_its_ingestion_time_is_after_as_of(db_session):
    """An event whose `event_time` is in the past relative to `as_of` but
    whose `ingestion_time` (when it was actually recorded/reported) is
    *after* `as_of` was not actually knowable at that historical moment
    -- it must not appear in the feature snapshot (see
    `app/intelligence/temporal.py::events_as_of()`'s own
    `strict_point_in_time` docstring)."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=AS_OF - timedelta(days=3),  # happened before as_of...
            ingestion_time=AS_OF + timedelta(days=10),  # ...but only reported after as_of
        )
    )
    db_session.commit()
    feature_set = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert feature_set.features["near_miss_count_30d"].value == 0


def test_case_3_a_label_is_never_affected_by_events_at_or_before_as_of(db_session):
    """`generate_label()`'s horizon is strictly `event_time > as_of` --
    an incident exactly at (or before) as_of must never count toward the
    future-looking label."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF, data_quality_status="VALID",
        )
    )
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=1), data_quality_status="VALID",
        )
    )
    db_session.commit()
    result = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)
    assert result.label == 0


def test_case_4_a_backtested_prediction_is_unaffected_by_events_added_after_its_as_of(db_session):
    """`predict_as_of()` is the internal backtesting mechanism (milestone
    item 34) -- a historical prediction it produces must be bit-for-bit
    unaffected by events inserted into the database *after* that
    prediction's `as_of`, exactly as a real point-in-time backtest
    requires."""
    org, sites = seed_synthetic_organization(db_session, name="Leakage Org", site_names=["Site 1"], seed=321)
    dates = as_of_dates()

    training_examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    entry = train_baseline_model(db_session, organization_id=org.id, examples=training_examples)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    entry = model_registry.approve(db_session, entry)
    entry = model_registry.deploy(db_session, entry)

    backtest_as_of = dates[len(dates) // 2]
    before = predict_as_of(
        db_session, organization_id=org.id, site_id=sites[0].id, as_of=backtest_as_of, model=entry, persist=False,
    )

    # Delete the feature snapshot get_or_build_feature_snapshot() just
    # cached for (site, backtest_as_of) -- otherwise the second call
    # below would just replay the cached snapshot, which would prove
    # idempotency, not that a *fresh* computation still excludes future
    # events. Forcing recomputation makes this a genuine leakage test.
    from app.models.feature_snapshot import FeatureSnapshot

    db_session.query(FeatureSnapshot).filter(
        FeatureSnapshot.organization_id == org.id, FeatureSnapshot.entity_id == sites[0].id
    ).delete()
    db_session.commit()

    # Insert a dramatic future incident, well after backtest_as_of.
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=sites[0].id, event_type="INCIDENT",
            event_time=backtest_as_of + timedelta(days=HORIZON_DAYS - 1), data_quality_status="VALID",
        )
    )
    db_session.commit()

    after = predict_as_of(
        db_session, organization_id=org.id, site_id=sites[0].id, as_of=backtest_as_of, model=entry, persist=False,
    )

    assert before.risk_score == after.risk_score
    assert before.risk_category == after.risk_category
