"""Feature/label separation — milestone item 7, explicitly called
NON-NEGOTIABLE. `app/predictions/labels.py` and
`app/predictions/feature_snapshot_service.py` must never share
information: a feature snapshot built for `(site, as_of)` must be
identical regardless of what happens after `as_of` (the label window),
and a label must be identical regardless of what a feature computation
did before/at `as_of`.
"""

from datetime import datetime, timedelta, timezone

from app.predictions.dataset import build_training_example
from app.predictions.feature_snapshot_service import compute_feature_set_v1
from app.predictions.labels import generate_label
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_feature_vector_is_unchanged_by_adding_or_removing_future_label_window_events(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    # Some pre-as_of history so the snapshot isn't trivially all-missing.
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
            event_time=AS_OF - timedelta(days=10), ingestion_time=AS_OF - timedelta(days=10),
        )
    )
    db_session.commit()

    before = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)

    # Add several qualifying INCIDENTs squarely inside the label's future
    # horizon window -- these would flip generate_label()'s output to 1,
    # and must have zero effect on the already-computed feature set.
    for d in (1, 5, 20):
        db_session.add(
            make_safety_event(
                organization_id=org.id, site_id=site.id, event_type="INCIDENT",
                event_time=AS_OF + timedelta(days=d), data_quality_status="VALID",
            )
        )
    db_session.commit()

    after = compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)

    for name in before.features:
        assert before.features[name].value == after.features[name].value, (
            f"feature {name!r} changed after adding future label-window events -- temporal leakage"
        )


def test_label_is_unaffected_by_the_feature_computation_or_by_pre_as_of_history(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)

    label_without_history = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)

    # Adding a large amount of pre-as_of history (which feature
    # computation would use) must not affect the label at all.
    for d in range(0, 90, 5):
        db_session.add(
            make_safety_event(
                organization_id=org.id, site_id=site.id, event_type="INCIDENT",
                event_time=AS_OF - timedelta(days=d), data_quality_status="VALID",
            )
        )
    db_session.commit()
    # Also force a feature computation in between -- calling it must not
    # mutate any state generate_label() depends on.
    compute_feature_set_v1(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)

    label_with_history = generate_label(db_session, organization_id=org.id, site_id=site.id, as_of=AS_OF)

    assert label_without_history.label == label_with_history.label == 0


def test_training_example_never_leaks_label_information_into_its_feature_vector(db_session):
    """End-to-end via dataset.py: an example whose label is 1 (a future
    incident occurred) must have a feature_vector indistinguishable from
    one built at the same as_of with no future incident -- proves
    build_training_example() itself never threads label information into
    feature construction."""
    org = make_org(db_session)
    site_a = make_site(db_session, org.id, name="No future incident")
    site_b = make_site(db_session, org.id, name="Future incident")

    # Identical pre-as_of history at both sites.
    for site in (site_a, site_b):
        db_session.add(
            make_safety_event(
                organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
                event_time=AS_OF - timedelta(days=10), ingestion_time=AS_OF - timedelta(days=10),
            )
        )
    db_session.commit()

    # Only site_b gets a qualifying future incident.
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site_b.id, event_type="INCIDENT",
            event_time=AS_OF + timedelta(days=5), data_quality_status="VALID",
        )
    )
    db_session.commit()

    example_a = build_training_example(db_session, organization_id=org.id, site_id=site_a.id, as_of=AS_OF)
    example_b = build_training_example(db_session, organization_id=org.id, site_id=site_b.id, as_of=AS_OF)

    assert example_a.label == 0
    assert example_b.label == 1
    # Both feature vectors were built from identical pre-as_of history --
    # the label divergence must not appear in the feature vectors.
    assert example_a.feature_vector == example_b.feature_vector
