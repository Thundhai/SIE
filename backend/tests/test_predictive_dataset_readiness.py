"""Predictive dataset readiness — Real-World Data Validation &
Intelligence Calibration v0.1, item 10.

**Goal (per the milestone's own framing): "Can we reliably construct a
defensible dataset for real model validation?"** Never "is the model
good" -- nothing here trains, tunes, or evaluates a model, and nothing
here claims predictive accuracy.

`tests/evaluation/calibration_harness.py::_validate_predictive_readiness()`
already builds an aggregate `PredictiveReadinessResult`, asserted on by
`tests/evaluation/test_calibration_evaluation.py`. This file is
additive, not a repeat: dedicated, more granular assertions against
`app/predictions/dataset.py::build_training_examples()`, using the same
realistic domain builders as `tests/fixtures/enterprise_scenarios.py`
(not the pre-existing narrow synthetic fixtures), through the real,
unmodified `EnterpriseIngestionService`. Feature/label separation itself
is `tests/test_feature_label_separation.py`'s own regression test and is
not re-proven here.

Requires real PostgreSQL (`@requires_postgres`, `pg_session`) for the
same reason `tests/evaluation/test_calibration_evaluation.py` does: some
assertions below compare raw Python datetimes against values read back
from the database, which SQLite's lack of a native timezone-aware
datetime type makes unreliable. See that module's own docstring.
"""

from __future__ import annotations

import dataclasses
import random
import uuid
from datetime import timedelta

from app.intelligence.enterprise_ingestion import enterprise_ingestion_service
from app.intelligence.temporal import utcnow
from app.models.organization import Organization
from app.models.site import Site
from app.predictions.dataset import build_training_examples
from tests.evaluation.calibration_harness import (
    _backdate_ingestion_time_near_event_time,
)
from tests.fixtures.enterprise_scenarios import incident, near_miss
from tests.postgres_support import requires_postgres


def _make_org_and_site(db, name: str) -> tuple[uuid.UUID, uuid.UUID]:
    org = Organization(name=name)
    db.add(org)
    db.commit()
    site = Site(organization_id=org.id, name=f"{name} Site")
    db.add(site)
    db.commit()
    return org.id, site.id


def _ingest_near_miss_escalation(db, *, organization_id, site_id, base_time, seed=9001):
    """A realistic escalation, the same shape as
    tests/fixtures/enterprise_scenarios.py's own scenario B (near misses
    sharply up in the current 30-day window against a quiet 90-day
    baseline) but with an explicit `site_id` -- scenario B's own builder
    omits one, since it is a whole-organization scenario, not a
    per-site one."""
    rng = random.Random(seed)
    payloads = [
        near_miss(rng, base_time, days_ago=period * 30 + 3, subtype="DROPPED_OBJECT", site_id=site_id)
        for period in range(1, 4)
    ]
    payloads += [
        near_miss(rng, base_time, days_ago=i, subtype="VEHICLE_NEAR_MISS", site_id=site_id) for i in range(10)
    ]
    enterprise_ingestion_service.ingest_batch(db, organization_id=organization_id, source_id=None, payloads=payloads)
    _backdate_ingestion_time_near_event_time(db, organization_id)


# --- Correct site/as-of construction ------------------------------------------------------


@requires_postgres
def test_examples_are_keyed_correctly_per_site_and_as_of(pg_session):
    org_id, site_a = _make_org_and_site(pg_session, "Readiness - Site Keying A")
    site_b = Site(organization_id=org_id, name="Readiness - Site Keying B")
    pg_session.add(site_b)
    pg_session.commit()

    _ingest_near_miss_escalation(pg_session, organization_id=org_id, site_id=site_a, base_time=utcnow(), seed=1)
    _ingest_near_miss_escalation(pg_session, organization_id=org_id, site_id=site_b.id, base_time=utcnow(), seed=2)

    as_of = utcnow()
    as_of_dates = [as_of - timedelta(days=d) for d in (14, 7, 0)]
    examples = build_training_examples(
        pg_session, organization_id=org_id, site_ids=[site_a, site_b.id], as_of_dates=as_of_dates, persist_snapshots=False
    )

    assert len(examples) == 6  # 2 sites x 3 as_of dates, no fewer, no duplicates
    keys = {(e.entity_id, e.as_of) for e in examples}
    assert len(keys) == 6  # every (site, as_of) pair is distinct
    for e in examples:
        assert e.entity_id in (site_a, site_b.id)
        assert e.as_of in as_of_dates
        assert e.organization_id == org_id


# --- Feature availability + no future leakage, on realistic escalation data ---------------


@requires_postgres
def test_feature_vector_reflects_the_escalation_only_after_it_actually_happens(pg_session):
    """The concrete, realistic-data version of item 10's "no future
    leakage" check: a feature snapshot built *before* the escalation
    began must show the quiet baseline, and one built *after* must show
    the real, elevated count -- proven with a specific feature value
    from real ingested data, not merely a boolean over an aggregate."""
    org_id, site_id = _make_org_and_site(pg_session, "Readiness - Escalation Visibility")
    base_time = utcnow()
    _ingest_near_miss_escalation(pg_session, organization_id=org_id, site_id=site_id, base_time=base_time)

    before_escalation = base_time - timedelta(days=45)  # squarely inside the quiet baseline
    after_escalation = base_time  # squarely inside the escalated current window

    examples = build_training_examples(
        pg_session, organization_id=org_id, site_ids=[site_id],
        as_of_dates=[before_escalation, after_escalation], persist_snapshots=False,
    )
    before_example = next(e for e in examples if e.as_of == before_escalation)
    after_example = next(e for e in examples if e.as_of == after_escalation)

    before_count = before_example.feature_vector["near_miss_count_30d"]
    after_count = after_example.feature_vector["near_miss_count_30d"]
    # Feature availability: real ingested activity produces a real
    # (non-None) computed value, never a fabricated placeholder.
    assert after_count is not None
    # No future leakage: the "before" snapshot must not see any part of
    # the escalation that, from its own point in time, has not happened yet.
    assert (before_count or 0) < after_count


# --- Label construction ---------------------------------------------------------------------


@requires_postgres
def test_label_reflects_only_incidents_strictly_after_as_of_within_the_horizon(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Readiness - Label Construction")
    as_of = utcnow()

    # One incident just before as_of (must NOT contribute to the label)
    # and one just after (must).
    rng = random.Random(4242)
    before_incident = incident(rng, as_of, days_ago=1, subtype="FIRST_AID_CASE", site_id=site_id)
    result = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org_id, source_id=None, payloads=[before_incident]
    )
    before_event_id = result.records[0].canonical_event_id

    after_time = as_of + timedelta(days=3)
    after_incident = incident(rng, after_time, days_ago=0, subtype="LOST_TIME_INCIDENT", site_id=site_id)
    result_after = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org_id, source_id=None, payloads=[after_incident]
    )
    after_event_id = result_after.records[0].canonical_event_id

    examples = build_training_examples(
        pg_session, organization_id=org_id, site_ids=[site_id], as_of_dates=[as_of], horizon_days=30,
        persist_snapshots=False,
    )
    example = examples[0]
    assert example.label == 1
    assert after_event_id in example.supporting_event_ids
    assert before_event_id not in example.supporting_event_ids


# --- Missing-data handling ------------------------------------------------------------------


@requires_postgres
def test_a_site_with_no_events_still_produces_a_defensible_example(pg_session):
    org_id, empty_site = _make_org_and_site(pg_session, "Readiness - Missing Data")
    examples = build_training_examples(
        pg_session, organization_id=org_id, site_ids=[empty_site], as_of_dates=[utcnow()], persist_snapshots=False
    )
    assert len(examples) == 1
    example = examples[0]
    assert example.data_quality is not None  # a real quality classification, not a crash
    assert example.label in (0, 1)
    assert isinstance(example.feature_vector, dict) and example.feature_vector  # present, even if values are None


# --- Tenant isolation -----------------------------------------------------------------------


@requires_postgres
def test_predictive_examples_never_reflect_another_organizations_data(pg_session):
    org_a_id, site_a = _make_org_and_site(pg_session, "Readiness - Tenant A")
    org_b_id, site_b = _make_org_and_site(pg_session, "Readiness - Tenant B")
    base_time = utcnow()
    _ingest_near_miss_escalation(pg_session, organization_id=org_a_id, site_id=site_a, base_time=base_time, seed=11)
    # Org B gets no escalation at all -- only a single quiet baseline event.
    rng = random.Random(12)
    quiet_payload = near_miss(rng, base_time, days_ago=3, subtype="DROPPED_OBJECT", site_id=site_b)
    enterprise_ingestion_service.ingest_batch(pg_session, organization_id=org_b_id, source_id=None, payloads=[quiet_payload])
    _backdate_ingestion_time_near_event_time(pg_session, org_b_id)

    examples_a = build_training_examples(
        pg_session, organization_id=org_a_id, site_ids=[site_a], as_of_dates=[base_time], persist_snapshots=False
    )
    examples_b = build_training_examples(
        pg_session, organization_id=org_b_id, site_ids=[site_b], as_of_dates=[base_time], persist_snapshots=False
    )
    assert all(e.organization_id == org_a_id for e in examples_a)
    assert all(e.organization_id == org_b_id for e in examples_b)
    # Org A's real escalation (10 recent near misses) must never leak into
    # org B's feature vector, which only has one quiet, unrelated event.
    assert examples_a[0].feature_vector["near_miss_count_30d"] != examples_b[0].feature_vector["near_miss_count_30d"]
    assert (examples_b[0].feature_vector["near_miss_count_30d"] or 0) <= 1


# --- Reproducibility -------------------------------------------------------------------------


@requires_postgres
def test_building_the_same_examples_twice_is_fully_reproducible(pg_session):
    org_id, site_id = _make_org_and_site(pg_session, "Readiness - Reproducibility")
    base_time = utcnow()
    _ingest_near_miss_escalation(pg_session, organization_id=org_id, site_id=site_id, base_time=base_time)
    as_of_dates = [base_time - timedelta(days=d) for d in (20, 10, 0)]

    examples_1 = build_training_examples(
        pg_session, organization_id=org_id, site_ids=[site_id], as_of_dates=as_of_dates, persist_snapshots=False
    )
    examples_2 = build_training_examples(
        pg_session, organization_id=org_id, site_ids=[site_id], as_of_dates=as_of_dates, persist_snapshots=False
    )

    # Full example equality (feature_set_version, data_quality, label,
    # supporting_event_ids included), not merely the feature vectors --
    # a stricter check than the calibration harness's own aggregate one.
    assert [dataclasses.asdict(e) for e in examples_1] == [dataclasses.asdict(e) for e in examples_2]
