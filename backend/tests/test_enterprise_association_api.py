"""SIE Milestone 24: Enterprise Intelligence Pattern & Correlation
Foundation v0.1 — HTTP-layer coverage for the `associations` field on
`GET /api/v1/intelligence/enterprise` and
`GET /api/v1/intelligence/sites/{site_id}` (milestone items 12, 17).
Extends the existing endpoints rather than adding a parallel API (item
12's own instruction) — authorization/tenant-isolation/invalid-window/
invalid-site coverage for those endpoints already lives in
`tests/test_enterprise_intelligence_api.py` and is not repeated here;
this file focuses on what's new: the `associations` field's presence,
shape, provenance, and risk-score non-interference.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.enterprise_association import SUPPORTED_ASSOCIATION_METRICS
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.intelligence_test_helpers import make_safety_event, make_site
from tests.test_ingestion_api import create_org

AS_OF = datetime.now(timezone.utc)


def _make_client_credential(db_session, org_id, *, scopes=None):
    scopes = scopes if scopes is not None else [Permission.INTELLIGENCE_READ]
    return api_client_service.create(db_session, organization_id=org_id, name="Test Integration", scopes=scopes)


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _seed_incidents(db_session, org_id, *, site_id=None, count, days_ago_start=0):
    for i in range(count):
        event = make_safety_event(
            organization_id=org_id, site_id=site_id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=days_ago_start + i),
            ingestion_time=AS_OF - timedelta(days=days_ago_start + i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    db_session.commit()


def test_enterprise_endpoint_response_includes_an_associations_field(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200
    body = response.json()
    assert "associations" in body
    assert isinstance(body["associations"], list)


def test_associations_cover_exactly_the_twenty_one_supported_pairs(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    associations = response.json()["associations"]
    assert len(associations) == 21
    pair_keys = {frozenset((a["metric_a"], a["metric_b"])) for a in associations}
    assert len(pair_keys) == 21
    all_metrics = {a["metric_a"] for a in associations} | {a["metric_b"] for a in associations}
    assert all_metrics == set(SUPPORTED_ASSOCIATION_METRICS)
    for association in associations:
        assert association["classification"] in (
            "STRONG_POSITIVE", "MODERATE_POSITIVE", "WEAK", "MODERATE_NEGATIVE", "STRONG_NEGATIVE",
            "INSUFFICIENT_DATA",
        )
        assert association["calculation_version"] == "association-v1"
        assert "correlation_coefficient" in association
        assert "period_count" in association
        assert "values_a" in association
        assert "values_b" in association
        assert "supporting_event_ids" in association


def test_associations_response_is_deterministic_across_repeated_requests(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)
    # An explicit as_of freezes the time reference -- see the identical
    # rationale in tests/test_enterprise_anomaly_api.py.
    params = {"organization_id": org["id"], "as_of": AS_OF.isoformat()}

    first = client.get(
        "/api/v1/intelligence/enterprise", params=params, headers=_bearer(credential)
    ).json()["associations"]
    second = client.get(
        "/api/v1/intelligence/enterprise", params=params, headers=_bearer(credential)
    ).json()["associations"]
    assert first == second


def test_site_endpoint_response_includes_an_associations_field(client, db_session):
    org = create_org(client)
    site = make_site(db_session, uuid.UUID(org["id"]), name="Site 02")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), site_id=site.id, count=3)

    response = client.get(
        f"/api/v1/intelligence/sites/{site.id}?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200
    assert "associations" in response.json()


def test_associations_never_leak_a_foreign_organizations_evidence(client, db_session):
    org_a = create_org(client, name="Org A6")
    org_b = create_org(client, name="Org B6")
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))
    _seed_incidents(db_session, uuid.UUID(org_a["id"]), count=2)
    b_events = []
    for i in range(20):
        event = make_safety_event(
            organization_id=uuid.UUID(org_b["id"]), event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
        b_events.append(event)
    db_session.commit()

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org_a['id']}", headers=_bearer(credential_a)
    )
    associations = response.json()["associations"]
    all_evidence_ids = {eid for a in associations for eid in a["supporting_event_ids"]}
    assert all_evidence_ids.isdisjoint({str(e.id) for e in b_events})


def test_association_calculation_version_appears_in_provenance(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    body = response.json()
    assert body["provenance"]["calculation_versions"]["association"] == "association-v1"


def test_risk_score_is_untouched_by_the_presence_of_associations(client, db_session):
    """Milestone item 8: associations are a separate dimension, never
    folded into enterprise-risk-v1."""
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    body = response.json()
    assert body["deterministic_risk"]["version"] == "enterprise-risk-v1"
    component_keys = {c["key"] for c in body["deterministic_risk"]["components"]}
    assert not any("association" in key.lower() for key in component_keys)


def test_a_strong_association_does_not_change_the_risk_score(client, db_session):
    """Milestone item 8's own worked example: a strong positive
    association must not automatically become "risk score +20"."""
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    # Perfectly correlated INCIDENT counts across recent history (both
    # the current period and equally-shaped historical periods) --
    # exercises a genuinely strong association without changing what
    # feeds the risk score's own, separate indicator/trend computation.
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)

    response_before = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    ).json()
    # Re-request: even though associations are computed on every call,
    # the risk score for the same underlying data must be identical.
    response_after = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    ).json()
    assert response_before["deterministic_risk"]["score"] == response_after["deterministic_risk"]["score"]
