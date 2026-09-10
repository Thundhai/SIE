"""SIE Milestone 34: Human Decision & Intervention Trace — HTTP-layer
tests for `POST /api/v1/intelligence/decisions`,
`GET /api/v1/intelligence/decisions`, and
`GET /api/v1/intelligence/decisions/{decision_id}`. Mirrors
`tests/test_attention_api.py`'s own established shape: runs against the
ordinary SQLite `client` fixture.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.safety_action import SafetyAction
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.intelligence_test_helpers import make_org, make_safety_event, seed_risk_area_ontology_concepts
from tests.test_ingestion_api import create_org, make_membership, make_user

AS_OF = datetime.now(timezone.utc)


def _make_client_credential(db_session, org_id, *, scopes=None):
    scopes = scopes if scopes is not None else [Permission.INTELLIGENCE_DECISION_WRITE, Permission.INTELLIGENCE_READ]
    return api_client_service.create(db_session, organization_id=org_id, name="Test Integration", scopes=scopes)


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _seed_incidents(db_session, org_id, *, count=8):
    for i in range(count):
        db_session.add(
            make_safety_event(
                organization_id=org_id,
                event_type="INCIDENT",
                event_time=AS_OF - timedelta(days=i),
                ingestion_time=AS_OF - timedelta(days=i),
                source_record_id=str(uuid.uuid4()),
            )
        )
    db_session.commit()


def _get_attention(client, org_id, headers):
    response = client.get(f"/api/v1/intelligence/attention?organization_id={org_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _decision_body(attention_response, item, **overrides):
    body = {
        "scope": attention_response["scope"],
        "site_id": attention_response["entity_id"],
        "as_of": attention_response["as_of"],
        "window_days": attention_response["window_days"],
        "attention_reference": item["reference"],
        "decision": "DO_NOT_ACT",
        "rationale": "Existing control verified effective.",
    }
    body.update(overrides)
    return body


# --- Authorization ---------------------------------------------------------------------------


def test_create_decision_requires_authentication(client):
    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={uuid.uuid4()}",
        json={
            "scope": "organization", "as_of": AS_OF.isoformat(), "window_days": 30,
            "attention_reference": "x", "decision": "DEFER", "rationale": "test",
        },
    )
    assert response.status_code == 401


def test_create_decision_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider@example.com")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json={
            "scope": "organization", "as_of": AS_OF.isoformat(), "window_days": 30,
            "attention_reference": "x", "decision": "DEFER", "rationale": "test",
        },
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_create_decision_requires_intelligence_decision_write_permission(client, db_session):
    """A VIEWER (INTELLIGENCE_READ only, no write) must be rejected --
    §12's "human users require the appropriate permission"."""
    org = create_org(client)
    user = make_user(db_session, "viewer@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)
    assert attention["items"], "expected at least one attention item for this fixture"

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, attention["items"][0]),
        headers=headers,
    )
    assert response.status_code == 403


def test_hse_manager_can_create_a_decision(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, attention["items"][0]),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision"] == "DO_NOT_ACT"
    assert body["decided_by_user_id"] == str(user.id)
    assert body["decided_by_api_client_id"] is None


def test_machine_client_with_scope_can_create_a_decision(client, db_session):
    org = create_org(client)
    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))
    attention = _get_attention(client, org["id"], _bearer(credential))

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, attention["items"][0]),
        headers=_bearer(credential),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decided_by_api_client_id"] == str(credential.api_client.id)
    assert body["decided_by_user_id"] is None


def test_machine_client_without_write_scope_is_rejected(client, db_session):
    org = create_org(client)
    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    read_only_credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])
    attention = _get_attention(client, org["id"], _bearer(read_only_credential))

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, attention["items"][0]),
        headers=_bearer(read_only_credential),
    )
    assert response.status_code == 403


def test_machine_client_cannot_create_a_decision_for_a_different_organization(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org_a["id"]))
    credential_a = _make_client_credential(db_session, uuid.UUID(org_a["id"]))
    attention = _get_attention(client, org_a["id"], _bearer(credential_a))

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org_b['id']}",
        json=_decision_body(attention, attention["items"][0]),
        headers=_bearer(credential_a),
    )
    assert response.status_code == 403


# --- Human authority / cannot impersonate another decision-maker -------------------------------


def test_decided_by_user_id_cannot_be_supplied_by_the_client(client, db_session):
    """The request body has no `decided_by_user_id` field at all --
    supplying one is simply ignored (extra body fields are dropped by
    Pydantic, never interpreted), and the decision-maker is always
    derived from RequestContext."""
    org = create_org(client)
    user = make_user(db_session, "real-decider@example.com")
    impersonated_id = uuid.uuid4()
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)

    body = _decision_body(attention, attention["items"][0])
    body["decided_by_user_id"] = str(impersonated_id)  # attempted impersonation
    response = client.post(f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["decided_by_user_id"] == str(user.id)
    assert response.json()["decided_by_user_id"] != str(impersonated_id)


# --- Provenance --------------------------------------------------------------------------------


def test_decision_response_preserves_sie_priority_and_provenance(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager2@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)
    item = attention["items"][0]

    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, item, decision="ACT", rationale="Field conditions require immediate intervention."),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["attention_category"] == item["category"]
    assert body["attention_priority"] == item["priority"]  # SIE's own priority, never overwritten
    assert body["attention_title"] == item["title"]
    assert body["intelligence_as_of"] == attention["as_of"]
    assert body["intelligence_window_days"] == attention["window_days"]
    assert body["calculation_version"] == item["evidence"]["calculation_version"]
    assert body["decision"] == "ACT"  # the human's own, separate fact -- never inferred from priority


def test_invalid_attention_reference_is_404(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager3@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(user.id)
    body = {
        "scope": "organization", "site_id": None, "as_of": AS_OF.isoformat(), "window_days": 30,
        "attention_reference": "DETERIORATING_TREND:organization:org:not-a-real-one", "decision": "DEFER",
        "rationale": "test",
    }
    response = client.post(f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=body, headers=headers)
    assert response.status_code == 404


def test_rationale_is_required(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager4@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)
    body = _decision_body(attention, attention["items"][0], rationale="")
    response = client.post(f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=body, headers=headers)
    assert response.status_code == 422


def test_every_decision_enum_value_is_accepted(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager5@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)
    item = attention["items"][0]

    for decision_value in ("ACT", "DO_NOT_ACT", "DEFER", "ALREADY_ADDRESSED", "NOT_RELEVANT"):
        response = client.post(
            f"/api/v1/intelligence/decisions?organization_id={org['id']}",
            json=_decision_body(attention, item, decision=decision_value, rationale=f"Testing {decision_value}."),
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["decision"] == decision_value


# --- SafetyAction linkage ------------------------------------------------------------------------


def test_decision_can_link_an_existing_same_tenant_action(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager6@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    action = SafetyAction(
        organization_id=uuid.UUID(org["id"]), title="Existing corrective action", action_type="CORRECTIVE",
        priority="HIGH", status="OPEN", attributes={},
    )
    db_session.add(action)
    db_session.commit()

    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)
    body = _decision_body(attention, attention["items"][0], decision="ACT", rationale="Linking existing action.", linked_action_id=str(action.id))
    response = client.post(f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["linked_action_id"] == str(action.id)
    assert result["linked_action"]["title"] == "Existing corrective action"

    # Readable from the decision side directly.
    get_response = client.get(f"/api/v1/intelligence/decisions/{result['id']}?organization_id={org['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["linked_action_id"] == str(action.id)

    # Readable "from the action side" via the reverse-lookup filter.
    list_response = client.get(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}&linked_action_id={action.id}", headers=headers
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == result["id"]


def test_decision_rejects_a_cross_tenant_action(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    user = make_user(db_session, "manager7@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org_a["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org_a["id"]))
    other_org_action = SafetyAction(
        organization_id=uuid.UUID(org_b["id"]), title="Org B's action", action_type="CORRECTIVE", priority="HIGH",
        status="OPEN", attributes={},
    )
    db_session.add(other_org_action)
    db_session.commit()

    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org_a["id"], headers)
    body = _decision_body(
        attention, attention["items"][0], decision="ACT", rationale="test", linked_action_id=str(other_org_action.id)
    )
    response = client.post(f"/api/v1/intelligence/decisions?organization_id={org_a['id']}", json=body, headers=headers)
    assert response.status_code == 404


def test_decision_rejects_a_nonexistent_action(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager8@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)
    body = _decision_body(
        attention, attention["items"][0], decision="ACT", rationale="test", linked_action_id=str(uuid.uuid4())
    )
    response = client.post(f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=body, headers=headers)
    assert response.status_code == 404


def test_act_decision_never_automatically_creates_an_action(client, db_session):
    from sqlalchemy import func, select

    org = create_org(client)
    user = make_user(db_session, "manager9@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    before = db_session.execute(select(func.count()).select_from(SafetyAction)).scalar_one()

    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)
    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, attention["items"][0], decision="ACT", rationale="Will link an action later."),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["linked_action_id"] is None

    after = db_session.execute(select(func.count()).select_from(SafetyAction)).scalar_one()
    assert before == after


# --- History / immutability -----------------------------------------------------------------


def test_a_second_decision_on_the_same_reference_is_a_new_row_not_an_overwrite(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager10@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    attention = _get_attention(client, org["id"], headers)
    item = attention["items"][0]

    first = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, item, decision="DEFER", rationale="Will revisit."),
        headers=headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, item, decision="ACT", rationale="Changed my mind -- acting now."),
        headers=headers,
    )
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]  # a new row, the first is never destroyed

    history = client.get(
        "/api/v1/intelligence/decisions",
        params={"organization_id": org["id"], "attention_reference": item["reference"]},
        headers=headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2
    returned_ids = {d["id"] for d in history.json()["items"]}
    assert returned_ids == {first.json()["id"], second.json()["id"]}
    # Newest first.
    assert history.json()["items"][0]["id"] == second.json()["id"]
    assert history.json()["items"][0]["decision"] == "ACT"
    assert history.json()["items"][1]["decision"] == "DEFER"


# --- Idempotency ---------------------------------------------------------------------------------


def test_duplicate_idempotent_request_does_not_create_a_duplicate_decision(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager11@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "test-key-1"}
    attention = _get_attention(client, org["id"], dev_auth_headers(user.id))
    body = _decision_body(attention, attention["items"][0])

    first = client.post(f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=body, headers=headers)
    second = client.post(f"/api/v1/intelligence/decisions?organization_id={org['id']}", json=body, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    list_response = client.get(
        "/api/v1/intelligence/decisions",
        params={"organization_id": org["id"], "attention_reference": attention["items"][0]["reference"]},
        headers=dev_auth_headers(user.id),
    )
    assert list_response.json()["total"] == 1


def test_same_idempotency_key_with_a_different_body_conflicts(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager12@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "test-key-2"}
    attention = _get_attention(client, org["id"], dev_auth_headers(user.id))
    item = attention["items"][0]

    first = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, item, decision="DEFER"), headers=headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org['id']}",
        json=_decision_body(attention, item, decision="ACT", rationale="A genuinely different request."),
        headers=headers,
    )
    assert second.status_code == 409


# --- Tenant isolation --------------------------------------------------------------------------


def test_cannot_read_another_organizations_decisions(client, db_session):
    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    user_a = make_user(db_session, "org-a-user@example.com")
    user_b = make_user(db_session, "org-b-user@example.com")
    make_membership(db_session, user_id=user_a.id, organization_id=uuid.UUID(org_a["id"]), role="HSE_MANAGER")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org_a["id"]))
    headers_a = dev_auth_headers(user_a.id)
    attention = _get_attention(client, org_a["id"], headers_a)
    created = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org_a['id']}",
        json=_decision_body(attention, attention["items"][0]), headers=headers_a,
    )
    assert created.status_code == 201
    decision_id = created.json()["id"]

    # Org B cannot read Org A's decision by id.
    headers_b = dev_auth_headers(user_b.id)
    get_response = client.get(f"/api/v1/intelligence/decisions/{decision_id}?organization_id={org_b['id']}", headers=headers_b)
    assert get_response.status_code == 404

    # Org B's list never includes it.
    list_response = client.get(f"/api/v1/intelligence/decisions?organization_id={org_b['id']}", headers=headers_b)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_cross_tenant_site_reference_is_rejected(client, db_session):
    from tests.intelligence_test_helpers import make_site

    org_a = create_org(client, name="Org A")
    org_b = create_org(client, name="Org B")
    user = make_user(db_session, "manager13@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org_a["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    site_b = make_site(db_session, uuid.UUID(org_b["id"]), name="Org B's Site")
    headers = dev_auth_headers(user.id)

    body = {
        "scope": "site", "site_id": str(site_b.id), "as_of": AS_OF.isoformat(), "window_days": 30,
        "attention_reference": "whatever", "decision": "DEFER", "rationale": "test",
    }
    response = client.post(f"/api/v1/intelligence/decisions?organization_id={org_a['id']}", json=body, headers=headers)
    assert response.status_code == 404


# --- Read-only boundary (M32/M33 unaffected) ---------------------------------------------------


def test_attention_and_context_endpoints_remain_read_only(client, db_session):
    """The decision endpoint is the *only* new write path -- GET
    /intelligence/attention and GET /intelligence/context must never
    write anything, before or after this milestone."""
    from sqlalchemy import func, select

    from app.models.intelligence_decision import IntelligenceDecision

    org = create_org(client)
    user = make_user(db_session, "manager14@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)

    before = db_session.execute(select(func.count()).select_from(IntelligenceDecision)).scalar_one()
    context_response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=headers)
    attention_response = client.get(f"/api/v1/intelligence/attention?organization_id={org['id']}", headers=headers)
    assert context_response.status_code == 200
    assert attention_response.status_code == 200
    after = db_session.execute(select(func.count()).select_from(IntelligenceDecision)).scalar_one()
    assert before == after == 0


def test_get_decisions_never_writes(client, db_session):
    from sqlalchemy import func, select

    from app.models.intelligence_decision import IntelligenceDecision

    org = create_org(client)
    user = make_user(db_session, "manager15@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers = dev_auth_headers(user.id)
    before = db_session.execute(select(func.count()).select_from(IntelligenceDecision)).scalar_one()
    response = client.get(f"/api/v1/intelligence/decisions?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []
    after = db_session.execute(select(func.count()).select_from(IntelligenceDecision)).scalar_one()
    assert before == after == 0
