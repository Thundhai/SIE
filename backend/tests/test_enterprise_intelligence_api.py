"""Task 01D-F3: `GET /api/v1/intelligence/enterprise` -- the Public SIE
API route wired to the real Commercial Core Enterprise Intelligence
client. Mirrors `tests/test_intelligence_api.py`'s own Analytics
section (`_FakeAnalyticsClient`, `_make_client_credential`, `_bearer`)
structure and fakes exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.test_ingestion_api import create_org, make_user
from tests.test_intelligence_api import _bearer, _make_client_credential


class _FakeEnterpriseIntelligenceClient:
    """A `CommercialCoreClient` test double for
    `get_enterprise_intelligence()` -- mirrors `_FakeAnalyticsClient`'s
    identical shape in `tests/test_intelligence_api.py`."""

    def __init__(self, *, result=None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.calls: list[dict] = []

    def unavailable(self, capability: str):
        raise NotImplementedError

    def get_enterprise_intelligence(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


def _full_result(organization_id, **overrides):
    """A fully-populated `EnterpriseIntelligenceResultDTO`, one item per
    list field, so a single success test can assert every reshaping
    `_enterprise_intelligence_response()` performs in one pass."""
    from sie_contract import (
        ActionsContextDTO,
        AsOfWindow,
        ConcentrationClassification,
        ConcentrationContributorDTO,
        EnterpriseAnomalyDirection,
        EnterpriseAnomalyDTO,
        EnterpriseAnomalyStatus,
        EnterpriseAssociationClassification,
        EnterpriseAssociationDTO,
        EnterpriseDataSufficiency,
        EnterpriseIndicatorCategory,
        EnterpriseIndicatorDTO,
        EnterpriseIntelligenceProvenanceDTO,
        EnterpriseIntelligenceResultDTO,
        EnterpriseRiskClassification,
        EnterpriseTrendClassification,
        EnterpriseTrendDTO,
        EvidenceReference,
        EvidenceType,
        ExplanationItemDTO,
        RecurrenceClassification,
        RecurrencePatternDTO,
        RiskScoreComponentDTO,
        RiskScoreDTO,
    )

    now = datetime.now(timezone.utc)
    as_of = AsOfWindow(as_of=now, generated_at=now, window_days=30)
    event_id = uuid.uuid4()
    site_id = uuid.uuid4()
    evidence = [EvidenceReference(evidence_type=EvidenceType.SAFETY_EVENT, reference_id=event_id)]

    defaults = dict(
        organization_id=organization_id,
        scope="organization",
        entity_id=None,
        as_of=as_of,
        data_sufficiency=EnterpriseDataSufficiency.SUFFICIENT_DATA,
        event_count=12,
        deterministic_risk=RiskScoreDTO(
            score=42.0,
            classification=EnterpriseRiskClassification.MODERATE,
            components=[RiskScoreComponentDTO(key="trend", label="Trend", raw_score=50.0, weight=30.0, normalized_weight=30.0, contribution=15.0)],
        ),
        trend=EnterpriseTrendDTO(
            classification=EnterpriseTrendClassification.IMPROVING,
            metric="incident_count",
            current_value=1,
            previous_value=3,
            absolute_change=-2,
            percentage_change=-66.7,
            current_period_start=now,
            current_period_end=now,
            previous_period_start=now,
            previous_period_end=now,
        ),
        indicators=[
            EnterpriseIndicatorDTO(key="near_miss_count", label="Near misses", value=5, category=EnterpriseIndicatorCategory.LEADING, period_start=now, period_end=now, window_days=30)
        ],
        patterns=[
            RecurrencePatternDTO(
                pattern_key="p1", scope="site:s1", site_id=site_id, site_label="North Yard", event_type="NEAR_MISS", event_subtype=None,
                count=5, first_seen=now, last_seen=now, window_start=now, window_end=now, window_days=90,
                classification=RecurrenceClassification.RECURRING, evidence=evidence,
            )
        ],
        concentrations=[ConcentrationContributorDTO(dimension="site", key="s1", label="North Yard", count=5, total=10, percentage=50.0, classification=ConcentrationClassification.MODERATE)],
        anomalies=[
            EnterpriseAnomalyDTO(
                metric="vehicle_incidents", label="Vehicle incidents", status=EnterpriseAnomalyStatus.ANOMALOUS, direction=EnterpriseAnomalyDirection.ABOVE_BASELINE,
                current_value=8, baseline_mean=3, baseline_stdev=1, z_score=3.2, baseline_period_count=6,
                current_period_start=now, current_period_end=now, window_days=30, supporting_event_count=8, evidence=evidence,
            )
        ],
        associations=[
            EnterpriseAssociationDTO(
                metric_a="near_misses", metric_b="observations", label_a="Near misses", label_b="Observations",
                classification=EnterpriseAssociationClassification.MODERATE_POSITIVE, correlation_coefficient=0.55,
                period_count=6, period_start=now, period_end=now, window_days=90, evidence=evidence,
            )
        ],
        explanations=[ExplanationItemDTO(code="RISK_ELEVATED", message="Risk is elevated.", value=42.0)],
        provenance=EnterpriseIntelligenceProvenanceDTO(window_start=now, window_end=now, event_count=12, total_supporting_events=12, evidence_sample=evidence),
        actions_context=ActionsContextDTO(open_action_count=3, overdue_action_count=1, high_priority_action_count=2),
    )
    defaults.update(overrides)
    return EnterpriseIntelligenceResultDTO(**defaults)


# --- Authentication / authorization --------------------------------------------------------------


def test_enterprise_intelligence_requires_authentication(client):
    response = client.get(f"/api/v1/intelligence/enterprise?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


def test_enterprise_intelligence_is_501_when_commercial_core_is_not_configured(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])
    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )
    assert response.status_code == 501


def test_enterprise_intelligence_tenant_security_a_machine_credential_cannot_reach_a_different_organization(
    client, db_session, monkeypatch
):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    credential = _make_client_credential(db_session, uuid.UUID(org_a["id"]), scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeEnterpriseIntelligenceClient(result=_full_result(uuid.UUID(org_b["id"])))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org_b['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 403
    assert fake_client.calls == []  # the client was never even invoked


def test_enterprise_intelligence_rejects_a_nonexistent_organization_with_403_not_500(client, db_session):
    """TASK G1 regression: mirrors `tests.test_intelligence_api::
    test_analytics_summary_rejects_a_nonexistent_organization_with_403_not_500`
    for this route -- proves the fix in `app/api/deps_context.py::
    _log_access_denied` is genuinely shared infrastructure, not an
    Enterprise-Intelligence-specific patch."""
    user = make_user(db_session, "no-such-org-enterprise@example.com")
    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={uuid.uuid4()}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


# --- Success: full response-shape reproof ----------------------------------------------------------


def test_enterprise_intelligence_succeeds_and_response_contains_every_field_the_frontend_reads(client, db_session, monkeypatch):
    """Proves `_enterprise_intelligence_response()`'s reshaping: scope
    is called with "organization"; `data_sufficiency` becomes a
    `{status, event_count}` object (not the bare contract enum string);
    `deterministic_risk` (not `risk`) carries score/classification;
    `patterns`/`anomalies`/`associations` each carry a plain
    `supporting_event_ids: string[]` (not the contract's typed
    `evidence: EvidenceReference[]`); `provenance` carries
    organization_id/scope/entity_id/as_of/window_days duplicated from
    the top level, exactly as the existing frontend's
    `IntelligenceProvenance` type expects."""
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])

    result = _full_result(org_id)
    fake_client = _FakeEnterpriseIntelligenceClient(result=result)
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}&window_days=30", headers=_bearer(credential)
    )

    assert response.status_code == 200
    body = response.json()

    assert body["scope"] == "organization"
    assert body["organization_id"] == str(org_id)
    assert body["entity_id"] is None
    assert body["window_days"] == 30
    assert "as_of" in body

    assert body["data_sufficiency"] == {"status": "SUFFICIENT_DATA", "event_count": 12}

    assert body["deterministic_risk"]["score"] == 42.0
    assert body["deterministic_risk"]["classification"] == "MODERATE"
    assert "version" not in body["deterministic_risk"]

    assert body["trend"]["metric"] == "incident_count"
    assert body["trend"]["classification"] == "IMPROVING"
    assert "calculation_version" not in body["trend"]

    assert body["indicators"][0]["key"] == "near_miss_count"
    assert "calculation_version" not in body["indicators"][0]

    pattern = body["patterns"][0]
    assert pattern["pattern_key"] == "p1"
    assert isinstance(pattern["supporting_event_ids"], list)
    assert "evidence" not in pattern
    assert "calculation_version" not in pattern

    anomaly = body["anomalies"][0]
    assert anomaly["status"] == "ANOMALOUS"
    assert isinstance(anomaly["supporting_event_ids"], list)
    assert "evidence" not in anomaly

    association = body["associations"][0]
    assert association["classification"] == "MODERATE_POSITIVE"
    assert isinstance(association["supporting_event_ids"], list)
    assert "evidence" not in association

    assert body["concentrations"][0]["dimension"] == "site"
    assert body["explanations"][0]["code"] == "RISK_ELEVATED"
    assert body["actions_context"] == {"open_action_count": 3, "overdue_action_count": 1, "high_priority_action_count": 2}

    provenance = body["provenance"]
    assert provenance["organization_id"] == str(org_id)
    assert provenance["scope"] == "organization"
    assert provenance["entity_id"] is None
    assert "as_of" in provenance
    assert provenance["window_days"] == 30
    assert provenance["event_count"] == 12
    assert provenance["total_supporting_events"] == 12
    assert isinstance(provenance["evidence_sample_event_ids"], list)
    assert "calculation_versions" not in provenance

    assert "predictive_context" not in body

    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["organization_id"] == org_id
    assert fake_client.calls[0]["scope"] == "organization"
    assert fake_client.calls[0]["site_id"] is None


def test_enterprise_intelligence_propagates_the_public_sie_request_id_to_the_client_call(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeEnterpriseIntelligenceClient(result=_full_result(org_id))
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 200
    assert fake_client.calls[0]["request_id"] == response.headers["X-Request-Id"]


def test_enterprise_intelligence_maps_a_client_integration_error_to_503_model_not_available(client, db_session, monkeypatch):
    from app.integrations.commercial_core import (
        CommercialCoreDependencyUnavailableError,
    )

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])
    fake_client = _FakeEnterpriseIntelligenceClient(
        error=CommercialCoreDependencyUnavailableError("A Commercial Core dependency is currently unavailable.")
    )
    monkeypatch.setattr("app.api.v1.intelligence.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_AVAILABLE"


def test_enterprise_intelligence_response_never_exposes_a_client_secret(client, db_session, monkeypatch):
    import httpx

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])

    secret = "super-secret-value-must-never-leak"

    def fake_post(url, *, json, headers, timeout):
        raise httpx.ConnectError(f"could not connect using {secret}")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(
        "app.api.v1.intelligence.get_commercial_core_client",
        lambda: __import__("app.integrations.commercial_core", fromlist=["HttpCommercialCoreClient"]).HttpCommercialCoreClient(
            base_url="https://cc.example.com", client_id="cid", client_secret=secret, timeout_seconds=2.0
        ),
    )

    response = client.get(
        f"/api/v1/intelligence/enterprise?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert secret not in response.text
