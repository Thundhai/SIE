"""SIE Milestone 23: Enterprise Intelligence Explainability & Anomaly
Foundation v0.1 — HTTP-layer coverage for the `anomalies` field on
`GET /api/v1/intelligence/enterprise` and
`GET /api/v1/intelligence/sites/{site_id}` (milestone items 13, 15).
Extends the existing endpoints rather than adding a parallel API (item
13's own instruction) — authorization/tenant-isolation/invalid-window/
invalid-site coverage for those endpoints already lives in
`tests/test_enterprise_intelligence_api.py` and is not repeated here;
this file focuses on what's new: the `anomalies` field's presence,
shape, and determinism.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.enterprise_anomaly import SUPPORTED_ANOMALY_METRICS
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


def test_enterprise_endpoint_response_includes_an_anomalies_field(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200
    body = response.json()
    assert "anomalies" in body
    assert isinstance(body["anomalies"], list)


def test_anomalies_cover_exactly_the_supported_metrics_deterministic_structure(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    anomalies = response.json()["anomalies"]
    assert {a["metric"] for a in anomalies} == set(SUPPORTED_ANOMALY_METRICS)
    for anomaly in anomalies:
        assert anomaly["status"] in ("NORMAL", "ANOMALOUS", "INSUFFICIENT_DATA")
        assert anomaly["direction"] in ("ABOVE_BASELINE", "BELOW_BASELINE", "NONE")
        assert anomaly["calculation_version"] == "anomaly-v1"
        assert "current_value" in anomaly
        assert "baseline_mean" in anomaly
        assert "baseline_stdev" in anomaly
        assert "z_score" in anomaly
        assert "supporting_event_count" in anomaly
        assert "supporting_event_ids" in anomaly


def test_anomalies_response_is_deterministic_across_repeated_requests(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)
    # An explicit as_of freezes the time reference -- omitting it would
    # resolve to a fresh utcnow() on each call, trivially varying
    # current_period_start/end by microseconds (a test-harness artifact,
    # not a real determinism defect -- the same would be true of every
    # other timestamped field in this response).
    params = {"organization_id": org["id"], "as_of": AS_OF.isoformat()}

    first = client.get(
        "/api/v1/intelligence/enterprise", params=params, headers=_bearer(credential)
    ).json()["anomalies"]
    second = client.get(
        "/api/v1/intelligence/enterprise", params=params, headers=_bearer(credential)
    ).json()["anomalies"]
    assert first == second


def test_site_endpoint_response_includes_an_anomalies_field(client, db_session):
    org = create_org(client)
    site = make_site(db_session, uuid.UUID(org["id"]), name="Site 01")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), site_id=site.id, count=3)

    response = client.get(
        f"/api/v1/intelligence/sites/{site.id}?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 200
    assert "anomalies" in response.json()


def test_anomalies_never_leak_a_foreign_organizations_evidence(client, db_session):
    org_a = create_org(client, name="Org A3")
    org_b = create_org(client, name="Org B3")
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
    anomalies = response.json()["anomalies"]
    all_evidence_ids = {eid for a in anomalies for eid in a["supporting_event_ids"]}
    assert all_evidence_ids.isdisjoint({str(e.id) for e in b_events})


def test_risk_score_is_untouched_by_the_presence_of_anomalies(client, db_session):
    """Milestone item 11: anomalies are a separate dimension, never
    folded into enterprise-risk-v1."""
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    _seed_incidents(db_session, uuid.UUID(org["id"]), count=3)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    body = response.json()
    assert body["deterministic_risk"]["version"] == "enterprise-risk-v1"
    # The risk score components list must never reference an anomaly.
    component_keys = {c["key"] for c in body["deterministic_risk"]["components"]}
    assert not any("anomaly" in key.lower() for key in component_keys)
