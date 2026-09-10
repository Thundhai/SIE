"""SIE Milestone 22: Enterprise Intelligence & Risk Analytics Foundation
v0.1, item 7 — `app/intelligence/concentration.py`. Pure-function tests
(no database).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.intelligence.concentration import compute_concentration
from tests.intelligence_test_helpers import make_safety_event

AS_OF = datetime(2026, 7, 1, tzinfo=timezone.utc)
ORG_ID = uuid.uuid4()
SITE_A = uuid.uuid4()
SITE_B = uuid.uuid4()


def _incident(*, site_id=None, event_subtype=None, severity=None):
    return make_safety_event(
        organization_id=ORG_ID, site_id=site_id, event_type="INCIDENT",
        event_subtype=event_subtype, severity=severity, event_time=AS_OF,
    )


def test_site_concentration_is_ranked_by_real_counts():
    events = (
        [_incident(site_id=SITE_A) for _ in range(7)]
        + [_incident(site_id=SITE_B) for _ in range(3)]
    )
    contributors = compute_concentration(events, scope="organization")
    site_contributors = [c for c in contributors if c.dimension == "site"]
    assert site_contributors[0].key == str(SITE_A)
    assert site_contributors[0].count == 7
    assert site_contributors[0].total == 10
    assert site_contributors[0].percentage == 0.7
    assert site_contributors[0].classification == "HIGH"
    assert site_contributors[1].key == str(SITE_B)
    assert site_contributors[1].percentage == 0.3
    assert site_contributors[1].classification == "MODERATE"


def test_site_dimension_is_never_computed_at_site_scope():
    events = [_incident(site_id=SITE_A) for _ in range(6)]
    contributors = compute_concentration(events, scope="site")
    assert not any(c.dimension == "site" for c in contributors)


def test_minimum_population_safeguard_omits_a_dimension_below_the_floor():
    # Only 2 incidents total -- below ENTERPRISE_CONCENTRATION_MIN_POPULATION (5).
    events = [_incident(site_id=SITE_A), _incident(site_id=SITE_B)]
    contributors = compute_concentration(events, scope="organization")
    assert not any(c.dimension == "site" for c in contributors)
    assert not any(c.dimension == "event_subtype" for c in contributors)


def test_event_subtype_concentration_ranks_incident_subtypes():
    events = (
        [_incident(site_id=SITE_A, event_subtype="VEHICLE_INCIDENT") for _ in range(4)]
        + [_incident(site_id=SITE_A, event_subtype="PROPERTY_DAMAGE")]
    )
    contributors = compute_concentration(events, scope="organization")
    subtype = [c for c in contributors if c.dimension == "event_subtype"]
    assert subtype[0].key == "VEHICLE_INCIDENT"
    assert subtype[0].count == 4
    assert subtype[0].percentage == 0.8


def test_severity_concentration_uses_the_same_pool_as_features():
    events = [_incident(site_id=SITE_A, severity="HIGH") for _ in range(3)] + [
        _incident(site_id=SITE_A, severity="LOW") for _ in range(2)
    ]
    # A near miss also counts toward the severity pool (matches features.py).
    near_miss = make_safety_event(
        organization_id=ORG_ID, site_id=SITE_A, event_type="NEAR_MISS", severity="HIGH", event_time=AS_OF
    )
    contributors = compute_concentration(events + [near_miss], scope="organization")
    severity = [c for c in contributors if c.dimension == "severity"]
    high = next(c for c in severity if c.key == "HIGH")
    assert high.count == 4
    assert high.total == 6


def test_event_type_concentration_spans_all_event_types():
    events = [_incident(site_id=SITE_A) for _ in range(4)] + [
        make_safety_event(organization_id=ORG_ID, site_id=SITE_A, event_type="OBSERVATION", event_time=AS_OF)
        for _ in range(1)
    ]
    contributors = compute_concentration(events, scope="organization")
    event_type = [c for c in contributors if c.dimension == "event_type"]
    assert {c.key for c in event_type} == {"INCIDENT", "OBSERVATION"}


def test_no_cross_tenant_contribution():
    other_org_id = uuid.uuid4()
    other_org_events = [
        make_safety_event(organization_id=other_org_id, site_id=SITE_A, event_type="INCIDENT", event_time=AS_OF)
        for _ in range(10)
    ]
    # compute_concentration is a pure function over whatever list it's
    # handed -- the real tenant-isolation guarantee lives in
    # events_as_of()'s organization_id filter (see
    # test_enterprise_intelligence_service.py's own tenant-isolation
    # coverage). This test documents that a concentration ranking
    # reflects exactly its input, never a second, implicit query.
    contributors = compute_concentration(other_org_events, scope="organization")
    assert all(c.key == str(SITE_A) for c in contributors if c.dimension == "site")
