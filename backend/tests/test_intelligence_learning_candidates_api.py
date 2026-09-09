"""SIE Milestone 39: Learning Candidate Foundation — HTTP-layer tests
for `POST /api/v1/intelligence/learning-candidates`,
`GET /api/v1/intelligence/learning-candidates`,
`GET /api/v1/intelligence/learning-candidates/{candidate_id}`,
`POST /api/v1/intelligence/learning-candidates/{candidate_id}/governance-decisions`,
`GET /api/v1/intelligence/learning-candidates/{candidate_id}/governance-decisions`,
and `GET /api/v1/intelligence/learning-candidates/{candidate_id}/state`.
Mirrors `tests/test_intelligence_outcome_verifications_api.py`'s own
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


def _setup_verified_outcome(client, db_session, email):
    """A fully eligible outcome: valid evidence + a VERIFIED
    verification -- the one precondition for creating a learning
    candidate."""
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
    return org, user, headers, decision, outcome, verification


def _setup_unverified_outcome(client, db_session, email):
    org = create_org(client)
    user = make_user(db_session, email)
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    decision = _create_decision(client, org["id"], headers)
    outcome = _create_outcome(client, org["id"], headers, decision["id"])
    return org, user, headers, decision, outcome


_CANDIDATES_URL = "/api/v1/intelligence/learning-candidates"


def _candidate_body(outcome_id) -> dict:
    return {"outcome_id": outcome_id}


def _governance_body(**overrides) -> dict:
    body = {"status": "ACCEPTED", "rationale": "This experience is representative and worth learning from."}
    body.update(overrides)
    return body


# --- Authorization -----------------------------------------------------------------------------


def test_create_candidate_requires_authentication(client):
    response = client.post(
        f"{_CANDIDATES_URL}?organization_id={uuid.uuid4()}", json=_candidate_body(str(uuid.uuid4()))
    )
    assert response.status_code == 401


def test_create_candidate_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider-lc1@example.com")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"{_CANDIDATES_URL}?organization_id={org['id']}",
        json=_candidate_body(str(uuid.uuid4())), headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_create_candidate_requires_intelligence_decision_write_permission(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc-setup1@example.com"
    )
    viewer = make_user(db_session, "viewer-lc1@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"{_CANDIDATES_URL}?organization_id={org['id']}",
        json=_candidate_body(outcome["id"]), headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_hse_manager_can_create_a_candidate(client, db_session):
    org, user, headers, _decision, outcome, verification = _setup_verified_outcome(
        client, db_session, "manager-lc1@example.com"
    )

    response = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome_id"] == outcome["id"]
    assert body["verification_id"] == verification["id"]
    assert body["created_by_user_id"] == str(user.id)
    assert body["created_by_api_client_id"] is None


def test_machine_client_with_decision_write_scope_can_create_a_candidate(client, db_session):
    org, _, _headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc-setup2@example.com"
    )
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))

    response = client.post(
        f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=_bearer(credential)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_by_api_client_id"] == str(credential.api_client.id)
    assert body["created_by_user_id"] is None


def test_machine_client_without_write_scope_is_rejected(client, db_session):
    org, _, _headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc-setup3@example.com"
    )
    read_only = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])

    response = client.post(
        f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=_bearer(read_only)
    )
    assert response.status_code == 403


# --- Actor governance / cannot impersonate --------------------------------------------------------


def test_created_by_user_id_cannot_be_supplied_by_the_client(client, db_session):
    org, user, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc2@example.com"
    )
    impersonated_id = uuid.uuid4()
    body = _candidate_body(outcome["id"])
    body["created_by_user_id"] = str(impersonated_id)  # attempted impersonation; not a real field

    response = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["created_by_user_id"] == str(user.id)
    assert response.json()["created_by_user_id"] != str(impersonated_id)


# --- The eligibility gate (M39 spec §6) ---------------------------------------------------------


def test_candidate_creation_rejects_a_never_verified_outcome(client, db_session):
    org, _, headers, _decision, outcome = _setup_unverified_outcome(client, db_session, "manager-lc3@example.com")

    response = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    assert response.status_code == 422


def test_candidate_creation_rejects_insufficient_evidence_verification(client, db_session):
    org, _, headers, _decision, outcome = _setup_unverified_outcome(client, db_session, "manager-lc4@example.com")
    _create_verification(client, org["id"], headers, outcome["id"], status="INSUFFICIENT_EVIDENCE")

    response = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    assert response.status_code == 422


def test_candidate_creation_rejects_disputed_verification(client, db_session):
    org, _, headers, _decision, outcome = _setup_unverified_outcome(client, db_session, "manager-lc5@example.com")
    _create_verification(client, org["id"], headers, outcome["id"], status="DISPUTED")

    response = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    assert response.status_code == 422


def test_candidate_creation_requires_a_valid_outcome_id(client, db_session):
    org, _, headers, _decision, _outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc6@example.com"
    )

    response = client.post(
        f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(str(uuid.uuid4())), headers=headers
    )
    assert response.status_code == 404


def test_candidate_creation_rejects_a_cross_tenant_outcome(client, db_session):
    org_a, _, headers_a, _decision_a, outcome_a, _verification_a = _setup_verified_outcome(
        client, db_session, "manager-lc7a@example.com"
    )
    org_b = create_org(client, name="Org B lc")
    user_b = make_user(db_session, "manager-lc7b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    response = client.post(
        f"{_CANDIDATES_URL}?organization_id={org_b['id']}", json=_candidate_body(outcome_a["id"]), headers=headers_b
    )
    assert response.status_code == 404


# --- Idempotent by construction (M39 spec §15) ---------------------------------------------------


def test_repeat_candidate_creation_for_the_same_outcome_returns_the_existing_row(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc8@example.com"
    )

    first = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    second = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    list_response = client.get(_CANDIDATES_URL, params={"organization_id": org["id"]}, headers=headers)
    assert list_response.json()["total"] == 1


def test_duplicate_idempotency_key_request_does_not_create_a_duplicate_candidate(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc9@example.com"
    )
    idem_headers = {**headers, "Idempotency-Key": "lc-test-key-1"}

    first = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=idem_headers)
    second = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=idem_headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_same_idempotency_key_with_a_different_outcome_conflicts(client, db_session):
    org, _, headers, decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc10@example.com"
    )
    event2 = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome2 = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event2.id)])
    _create_verification(client, org["id"], headers, outcome2["id"])
    idem_headers = {**headers, "Idempotency-Key": "lc-test-key-2"}

    first = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=idem_headers)
    assert first.status_code == 201
    second = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome2["id"]), headers=idem_headers)
    assert second.status_code == 409


# --- Reads: list/get -------------------------------------------------------------------------------


def test_get_candidate_returns_composed_outcome_and_verification_context(client, db_session):
    org, _, headers, _decision, outcome, verification = _setup_verified_outcome(
        client, db_session, "manager-lc11@example.com"
    )
    created = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    candidate_id = created.json()["id"]

    response = client.get(f"{_CANDIDATES_URL}/{candidate_id}", params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"]["id"] == outcome["id"]
    assert body["outcome"]["classification"] == "EFFECTIVE"
    assert body["verification"]["id"] == verification["id"]
    assert body["verification"]["status"] == "VERIFIED"


def test_get_candidate_requires_a_valid_id(client, db_session):
    org, _, headers, _decision, _outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc12@example.com"
    )
    response = client.get(f"{_CANDIDATES_URL}/{uuid.uuid4()}", params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 404


def test_list_candidates_filters_by_outcome_id(client, db_session):
    org, _, headers, decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc13@example.com"
    )
    event2 = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome2 = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event2.id)])
    _create_verification(client, org["id"], headers, outcome2["id"])

    client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome2["id"]), headers=headers)

    response = client.get(_CANDIDATES_URL, params={"organization_id": org["id"], "outcome_id": outcome["id"]}, headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["outcome_id"] == outcome["id"]


# --- No PUT/PATCH/DELETE (immutability) ----------------------------------------------------------


def test_no_put_route_exists_for_candidates(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc14@example.com"
    )
    created = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    candidate_id = created.json()["id"]

    put_response = client.put(f"{_CANDIDATES_URL}/{candidate_id}?organization_id={org['id']}", json={}, headers=headers)
    assert put_response.status_code in (404, 405)


def test_no_delete_route_exists_for_candidates(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc15@example.com"
    )
    created = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    candidate_id = created.json()["id"]

    delete_response = client.delete(f"{_CANDIDATES_URL}/{candidate_id}?organization_id={org['id']}", headers=headers)
    assert delete_response.status_code in (404, 405)


# --- Auditability -----------------------------------------------------------------------------


def test_candidate_creation_creates_an_audit_record(client, db_session):
    from sqlalchemy import func, select

    from app.models.audit_log import AuditLog

    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc16@example.com"
    )
    before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()

    response = client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    assert response.status_code == 201

    after = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before + 1
    log_row = db_session.execute(
        select(AuditLog).where(AuditLog.action == "INTELLIGENCE_LEARNING_CANDIDATE_CREATED")
    ).scalar_one()
    assert log_row.resource_id == uuid.UUID(response.json()["id"])


def test_repeat_candidate_creation_does_not_duplicate_the_audit_record(client, db_session):
    """Only the genuinely first creation (`created=True`) is audited --
    mirrors `link_project_site()`'s own established precedent."""
    from sqlalchemy import func, select

    from app.models.audit_log import AuditLog

    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc17@example.com"
    )

    client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    client.post(f"{_CANDIDATES_URL}?organization_id={org['id']}", json=_candidate_body(outcome["id"]), headers=headers)
    after = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before


# --- Tenant isolation --------------------------------------------------------------------------


def test_cannot_read_another_organizations_candidates(client, db_session):
    org_a, _, headers_a, _decision_a, outcome_a, _verification_a = _setup_verified_outcome(
        client, db_session, "manager-lc18a@example.com"
    )
    org_b = create_org(client, name="Org B lc read")
    user_b = make_user(db_session, "manager-lc18b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    created = client.post(f"{_CANDIDATES_URL}?organization_id={org_a['id']}", json=_candidate_body(outcome_a["id"]), headers=headers_a)
    assert created.status_code == 201

    response = client.get(f"{_CANDIDATES_URL}/{created.json()['id']}", params={"organization_id": org_b["id"]}, headers=headers_b)
    assert response.status_code == 404


def test_machine_client_cannot_create_a_candidate_for_a_different_organization(client, db_session):
    """M38-corrective, reused verbatim here: a machine caller's own
    credential-bound organization is authoritative. `authorize_context()`
    itself already requires the query `organization_id` to equal the
    credential's own `machine_organization_id` before the route handler
    is ever reached (a first layer of defense) -- so a machine credential
    for org_b attempting to target org_a via the query parameter is
    rejected with 403 at the permission dependency, never reaching
    `resolve_authorized_organization_id()`'s own defense-in-depth
    substitution."""
    org_a, _, _headers_a, _decision_a, outcome_a, _verification_a = _setup_verified_outcome(
        client, db_session, "manager-lc19a@example.com"
    )
    org_b = create_org(client, name="Org B lc machine")
    credential_b = _make_client_credential(db_session, uuid.UUID(org_b["id"]))

    response = client.post(
        f"{_CANDIDATES_URL}?organization_id={org_a['id']}", json=_candidate_body(outcome_a["id"]), headers=_bearer(credential_b)
    )
    assert response.status_code == 403


# --- Governance decisions ------------------------------------------------------------------------


def _create_candidate(client, org_id, headers, outcome_id) -> dict:
    response = client.post(f"{_CANDIDATES_URL}?organization_id={org_id}", json=_candidate_body(outcome_id), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_hse_manager_can_accept_a_candidate(client, db_session):
    org, user, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc20@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])

    response = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="ACCEPTED"), headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["candidate_id"] == candidate["id"]
    assert body["status"] == "ACCEPTED"
    assert body["decided_by_user_id"] == str(user.id)


def test_hse_manager_can_reject_a_candidate(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc21@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])

    response = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="REJECTED", rationale="Not representative of typical operations."), headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "REJECTED"


def test_governance_decision_requires_intelligence_decision_write_permission(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc22@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    viewer = make_user(db_session, "viewer-lc22@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(), headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_governance_decision_requires_a_valid_candidate_id(client, db_session):
    org, _, headers, _decision, _outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc23@example.com"
    )

    response = client.post(
        f"{_CANDIDATES_URL}/{uuid.uuid4()}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(), headers=headers,
    )
    assert response.status_code == 404


def test_governance_decision_rejects_a_cross_tenant_candidate(client, db_session):
    org_a, _, headers_a, _decision_a, outcome_a, _verification_a = _setup_verified_outcome(
        client, db_session, "manager-lc24a@example.com"
    )
    candidate_a = _create_candidate(client, org_a["id"], headers_a, outcome_a["id"])
    org_b = create_org(client, name="Org B lc gov")
    user_b = make_user(db_session, "manager-lc24b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    response = client.post(
        f"{_CANDIDATES_URL}/{candidate_a['id']}/governance-decisions?organization_id={org_b['id']}",
        json=_governance_body(), headers=headers_b,
    )
    assert response.status_code == 404


def test_rationale_is_required_for_a_governance_decision(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc25@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])

    response = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(rationale=""), headers=headers,
    )
    assert response.status_code == 422


def test_a_second_governance_decision_is_a_new_row_not_an_overwrite(client, db_session):
    """§10: a reviewer changing their mind is a second row referencing
    the same candidate_id, ordered newest-first; the first row is never
    destroyed."""
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc26@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])

    first = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="REJECTED", rationale="First pass -- not representative."), headers=headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="ACCEPTED", rationale="Reconsidered -- worth keeping."), headers=headers,
    )
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    history = client.get(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions", params={"organization_id": org["id"]}, headers=headers
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2
    assert history.json()["items"][0]["id"] == second.json()["id"]  # newest first
    assert history.json()["items"][0]["status"] == "ACCEPTED"
    assert history.json()["items"][1]["status"] == "REJECTED"


def test_governance_decision_creates_an_audit_record(client, db_session):
    from sqlalchemy import func, select

    from app.models.audit_log import AuditLog

    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc27@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()

    response = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(), headers=headers,
    )
    assert response.status_code == 201

    after = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before + 1
    log_row = db_session.execute(
        select(AuditLog).where(AuditLog.action == "INTELLIGENCE_LEARNING_CANDIDATE_GOVERNANCE_DECISION_RECORDED")
    ).scalar_one()
    assert log_row.resource_id == uuid.UUID(response.json()["id"])


def test_repeated_governance_decisions_are_not_deduplicated_by_natural_key(client, db_session):
    """Unlike candidate creation, governance decisions are NOT
    idempotent by a natural key -- each call (even with an identical
    body, no Idempotency-Key) creates a new row, preserving the full
    decision history."""
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc28@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    body = _governance_body()

    first = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}", json=body, headers=headers
    )
    second = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}", json=body, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_duplicate_idempotency_key_governance_request_does_not_duplicate(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc29@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    idem_headers = {**headers, "Idempotency-Key": "lc-gov-test-key-1"}
    body = _governance_body()

    first = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}", json=body, headers=idem_headers
    )
    second = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}", json=body, headers=idem_headers
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


# --- Resolved learning-candidate state endpoint ---------------------------------------------------


def test_candidate_state_with_no_governance_yet(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc30@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])

    response = client.get(
        f"{_CANDIDATES_URL}/{candidate['id']}/state", params={"organization_id": org["id"]}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_governance"] is None  # "pending" -- distinct initial state
    assert body["current_evidence_evaluation"]["evidence_status"] == "VALID_EVIDENCE"


def test_candidate_state_after_governance_decision(client, db_session):
    org, _, headers, _decision, outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc31@example.com"
    )
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/governance-decisions?organization_id={org['id']}",
        json=_governance_body(status="ACCEPTED"), headers=headers,
    )

    response = client.get(
        f"{_CANDIDATES_URL}/{candidate['id']}/state", params={"organization_id": org["id"]}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_governance"]["status"] == "ACCEPTED"


def test_candidate_state_requires_a_valid_id(client, db_session):
    org, _, headers, _decision, _outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc32@example.com"
    )
    response = client.get(f"{_CANDIDATES_URL}/{uuid.uuid4()}/state", params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 404


# --- Read-only boundary -----------------------------------------------------------------------


def test_get_candidates_never_writes(client, db_session):
    from sqlalchemy import func, select

    from app.models.intelligence_learning_candidate import IntelligenceLearningCandidate

    org, _, headers, _decision, _outcome, _verification = _setup_verified_outcome(
        client, db_session, "manager-lc33@example.com"
    )
    before = db_session.execute(select(func.count()).select_from(IntelligenceLearningCandidate)).scalar_one()

    response = client.get(_CANDIDATES_URL, params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []

    after = db_session.execute(select(func.count()).select_from(IntelligenceLearningCandidate)).scalar_one()
    assert before == after == 0
