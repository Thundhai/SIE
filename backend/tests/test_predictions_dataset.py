"""Training-example construction — milestone items 6-7. DB-backed
(SQLite) tests over `build_training_examples()`."""

from datetime import datetime, timedelta, timezone

from app.predictions.dataset import build_training_examples
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_one_example_is_built_per_site_and_as_of_pair(db_session):
    org = make_org(db_session)
    site_1 = make_site(db_session, org.id, name="Site 1")
    site_2 = make_site(db_session, org.id, name="Site 2")
    as_of_dates = [AS_OF, AS_OF - timedelta(days=30)]

    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[site_1.id, site_2.id], as_of_dates=as_of_dates
    )
    assert len(examples) == 4
    pairs = {(e.entity_id, e.as_of) for e in examples}
    assert len(pairs) == 4


def test_examples_carry_their_organization_and_entity_type(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    examples = build_training_examples(db_session, organization_id=org.id, site_ids=[site.id], as_of_dates=[AS_OF])
    assert examples[0].organization_id == org.id
    assert examples[0].entity_type == "site"
    assert examples[0].entity_id == site.id


def test_examples_reuse_persisted_snapshots_across_calls(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    first = build_training_examples(db_session, organization_id=org.id, site_ids=[site.id], as_of_dates=[AS_OF])
    second = build_training_examples(db_session, organization_id=org.id, site_ids=[site.id], as_of_dates=[AS_OF])
    assert first[0].feature_snapshot_id == second[0].feature_snapshot_id


def test_labels_reflect_actual_future_incidents_per_example(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    db_session.add(
        make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF + timedelta(days=5), data_quality_status="VALID",
        )
    )
    db_session.commit()
    examples = build_training_examples(db_session, organization_id=org.id, site_ids=[site.id], as_of_dates=[AS_OF])
    assert examples[0].label == 1
    assert examples[0].supporting_event_ids
