"""Roadmap Phase 1: `POST /api/v1/intelligence/decisions`,
`GET /api/v1/intelligence/decisions`, and
`GET /api/v1/intelligence/decisions/{decision_id}` -- the Public SIE
API routes wired to the real Commercial Core Decisions client. Mirrors
`tests/test_enterprise_intelligence_api.py`'s own
`_FakeEnterpriseIntelligenceClient`/`monkeypatch` structure and fakes
exactly. `memory-context` stays a 501 stub (Roadmap Phase 2) and is not
covered here beyond that one assertion.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sie_contract import ActorType, AttentionPriority, AttentionScope, DecisionListResultDTO, DecisionReferenceDTO

from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.test_ingestion_api import create_org, make_user
from tests.test_intelligence_api import _bearer, _make_client_credential


class _FakeDecisionsClient:
    """A `CommercialCoreClient` test double covering
    `create_decision`/`get_decision`/`list_decisions` -- mirrors
    `_FakeEnterpriseIntelligenceClient`'s identical shape."""

    def __init__(self, *, create_result=None, get_result=None, list_result=None, error: Exception | None = None):
        self._create_result = create_result
        self._get_result = get_result
        self._list_result = list_result
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    def unavailable(self, capability: str):
        raise NotImplementedError

    def create_decision(self, **kwargs):
        self.calls.append(("create_decision", kwargs))
        if self._error is not None:
            raise self._error
        return self._create_result

    def get_decision(self, **kwargs):
        self.calls.append(("get_decision", kwargs))
        if self._error is not None:
            raise self._error
        return self._get_result

    def list_decisions(self, **kwargs):
        self.calls.append(("list_decisions", kwargs))
        if self._error is not None:
            raise self._error
        return self._list_result


def _decision_dto(organization_id, **overrides) -> DecisionReferenceDTO:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=organization_id,
        attention_reference="attn:org:2026-06-01:trend:0",
        scope=AttentionScope.ORGANIZATION,
        site_id=None,
        attention_category="enterprise_trend",
        attention_priority=AttentionPriority.HIGH,
        attention_title="Rising incident rate",
        decision_type="ACT",
        rationale="Escalated to site manager.",
        decided_at=datetime.now(timezone.utc),
        actor_type=ActorType.HUMAN,
        actor_id=uuid.uuid4(),
    )
    defaults.update(overrides)
    return DecisionReferenceDTO(**defaults)


def _create_body(**overrides) -> dict:
    body = {
        "scope": "organization",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "window_days": 30,
        "attention_reference": "attn:org:2026-06-01:trend:0",
        "decision": "ACT",
        "rationale": "Escalated to site manager.",
    }
    body.update(overrides)
    return body


# --- Authentication / authorization --------------------------------------------------------------


def test_create_decision_requires_authentication(client):
    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={uuid.uuid4()}", json=_create_body()
    )
    assert response.status_code == 401


def test_list_decisions_requires_authentication(client):
    response = client.get(f"/api/v1/intelligence/decisions?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


def test_create_decision_is_501_when_commercial_core_is_not_configured(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_DECISION_WRITE])
    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=_create_body(), headers=_bearer(credential)
    )
    assert response.status_code == 501


def test_memory_context_is_always_a_501_stub(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])
    response = client.get(
        f"/api/v1/intelligence/decisions/{uuid.uuid4()}/memory-context?organization_id={org['id']}",
        headers=_bearer(credential),
    )
    assert response.status_code == 501


def test_create_decision_tenant_security_a_machine_credential_cannot_write_for_a_different_organization(
    client, db_session, monkeypatch
):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    credential = _make_client_credential(db_session, uuid.UUID(org_a["id"]), scopes=[Permission.INTELLIGENCE_DECISION_WRITE])
    fake_client = _FakeDecisionsClient(create_result=_decision_dto(uuid.UUID(org_b["id"])))
    monkeypatch.setattr("app.api.v1.intelligence_decisions.get_commercial_core_client", lambda: fake_client)

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org_b['id']}", json=_create_body(), headers=_bearer(credential)
    )

    assert response.status_code == 403
    assert fake_client.calls == []  # the client was never even invoked


def test_create_decision_rejects_a_nonexistent_organization_with_403_not_500(client, db_session):
    user = make_user(db_session, "no-such-org-decisions@example.com")
    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={uuid.uuid4()}",
        json=_create_body(),
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


# --- Success: response shape -----------------------------------------------------------------------


def test_create_decision_succeeds_and_response_matches_the_contract_shape(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_DECISION_WRITE])

    dto = _decision_dto(org_id)
    fake_client = _FakeDecisionsClient(create_result=dto)
    monkeypatch.setattr("app.api.v1.intelligence_decisions.get_commercial_core_client", lambda: fake_client)

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=_create_body(), headers=_bearer(credential)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(dto.id)
    assert body["attention_reference"] == dto.attention_reference
    assert body["attention_title"] == dto.attention_title
    assert body["decision"] == "ACT"
    assert body["actor_type"] == "human"
    assert body["actor_id"] == str(dto.actor_id)
    for private_field in ("calculation_version", "evidence_source", "evidence_entity_ids", "linked_action", "decided_by_user_id"):
        assert private_field not in body

    call_name, call_kwargs = fake_client.calls[0]
    assert call_name == "create_decision"
    assert call_kwargs["organization_id"] == org_id
    # The test caller is a machine API client (_make_client_credential) --
    # the route must derive actor_type from the real caller's own kind,
    # never hardcode or guess it.
    assert call_kwargs["actor_type"] == ActorType.MACHINE
    assert call_kwargs["actor_id"] == credential.api_client.id


def test_list_decisions_succeeds_and_response_contains_the_envelope(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])

    dto = _decision_dto(org_id)
    fake_client = _FakeDecisionsClient(list_result=DecisionListResultDTO(items=[dto], total=1, page=1, page_size=25))
    monkeypatch.setattr("app.api.v1.intelligence_decisions.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(dto.id)


def test_get_decision_succeeds(client, db_session, monkeypatch):
    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_READ])

    dto = _decision_dto(org_id)
    fake_client = _FakeDecisionsClient(get_result=dto)
    monkeypatch.setattr("app.api.v1.intelligence_decisions.get_commercial_core_client", lambda: fake_client)

    response = client.get(
        f"/api/v1/intelligence/decisions/{dto.id}?organization_id={org['id']}", headers=_bearer(credential)
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(dto.id)


# --- Error mapping -----------------------------------------------------------------------------------


def test_create_decision_maps_commercial_core_not_found_to_404(client, db_session, monkeypatch):
    from app.integrations.commercial_core import CommercialCoreNotFoundError

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_DECISION_WRITE])

    fake_client = _FakeDecisionsClient(error=CommercialCoreNotFoundError("No attention item matches attention_reference."))
    monkeypatch.setattr("app.api.v1.intelligence_decisions.get_commercial_core_client", lambda: fake_client)

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=_create_body(), headers=_bearer(credential)
    )
    assert response.status_code == 404


def test_create_decision_maps_a_client_integration_error_to_503_model_not_available(client, db_session, monkeypatch):
    from app.integrations.commercial_core import CommercialCoreTimeoutError

    org = create_org(client)
    org_id = uuid.UUID(org["id"])
    credential = _make_client_credential(db_session, org_id, scopes=[Permission.INTELLIGENCE_DECISION_WRITE])

    fake_client = _FakeDecisionsClient(error=CommercialCoreTimeoutError("Commercial Core did not respond in time."))
    monkeypatch.setattr("app.api.v1.intelligence_decisions.get_commercial_core_client", lambda: fake_client)

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=_create_body(), headers=_bearer(credential)
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_AVAILABLE"
