"""SIE Milestone 40: Organizational Memory Architecture — HTTP-layer
tests for `POST /api/v1/intelligence/organizational-memory`,
`GET /api/v1/intelligence/organizational-memory`,
`GET /api/v1/intelligence/organizational-memory/{memory_id}`,
`POST /api/v1/intelligence/organizational-memory/{memory_id}/governance-decisions`,
`GET /api/v1/intelligence/organizational-memory/{memory_id}/governance-decisions`,
and `GET /api/v1/intelligence/organizational-memory/{memory_id}/state`.
Mirrors `tests/test_intelligence_learning_candidates_api.py`'s own
established shape: runs against the ordinary SQLite `client` fixture.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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
        "decision": "ACT",
        "rationale": "Field conditions require immediate intervention.",
    }
    body.update(overrides)
    return body


def _create_decision(client, org_id, headers) -> dict:
    attention = _get_attention(client, org_id, headers)
    response = client.post(
        f"/api/v1/intelligence/decisions?organization_id={org_id}",
        json=_decision_body(attention, attention["items"][0]),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_outcome(client, org_id, headers, decision_id, **overrides) -> dict:
    body = {
        "decision_id": decision_id,
        "classification": "EFFECTIVE",
        "summary": "Follow-up observation confirmed the hazard was corrected.",
        "outcome_at": AS_OF.isoformat(),
    }
    body.update(overrides)
    response = client.post(f"/api/v1/intelligence/outcomes?organization_id={org_id}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _make_evidence_event(db_session, org_id, **overrides):
    kwargs = dict(event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    kwargs.update(overrides)
    event = make_safety_event(organization_id=org_id, source_record_id=str(uuid.uuid4()), **kwargs)
    db_session.add(event)
    db_session.commit()
    return event


def _create_verification(client, org_id, headers, outcome_id, **overrides) -> dict:
    body = {"status": "VERIFIED", "rationale": "Confirmed on-site.", "verified_at": AS_OF.isoformat()}
    body.update(overrides)
    response = client.post(
        f"/api/v1/intelligence/outcomes/{outcome_id}/verifications?organization_id={org_id}",
        json=body, headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


_CANDIDATES_URL = "/api/v1/intelligence/learning-candidates"
_MEMORY_URL = "/api/v1/intelligence/organizational-memory"


def _create_candidate(client, org_id, headers, outcome_id) -> dict:
    response = client.post(f"{_CANDIDATES_URL}?organization_id={org_id}", json={"outcome_id": outcome_id}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _govern_candidate(client, org_id, headers, candidate_id, status, **overrides) -> dict:
    body = {"status": status, "rationale": "Governance test rationale."}
    body.update(overrides)
    response = client.post(
        f"{_CANDIDATES_URL}/{candidate_id}/governance-decisions?organization_id={org_id}", json=body, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _setup_accepted_candidate(client, db_session, email):
    """A fully accepted candidate: verified outcome + eligible learning
    candidate + ACCEPTED governance decision -- the one precondition for
    creating organizational memory."""
    org = create_org(client)
    user = make_user(db_session, email)
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    decision = _create_decision(client, org["id"], headers)
    event = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event.id)])
    verification = _create_verification(client, org["id"], headers, outcome["id"])
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    _govern_candidate(client, org["id"], headers, candidate["id"], "ACCEPTED")
    return org, user, headers, decision, outcome, verification, candidate


def _setup_pending_candidate(client, db_session, email):
    """A verified, eligible candidate that has never been governed."""
    org = create_org(client)
    user = make_user(db_session, email)
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    decision = _create_decision(client, org["id"], headers)
    event = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event.id)])
    _create_verification(client, org["id"], headers, outcome["id"])
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    return org, user, headers, decision, outcome, candidate


def _memory_body(learning_candidate_id, **overrides) -> dict:
    body = {
        "learning_candidate_id": learning_candidate_id,
        "memory_type": "LESSON_LEARNED",
        "title": "Permit checks should precede coordination meetings",
        "memory_content": (
            "Repeated permit deviations during simultaneous operations indicate that permit "
            "verification should occur before the coordination meeting."
        ),
        "rationale": "This pattern recurred across multiple accepted candidates and generalizes well.",
    }
    body.update(overrides)
    return body


def _governance_body(**overrides) -> dict:
    body = {"status": "RETRACTED", "rationale": "This turned out not to generalize as expected."}
    body.update(overrides)
    return body


# --- Authorization -----------------------------------------------------------------------------


def test_create_memory_requires_authentication(client):
    response = client.post(f"{_MEMORY_URL}?organization_id={uuid.uuid4()}", json=_memory_body(str(uuid.uuid4())))
    assert response.status_code == 401


def test_create_memory_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider-mem1@example.com")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"{_MEMORY_URL}?organization_id={org['id']}",
        json=_memory_body(str(uuid.uuid4())), headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_create_memory_requires_intelligence_decision_write_permission(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem-setup1@example.com"
    )
    viewer = make_user(db_session, "viewer-mem1@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"{_MEMORY_URL}?organization_id={org['id']}",
        json=_memory_body(candidate["id"]), headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_hse_manager_can_create_memory_from_an_accepted_candidate(client, db_session):
    org, user, headers, _decision, outcome, verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem1@example.com"
    )

    response = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["learning_candidate_id"] == candidate["id"]
    assert body["memory_type"] == "LESSON_LEARNED"
    assert body["created_by_user_id"] == str(user.id)
    assert body["created_by_api_client_id"] is None
    # Provenance chain traceable in one response (M40 spec §10).
    assert body["learning_candidate"]["outcome_id"] == outcome["id"]
    assert body["learning_candidate"]["verification_id"] == verification["id"]
    assert body["learning_candidate"]["outcome"]["classification"] == "EFFECTIVE"
    assert body["learning_candidate"]["verification"]["status"] == "VERIFIED"


def test_machine_client_with_decision_write_scope_can_create_memory(client, db_session):
    org, _, _headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem-setup2@example.com"
    )
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))

    response = client.post(
        f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=_bearer(credential)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_by_api_client_id"] == str(credential.api_client.id)
    assert body["created_by_user_id"] is None


def test_machine_client_without_write_scope_is_rejected(client, db_session):
    org, _, _headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem-setup3@example.com"
    )
    read_only = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])

    response = client.post(
        f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=_bearer(read_only)
    )
    assert response.status_code == 403


def test_machine_client_cannot_create_memory_for_a_different_organization(client, db_session):
    """The credential-bound organization is authoritative;
    `authorize_context()` rejects a mismatched query organization_id
    before the route handler is ever reached (M38-corrective, reused
    verbatim by M40)."""
    org_a, _, _headers_a, _decision_a, _outcome_a, _verification_a, candidate_a = _setup_accepted_candidate(
        client, db_session, "manager-mem19a@example.com"
    )
    org_b = create_org(client, name="Org B mem machine")
    credential_b = _make_client_credential(db_session, uuid.UUID(org_b["id"]))

    response = client.post(
        f"{_MEMORY_URL}?organization_id={org_a['id']}", json=_memory_body(candidate_a["id"]), headers=_bearer(credential_b)
    )
    assert response.status_code == 403


# --- Actor governance / cannot impersonate --------------------------------------------------------


def test_created_by_user_id_cannot_be_supplied_by_the_client(client, db_session):
    org, user, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem2@example.com"
    )
    impersonated_id = uuid.uuid4()
    body = _memory_body(candidate["id"])
    body["created_by_user_id"] = str(impersonated_id)  # attempted impersonation; not a real field

    response = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["created_by_user_id"] == str(user.id)
    assert response.json()["created_by_user_id"] != str(impersonated_id)


# --- The governance gate (M40 spec §5) -----------------------------------------------------------


def test_memory_creation_rejects_a_pending_candidate(client, db_session):
    org, _, headers, _decision, _outcome, candidate = _setup_pending_candidate(
        client, db_session, "manager-mem3@example.com"
    )

    response = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    assert response.status_code == 422


def test_memory_creation_rejects_a_rejected_candidate(client, db_session):
    org, _, headers, _decision, _outcome, candidate = _setup_pending_candidate(
        client, db_session, "manager-mem4@example.com"
    )
    _govern_candidate(client, org["id"], headers, candidate["id"], "REJECTED")

    response = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    assert response.status_code == 422


def test_memory_creation_requires_a_valid_candidate_id(client, db_session):
    org, _, headers, _decision, _outcome, _verification, _candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem5@example.com"
    )

    response = client.post(
        f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(str(uuid.uuid4())), headers=headers
    )
    assert response.status_code == 404


def test_memory_creation_rejects_a_cross_tenant_candidate(client, db_session):
    org_a, _, headers_a, _decision_a, _outcome_a, _verification_a, candidate_a = _setup_accepted_candidate(
        client, db_session, "manager-mem6a@example.com"
    )
    org_b = create_org(client, name="Org B mem")
    user_b = make_user(db_session, "manager-mem6b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    response = client.post(
        f"{_MEMORY_URL}?organization_id={org_b['id']}", json=_memory_body(candidate_a["id"]), headers=headers_b
    )
    assert response.status_code == 404


def test_memory_content_is_rejected_when_empty(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem7@example.com"
    )

    response = client.post(
        f"{_MEMORY_URL}?organization_id={org['id']}",
        json=_memory_body(candidate["id"], memory_content=""), headers=headers,
    )
    assert response.status_code == 422


def test_rationale_is_required(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem8@example.com"
    )

    response = client.post(
        f"{_MEMORY_URL}?organization_id={org['id']}",
        json=_memory_body(candidate["id"], rationale=""), headers=headers,
    )
    assert response.status_code == 422


# --- Idempotent by construction (M40 spec §15) ---------------------------------------------------


def test_repeat_memory_creation_for_the_same_candidate_returns_the_existing_row(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem9@example.com"
    )

    first = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    second = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    list_response = client.get(_MEMORY_URL, params={"organization_id": org["id"]}, headers=headers)
    assert list_response.json()["total"] == 1


def test_duplicate_idempotency_key_request_does_not_create_a_duplicate_memory(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem10@example.com"
    )
    idem_headers = {**headers, "Idempotency-Key": "mem-test-key-1"}

    first = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=idem_headers)
    second = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=idem_headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_same_idempotency_key_with_a_different_candidate_conflicts(client, db_session):
    org, user, headers, decision, outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem11@example.com"
    )
    # A second, independent accepted candidate in the same org.
    event2 = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome2 = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event2.id)])
    _create_verification(client, org["id"], headers, outcome2["id"])
    candidate2 = _create_candidate(client, org["id"], headers, outcome2["id"])
    _govern_candidate(client, org["id"], headers, candidate2["id"], "ACCEPTED")
    idem_headers = {**headers, "Idempotency-Key": "mem-test-key-2"}

    first = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=idem_headers)
    assert first.status_code == 201
    second = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate2["id"]), headers=idem_headers)
    assert second.status_code == 409


# --- Reads: list/get -------------------------------------------------------------------------------


def test_get_memory_returns_composed_provenance_chain(client, db_session):
    org, _, headers, _decision, outcome, verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem12@example.com"
    )
    created = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    memory_id = created.json()["id"]

    response = client.get(f"{_MEMORY_URL}/{memory_id}", params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["learning_candidate"]["id"] == candidate["id"]
    assert body["learning_candidate"]["outcome"]["id"] == outcome["id"]
    assert body["learning_candidate"]["verification"]["id"] == verification["id"]


def test_get_memory_requires_a_valid_id(client, db_session):
    org, _, headers, _decision, _outcome, _verification, _candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem13@example.com"
    )
    response = client.get(f"{_MEMORY_URL}/{uuid.uuid4()}", params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 404


def test_list_memory_filters_by_memory_type(client, db_session):
    org, _, headers, decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem14@example.com"
    )
    event2 = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome2 = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event2.id)])
    _create_verification(client, org["id"], headers, outcome2["id"])
    candidate2 = _create_candidate(client, org["id"], headers, outcome2["id"])
    _govern_candidate(client, org["id"], headers, candidate2["id"], "ACCEPTED")

    client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"], memory_type="LESSON_LEARNED"), headers=headers)
    client.post(
        f"{_MEMORY_URL}?organization_id={org['id']}",
        json=_memory_body(candidate2["id"], memory_type="CONTROL_INSIGHT"), headers=headers,
    )

    response = client.get(_MEMORY_URL, params={"organization_id": org["id"], "memory_type": "CONTROL_INSIGHT"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["memory_type"] == "CONTROL_INSIGHT"


def test_list_memory_pagination(client, db_session):
    org, _, headers, decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem15@example.com"
    )
    client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    for _ in range(2):
        event = _make_evidence_event(db_session, uuid.UUID(org["id"]))
        outcome = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event.id)])
        _create_verification(client, org["id"], headers, outcome["id"])
        cand = _create_candidate(client, org["id"], headers, outcome["id"])
        _govern_candidate(client, org["id"], headers, cand["id"], "ACCEPTED")
        client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(cand["id"]), headers=headers)

    page1 = client.get(_MEMORY_URL, params={"organization_id": org["id"], "page": 1, "page_size": 2}, headers=headers)
    assert page1.status_code == 200
    assert page1.json()["total"] == 3
    assert len(page1.json()["items"]) == 2
    page2 = client.get(_MEMORY_URL, params={"organization_id": org["id"], "page": 2, "page_size": 2}, headers=headers)
    assert len(page2.json()["items"]) == 1


# --- No PUT/PATCH/DELETE (immutability) ----------------------------------------------------------


def test_no_put_route_exists_for_memory(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem16@example.com"
    )
    created = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    memory_id = created.json()["id"]

    put_response = client.put(f"{_MEMORY_URL}/{memory_id}?organization_id={org['id']}", json={}, headers=headers)
    assert put_response.status_code in (404, 405)


def test_no_delete_route_exists_for_memory(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem17@example.com"
    )
    created = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    memory_id = created.json()["id"]

    delete_response = client.delete(f"{_MEMORY_URL}/{memory_id}?organization_id={org['id']}", headers=headers)
    assert delete_response.status_code in (404, 405)


# --- Auditability -----------------------------------------------------------------------------


def test_memory_creation_creates_an_audit_record(client, db_session):
    from sqlalchemy import func, select

    from app.models.audit_log import AuditLog

    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem18@example.com"
    )
    before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()

    response = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    assert response.status_code == 201

    after = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before + 1
    log_row = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ORGANIZATIONAL_MEMORY_CREATED")
    ).scalar_one()
    assert log_row.resource_id == uuid.UUID(response.json()["id"])


def test_repeat_memory_creation_does_not_duplicate_the_audit_record(client, db_session):
    from sqlalchemy import func, select

    from app.models.audit_log import AuditLog

    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem20@example.com"
    )

    client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    after = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before


# --- Tenant isolation --------------------------------------------------------------------------


def test_cannot_read_another_organizations_memory(client, db_session):
    org_a, _, headers_a, _decision_a, _outcome_a, _verification_a, candidate_a = _setup_accepted_candidate(
        client, db_session, "manager-mem21a@example.com"
    )
    org_b = create_org(client, name="Org B mem read")
    user_b = make_user(db_session, "manager-mem21b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    created = client.post(f"{_MEMORY_URL}?organization_id={org_a['id']}", json=_memory_body(candidate_a["id"]), headers=headers_a)
    assert created.status_code == 201

    response = client.get(f"{_MEMORY_URL}/{created.json()['id']}", params={"organization_id": org_b["id"]}, headers=headers_b)
    assert response.status_code == 404


# --- Governance decisions ------------------------------------------------------------------------


def _create_memory(client, org_id, headers, candidate_id) -> dict:
    response = client.post(f"{_MEMORY_URL}?organization_id={org_id}", json=_memory_body(candidate_id), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_hse_manager_can_retract_a_memory(client, db_session):
    org, user, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem22@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])

    response = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="RETRACTED"), headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["memory_id"] == memory["id"]
    assert body["status"] == "RETRACTED"
    assert body["decided_by_user_id"] == str(user.id)


def test_governance_decision_requires_intelligence_decision_write_permission(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem23@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])
    viewer = make_user(db_session, "viewer-mem23@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(), headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_governance_decision_requires_a_valid_memory_id(client, db_session):
    org, _, headers, _decision, _outcome, _verification, _candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem24@example.com"
    )

    response = client.post(
        f"{_MEMORY_URL}/{uuid.uuid4()}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(), headers=headers,
    )
    assert response.status_code == 404


def test_governance_decision_rejects_a_cross_tenant_memory(client, db_session):
    org_a, _, headers_a, _decision_a, _outcome_a, _verification_a, candidate_a = _setup_accepted_candidate(
        client, db_session, "manager-mem25a@example.com"
    )
    memory_a = _create_memory(client, org_a["id"], headers_a, candidate_a["id"])
    org_b = create_org(client, name="Org B mem gov")
    user_b = make_user(db_session, "manager-mem25b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    response = client.post(
        f"{_MEMORY_URL}/{memory_a['id']}/governance-decisions?organization_id={org_b['id']}",
        json=_governance_body(), headers=headers_b,
    )
    assert response.status_code == 404


def test_rationale_is_required_for_a_governance_decision(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem26@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])

    response = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(rationale=""), headers=headers,
    )
    assert response.status_code == 422


def test_a_second_governance_decision_is_a_new_row_not_an_overwrite(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem27@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])

    first = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="RETRACTED", rationale="First pass -- outdated."), headers=headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="ACTIVE", rationale="Reconsidered -- still applies."), headers=headers,
    )
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    history = client.get(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions", params={"organization_id": org["id"]}, headers=headers
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2
    assert history.json()["items"][0]["id"] == second.json()["id"]  # newest first
    assert history.json()["items"][0]["status"] == "ACTIVE"
    assert history.json()["items"][1]["status"] == "RETRACTED"


def test_governance_decision_creates_an_audit_record(client, db_session):
    from sqlalchemy import func, select

    from app.models.audit_log import AuditLog

    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem28@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])
    before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()

    response = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(), headers=headers,
    )
    assert response.status_code == 201

    after = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before + 1
    log_row = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ORGANIZATIONAL_MEMORY_GOVERNANCE_DECISION_RECORDED")
    ).scalar_one()
    assert log_row.resource_id == uuid.UUID(response.json()["id"])


def test_repeated_governance_decisions_are_not_deduplicated_by_natural_key(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem29@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])
    body = _governance_body()

    first = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}", json=body, headers=headers
    )
    second = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}", json=body, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_duplicate_idempotency_key_governance_request_does_not_duplicate(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem30@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])
    idem_headers = {**headers, "Idempotency-Key": "mem-gov-test-key-1"}
    body = _governance_body()

    first = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}", json=body, headers=idem_headers
    )
    second = client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}", json=body, headers=idem_headers
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


# --- Resolved organizational-memory state endpoint ------------------------------------------------


def test_memory_state_with_no_governance_yet(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem31@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])

    response = client.get(f"{_MEMORY_URL}/{memory['id']}/state", params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["current_governance"] is None  # implicit ACTIVE state


def test_memory_state_after_governance_decision(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem32@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])
    client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="RETRACTED"), headers=headers,
    )

    response = client.get(f"{_MEMORY_URL}/{memory['id']}/state", params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 200
    assert response.json()["current_governance"]["status"] == "RETRACTED"


def test_memory_state_requires_a_valid_id(client, db_session):
    org, _, headers, _decision, _outcome, _verification, _candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem33@example.com"
    )
    response = client.get(f"{_MEMORY_URL}/{uuid.uuid4()}/state", params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 404


# --- Point-in-time reads (as_of) -----------------------------------------------------------------


def test_as_of_excludes_memory_created_after_the_cutoff(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem34@example.com"
    )
    cutoff = datetime.now(timezone.utc)

    response = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    assert response.status_code == 201

    list_response = client.get(
        _MEMORY_URL, params={"organization_id": org["id"], "as_of": cutoff.isoformat()}, headers=headers
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_as_of_includes_memory_created_before_the_cutoff(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem35@example.com"
    )

    response = client.post(f"{_MEMORY_URL}?organization_id={org['id']}", json=_memory_body(candidate["id"]), headers=headers)
    assert response.status_code == 201

    future_cutoff = datetime.now(timezone.utc) + timedelta(days=1)
    list_response = client.get(
        _MEMORY_URL, params={"organization_id": org["id"], "as_of": future_cutoff.isoformat()}, headers=headers
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_governance_as_of_excludes_a_decision_recorded_after_the_cutoff(client, db_session):
    org, _, headers, _decision, _outcome, _verification, candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem36@example.com"
    )
    memory = _create_memory(client, org["id"], headers, candidate["id"])
    cutoff = datetime.now(timezone.utc)

    client.post(
        f"{_MEMORY_URL}/{memory['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="RETRACTED"), headers=headers,
    )

    response = client.get(
        f"{_MEMORY_URL}/{memory['id']}/state",
        params={"organization_id": org["id"], "as_of": cutoff.isoformat()}, headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["current_governance"] is None


# --- Read-only boundary -----------------------------------------------------------------------


def test_get_memory_list_never_writes(client, db_session):
    from sqlalchemy import func, select

    from app.models.organizational_memory import OrganizationalMemory

    org, _, headers, _decision, _outcome, _verification, _candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem37@example.com"
    )
    before = db_session.execute(select(func.count()).select_from(OrganizationalMemory)).scalar_one()

    response = client.get(_MEMORY_URL, params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 200

    after = db_session.execute(select(func.count()).select_from(OrganizationalMemory)).scalar_one()
    assert before == after == 0


# --- Explicit non-goals: no automatic memory creation / acceptance --------------------------------


def test_accepting_a_candidate_never_automatically_creates_a_memory(client, db_session):
    """§25/T -- ACCEPT on a learning candidate must never, by itself,
    produce an OrganizationalMemory row. Only an explicit
    POST /organizational-memory call creates one."""
    from sqlalchemy import func, select

    from app.models.organizational_memory import OrganizationalMemory

    org, _, headers, _decision, _outcome, _verification, _candidate = _setup_accepted_candidate(
        client, db_session, "manager-mem38@example.com"
    )
    count = db_session.execute(select(func.count()).select_from(OrganizationalMemory)).scalar_one()
    assert count == 0
