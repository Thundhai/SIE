"""SIE Milestone 38: Outcome Verification & Evidence — HTTP-layer tests
for `POST /api/v1/intelligence/outcomes/{outcome_id}/verifications`,
`GET /api/v1/intelligence/outcomes/{outcome_id}/verifications`, and
`GET /api/v1/intelligence/outcomes/{outcome_id}/verification-state`.
Mirrors `tests/test_intelligence_outcomes_api.py`'s own established
shape: runs against the ordinary SQLite `client` fixture.
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


def _verification_body(**overrides):
    body = {
        "status": "INSUFFICIENT_EVIDENCE",
        "rationale": "No supporting evidence was supplied.",
        "verified_at": AS_OF.isoformat(),
    }
    body.update(overrides)
    return body


def _setup_outcome(client, db_session, email, **outcome_overrides):
    org = create_org(client)
    user = make_user(db_session, email)
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    decision = _create_decision(client, org["id"], headers)
    outcome = _create_outcome(client, org["id"], headers, decision["id"], **outcome_overrides)
    return org, user, headers, decision, outcome


def _make_evidence_event(db_session, org_id, **overrides):
    kwargs = dict(event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    kwargs.update(overrides)
    event = make_safety_event(organization_id=org_id, source_record_id=str(uuid.uuid4()), **kwargs)
    db_session.add(event)
    db_session.commit()
    return event


_VERIFICATIONS_URL = "/api/v1/intelligence/outcomes/{outcome_id}/verifications"
_STATE_URL = "/api/v1/intelligence/outcomes/{outcome_id}/verification-state"


# --- _authorized_organization_id: server-derived tenant for the M38 surface --------------------
#
# Corrective hardening: the three M38 verification endpoints resolve
# their operative organization_id through this helper rather than using
# the raw query parameter directly. For a machine caller, the
# credential-bound app.api.deps_context.RequestContext.
# machine_organization_id always wins, even over a (hypothetically
# mismatched) query value -- defense in depth beyond what
# require_context_permission()'s own authorize_context() already
# guarantees before any of these three handlers is ever reached. For a
# human caller, RequestContext carries no organization id of its own (a
# human may hold membership in more than one organization), so the
# already-authorized query parameter remains the only available source
# -- identical to every other endpoint in this codebase, M37's own
# outcomes/decisions endpoints included, deliberately left unchanged.


def test_authorized_organization_id_prefers_machine_context_over_the_query_value(db_session):
    from app.api.deps_context import RequestContext
    from app.api.v1.intelligence_outcomes import _authorized_organization_id

    machine_org = uuid.uuid4()
    mismatched_query_org = uuid.uuid4()
    context = RequestContext(
        kind="machine", api_client_id=uuid.uuid4(), client_id="test-client", machine_organization_id=machine_org
    )

    # Even a query value that does not match the credential's own
    # organization never wins for a machine caller.
    assert _authorized_organization_id(context, mismatched_query_org) == machine_org
    assert _authorized_organization_id(context, machine_org) == machine_org


def test_authorized_organization_id_uses_the_query_value_for_human_callers(db_session):
    from app.api.deps_context import RequestContext
    from app.api.v1.intelligence_outcomes import _authorized_organization_id

    org_id = uuid.uuid4()
    context = RequestContext(kind="human", user_id=uuid.uuid4())

    assert _authorized_organization_id(context, org_id) == org_id


# --- Authorization ---------------------------------------------------------------------------


def test_create_verification_requires_authentication(client):
    response = client.post(
        f"/api/v1/intelligence/outcomes/{uuid.uuid4()}/verifications?organization_id={uuid.uuid4()}",
        json=_verification_body(),
    )
    assert response.status_code == 401


def test_create_verification_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider-verify1@example.com")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"/api/v1/intelligence/outcomes/{uuid.uuid4()}/verifications?organization_id={org['id']}",
        json=_verification_body(),
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_create_verification_requires_intelligence_decision_write_permission(client, db_session):
    """A VIEWER (INTELLIGENCE_READ only) must be rejected -- verification
    reuses the M34 decision-write permission, not INTELLIGENCE_READ."""
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify-setup1@example.com")
    viewer = make_user(db_session, "viewer-verify1@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(),
        headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_hse_manager_can_create_a_verification(client, db_session):
    org, user, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify1@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE"
    assert body["outcome_id"] == outcome["id"]
    assert body["verified_by_user_id"] == str(user.id)
    assert body["verified_by_api_client_id"] is None


def test_machine_client_with_decision_write_scope_can_create_a_verification(client, db_session):
    org, _, _headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify-setup2@example.com")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(),
        headers=_bearer(credential),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verified_by_api_client_id"] == str(credential.api_client.id)
    assert body["verified_by_user_id"] is None


def test_machine_client_without_write_scope_is_rejected(client, db_session):
    org, _, _headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify-setup3@example.com")
    read_only_credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(),
        headers=_bearer(read_only_credential),
    )
    assert response.status_code == 403


# --- Actor governance / cannot impersonate ------------------------------------------------------


def test_verified_by_user_id_cannot_be_supplied_by_the_client(client, db_session):
    org, user, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify2@example.com")
    impersonated_id = uuid.uuid4()

    body = _verification_body()
    body["verified_by_user_id"] = str(impersonated_id)  # attempted impersonation; not a real field
    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=body, headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["verified_by_user_id"] == str(user.id)
    assert response.json()["verified_by_user_id"] != str(impersonated_id)


# --- Outcome relationship (required, tenant-hardened) --------------------------------------------


def test_verification_requires_a_valid_outcome_id(client, db_session):
    org, _, headers, _decision, _outcome = _setup_outcome(client, db_session, "manager-verify3@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=uuid.uuid4()) + f"?organization_id={org['id']}",
        json=_verification_body(), headers=headers,
    )
    assert response.status_code == 404


def test_verification_rejects_a_cross_tenant_outcome(client, db_session):
    org_a, _, headers_a, _decision_a, outcome_a = _setup_outcome(client, db_session, "manager-verify4a@example.com")
    org_b = create_org(client, name="Org B verify")
    user_b = make_user(db_session, "manager-verify4b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome_a["id"]) + f"?organization_id={org_b['id']}",
        json=_verification_body(), headers=headers_b,
    )
    assert response.status_code == 404


# --- "VALID EVIDENCE != VERIFIED OUTCOME" (M38 spec §8-9) ---------------------------------------


def test_verified_status_rejected_when_outcome_has_no_evidence(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify5@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="VERIFIED"), headers=headers,
    )
    assert response.status_code == 422


def test_verified_status_rejected_when_evidence_is_invalid(client, db_session):
    """M37's own write path only checks that a supplied evidence id
    *exists* in this organization (`validate_source_event_reference()`)
    -- it does not check temporal validity. A future-dated evidence
    event is therefore accepted at outcome-creation time, and M38 must
    still reject `VERIFIED` against it at verification time."""
    org, _, headers, decision, _outcome = _setup_outcome(client, db_session, "manager-verify5b@example.com")
    future_event = _make_evidence_event(
        db_session, uuid.UUID(org["id"]), event_time=AS_OF + timedelta(days=5), ingestion_time=AS_OF + timedelta(days=5)
    )
    outcome_bad_evidence = _create_outcome(
        client, org["id"], headers, decision["id"], evidence_event_ids=[str(future_event.id)]
    )

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome_bad_evidence["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="VERIFIED"), headers=headers,
    )
    assert response.status_code == 422


def test_verified_status_accepted_when_evidence_is_valid(client, db_session):
    org, _, headers, decision, _outcome = _setup_outcome(client, db_session, "manager-verify6@example.com")
    event = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome_with_evidence = _create_outcome(
        client, org["id"], headers, decision["id"], evidence_event_ids=[str(event.id)]
    )

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome_with_evidence["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="VERIFIED", rationale="Evidence confirmed on-site."), headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "VERIFIED"


def test_insufficient_evidence_status_never_requires_valid_evidence(client, db_session):
    """A human may record INSUFFICIENT_EVIDENCE regardless of what the
    evidence evaluation says -- the evidence gate applies only to
    VERIFIED."""
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify7@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="INSUFFICIENT_EVIDENCE"), headers=headers,
    )
    assert response.status_code == 201, response.text


def test_disputed_status_never_requires_valid_evidence(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify8@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="DISPUTED", rationale="Second reviewer disagrees."), headers=headers,
    )
    assert response.status_code == 201, response.text


# --- Validation -----------------------------------------------------------------------------


def test_rationale_is_required(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify9@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(rationale=""), headers=headers,
    )
    assert response.status_code == 422


def test_future_verified_at_is_rejected(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify10@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(verified_at=(AS_OF + timedelta(days=1)).isoformat()), headers=headers,
    )
    assert response.status_code == 422


def test_backdated_verified_at_is_accepted(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify11@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(verified_at=(AS_OF - timedelta(days=10)).isoformat()), headers=headers,
    )
    assert response.status_code == 201, response.text


# --- No PUT/PATCH/DELETE (immutability) -------------------------------------------------------


def test_no_put_route_exists_for_verifications(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify12@example.com")
    created = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(), headers=headers,
    )
    verification_id = created.json()["id"]

    put_response = client.put(
        f"/api/v1/intelligence/outcomes/{outcome['id']}/verifications/{verification_id}?organization_id={org['id']}",
        json=_verification_body(status="DISPUTED"), headers=headers,
    )
    assert put_response.status_code in (404, 405)


def test_no_patch_route_exists_for_verifications(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify13@example.com")
    created = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(), headers=headers,
    )
    verification_id = created.json()["id"]

    patch_response = client.patch(
        f"/api/v1/intelligence/outcomes/{outcome['id']}/verifications/{verification_id}?organization_id={org['id']}",
        json={"status": "DISPUTED"}, headers=headers,
    )
    assert patch_response.status_code in (404, 405)


def test_no_delete_route_exists_for_verifications(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify14@example.com")
    created = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(), headers=headers,
    )
    verification_id = created.json()["id"]

    delete_response = client.delete(
        f"/api/v1/intelligence/outcomes/{outcome['id']}/verifications/{verification_id}?organization_id={org['id']}",
        headers=headers,
    )
    assert delete_response.status_code in (404, 405)


def test_a_second_verification_is_a_new_row_not_an_overwrite(client, db_session):
    """§4: a correction is a second row referencing the same outcome_id,
    ordered newest-first; the first row is never destroyed."""
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify15@example.com")

    first = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="INSUFFICIENT_EVIDENCE"), headers=headers,
    )
    assert first.status_code == 201
    second = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="DISPUTED", rationale="Second reviewer disagrees."), headers=headers,
    )
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    history = client.get(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]), params={"organization_id": org["id"]}, headers=headers
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2
    returned_ids = {v["id"] for v in history.json()["items"]}
    assert returned_ids == {first.json()["id"], second.json()["id"]}
    assert history.json()["items"][0]["id"] == second.json()["id"]  # newest first
    assert history.json()["items"][0]["status"] == "DISPUTED"
    assert history.json()["items"][1]["status"] == "INSUFFICIENT_EVIDENCE"


# --- Idempotency ---------------------------------------------------------------------------------


def test_duplicate_idempotent_request_does_not_create_a_duplicate_verification(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify16@example.com")
    idem_headers = {**headers, "Idempotency-Key": "verify-test-key-1"}
    body = _verification_body()

    first = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=body, headers=idem_headers,
    )
    second = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=body, headers=idem_headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    list_response = client.get(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]), params={"organization_id": org["id"]}, headers=headers
    )
    assert list_response.json()["total"] == 1


def test_same_idempotency_key_with_a_different_body_conflicts(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify17@example.com")
    idem_headers = {**headers, "Idempotency-Key": "verify-test-key-2"}

    first = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="INSUFFICIENT_EVIDENCE"), headers=idem_headers,
    )
    assert first.status_code == 201
    second = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="DISPUTED", rationale="A genuinely different request."), headers=idem_headers,
    )
    assert second.status_code == 409


# --- Auditability -----------------------------------------------------------------------------


def test_verification_creates_an_audit_record(client, db_session):
    from sqlalchemy import func, select

    from app.models.audit_log import AuditLog

    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify18@example.com")
    before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(), headers=headers,
    )
    assert response.status_code == 201

    after = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before + 1
    log_row = db_session.execute(
        select(AuditLog).where(AuditLog.action == "INTELLIGENCE_OUTCOME_VERIFICATION_RECORDED")
    ).scalar_one()
    assert log_row.resource_id == uuid.UUID(response.json()["id"])


# --- Tenant isolation --------------------------------------------------------------------------


def test_cannot_read_another_organizations_verifications(client, db_session):
    org_a, _, headers_a, _decision_a, outcome_a = _setup_outcome(client, db_session, "manager-verify19a@example.com")
    org_b = create_org(client, name="Org B verifications")
    user_b = make_user(db_session, "manager-verify19b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)

    created = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome_a["id"]) + f"?organization_id={org_a['id']}",
        json=_verification_body(), headers=headers_a,
    )
    assert created.status_code == 201

    list_response = client.get(
        _VERIFICATIONS_URL.format(outcome_id=outcome_a["id"]), params={"organization_id": org_b["id"]},
        headers=headers_b,
    )
    assert list_response.status_code == 404  # outcome itself does not resolve in Org B


# --- Point-in-time reads (as_of) -----------------------------------------------------------------


def test_as_of_excludes_verifications_recorded_after_the_cutoff(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify20@example.com")
    cutoff = datetime.now(timezone.utc)

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(), headers=headers,
    )
    assert response.status_code == 201

    list_response = client.get(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]),
        params={"organization_id": org["id"], "as_of": cutoff.isoformat()}, headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_as_of_includes_verifications_recorded_before_the_cutoff(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify21@example.com")

    response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(), headers=headers,
    )
    assert response.status_code == 201

    future_cutoff = datetime.now(timezone.utc) + timedelta(days=1)
    list_response = client.get(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]),
        params={"organization_id": org["id"], "as_of": future_cutoff.isoformat()}, headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


# --- Resolved verification-state endpoint --------------------------------------------------------


def test_verification_state_with_no_verification_yet(client, db_session):
    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify22@example.com")

    response = client.get(
        _STATE_URL.format(outcome_id=outcome["id"]), params={"organization_id": org["id"]}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_verification"] is None
    assert body["evidence_evaluation"]["evidence_status"] == "NO_EVIDENCE"
    assert body["learning_eligibility"]["eligible"] is False


def test_verification_state_after_verified_with_valid_evidence(client, db_session):
    org, _, headers, decision, _outcome = _setup_outcome(client, db_session, "manager-verify23@example.com")
    event = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event.id)])

    verify_response = client.post(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]) + f"?organization_id={org['id']}",
        json=_verification_body(status="VERIFIED", rationale="Confirmed on-site."), headers=headers,
    )
    assert verify_response.status_code == 201

    response = client.get(
        _STATE_URL.format(outcome_id=outcome["id"]), params={"organization_id": org["id"]}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_verification"]["status"] == "VERIFIED"
    assert body["evidence_evaluation"]["evidence_status"] == "VALID_EVIDENCE"
    assert body["evidence_evaluation"]["evidence_eligible_for_verification"] is True
    assert body["learning_eligibility"]["eligible"] is True


def test_verification_state_requires_a_valid_outcome_id(client, db_session):
    org, _, headers, _decision, _outcome = _setup_outcome(client, db_session, "manager-verify24@example.com")

    response = client.get(
        _STATE_URL.format(outcome_id=uuid.uuid4()), params={"organization_id": org["id"]}, headers=headers
    )
    assert response.status_code == 404


# --- Read-only boundary -----------------------------------------------------------------------


def test_get_verifications_never_writes(client, db_session):
    from sqlalchemy import func, select

    from app.models.intelligence_outcome_verification import IntelligenceOutcomeVerification

    org, _, headers, _decision, outcome = _setup_outcome(client, db_session, "manager-verify25@example.com")
    before = db_session.execute(select(func.count()).select_from(IntelligenceOutcomeVerification)).scalar_one()

    response = client.get(
        _VERIFICATIONS_URL.format(outcome_id=outcome["id"]), params={"organization_id": org["id"]}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["items"] == []

    state_response = client.get(
        _STATE_URL.format(outcome_id=outcome["id"]), params={"organization_id": org["id"]}, headers=headers
    )
    assert state_response.status_code == 200

    after = db_session.execute(select(func.count()).select_from(IntelligenceOutcomeVerification)).scalar_one()
    assert before == after == 0
