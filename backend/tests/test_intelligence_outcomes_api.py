"""SIE Milestone 37: Field Outcome Foundation — HTTP-layer tests for
`POST /api/v1/intelligence/outcomes`, `GET /api/v1/intelligence/outcomes`,
and `GET /api/v1/intelligence/outcomes/{outcome_id}`. Mirrors
`tests/test_intelligence_decisions_api.py`'s own established shape: runs
against the ordinary SQLite `client` fixture.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.safety_action import SafetyAction
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site, seed_risk_area_ontology_concepts
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


def _outcome_body(decision_id, **overrides):
    body = {
        "decision_id": decision_id,
        "classification": "EFFECTIVE",
        "summary": "Follow-up observation confirmed the hazard was corrected.",
        "outcome_at": AS_OF.isoformat(),
    }
    body.update(overrides)
    return body


def _setup_manager(client, db_session, email):
    org = create_org(client)
    user = make_user(db_session, email)
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    decision = _create_decision(client, org["id"], headers)
    return org, user, headers, decision


# --- Authorization ---------------------------------------------------------------------------


def test_create_outcome_requires_authentication(client):
    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={uuid.uuid4()}",
        json=_outcome_body(str(uuid.uuid4())),
    )
    assert response.status_code == 401


def test_create_outcome_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider2@example.com")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(str(uuid.uuid4())),
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_create_outcome_requires_intelligence_decision_write_permission(client, db_session):
    """A VIEWER (INTELLIGENCE_READ only) must be rejected -- outcomes
    reuse the M34 decision-write permission, not INTELLIGENCE_READ."""
    org, _, headers, decision = _setup_manager(client, db_session, "manager-setup1@example.com")
    viewer = make_user(db_session, "viewer2@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"]),
        headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_hse_manager_can_create_an_outcome(client, db_session):
    org, user, headers, decision = _setup_manager(client, db_session, "manager-outcome1@example.com")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"]),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["classification"] == "EFFECTIVE"
    assert body["decision_id"] == decision["id"]
    assert body["recorded_by_user_id"] == str(user.id)
    assert body["recorded_by_api_client_id"] is None


def test_machine_client_with_decision_write_scope_can_create_an_outcome(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-setup2@example.com")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"]),
        headers=_bearer(credential),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recorded_by_api_client_id"] == str(credential.api_client.id)
    assert body["recorded_by_user_id"] is None


def test_machine_client_without_write_scope_is_rejected(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-setup3@example.com")
    read_only_credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"]),
        headers=_bearer(read_only_credential),
    )
    assert response.status_code == 403


# --- Actor governance / cannot impersonate ------------------------------------------------------


def test_recorded_by_user_id_cannot_be_supplied_by_the_client(client, db_session):
    org, user, headers, decision = _setup_manager(client, db_session, "manager-outcome2@example.com")
    impersonated_id = uuid.uuid4()

    body = _outcome_body(decision["id"])
    body["recorded_by_user_id"] = str(impersonated_id)  # attempted impersonation; not a real field
    response = client.post(f"/api/v1/intelligence/outcomes?organization_id={org['id']}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["recorded_by_user_id"] == str(user.id)
    assert response.json()["recorded_by_user_id"] != str(impersonated_id)


# --- Decision relationship (required, tenant-hardened) ------------------------------------------


def test_outcome_requires_a_valid_decision_id(client, db_session):
    org, _, headers, _decision = _setup_manager(client, db_session, "manager-outcome3@example.com")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(str(uuid.uuid4())),
        headers=headers,
    )
    assert response.status_code == 404


def test_outcome_rejects_a_cross_tenant_decision(client, db_session):
    org_a, _, headers_a, decision_a = _setup_manager(client, db_session, "manager-outcome4a@example.com")
    org_b = create_org(client, name="Org B")
    user_b = make_user(db_session, "manager-outcome4b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    # Org B attempts to record an outcome against Org A's decision.
    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org_b['id']}",
        json=_outcome_body(decision_a["id"]),
        headers=headers_b,
    )
    assert response.status_code == 404


# --- Action relationship (optional, never forced) -----------------------------------------------


def test_outcome_can_reference_an_existing_same_tenant_action(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome5@example.com")
    action = SafetyAction(
        organization_id=uuid.UUID(org["id"]), title="Corrective action", action_type="CORRECTIVE",
        priority="HIGH", status="OPEN", attributes={},
    )
    db_session.add(action)
    db_session.commit()

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], linked_action_id=str(action.id)),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["linked_action_id"] == str(action.id)
    assert result["linked_action"]["title"] == "Corrective action"


def test_outcome_rejects_a_cross_tenant_action(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome6@example.com")
    org_b = create_org(client, name="Org B outcome")
    other_org_action = SafetyAction(
        organization_id=uuid.UUID(org_b["id"]), title="Org B's action", action_type="CORRECTIVE", priority="HIGH",
        status="OPEN", attributes={},
    )
    db_session.add(other_org_action)
    db_session.commit()

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], linked_action_id=str(other_org_action.id)),
        headers=headers,
    )
    assert response.status_code == 404


def test_outcome_without_a_linked_action_is_legitimate(client, db_session):
    """§5 -- Decision -> Outcome with no SafetyAction is a first-class
    case, never forced through the action model."""
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome7@example.com")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"]),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["linked_action_id"] is None
    assert response.json()["linked_action"] is None


# --- Site relationship (optional, independently supplied) ---------------------------------------


def test_outcome_can_supply_a_site_independently_of_the_decision(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome8@example.com")
    site = make_site(db_session, uuid.UUID(org["id"]), name="Follow-up Site")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], site_id=str(site.id)),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["site_id"] == str(site.id)
    assert result["site_label"] == "Follow-up Site"


def test_outcome_rejects_a_cross_tenant_site(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome9@example.com")
    org_b = create_org(client, name="Org B site")
    site_b = make_site(db_session, uuid.UUID(org_b["id"]), name="Org B's Site")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], site_id=str(site_b.id)),
        headers=headers,
    )
    assert response.status_code == 404


# --- Evidence -----------------------------------------------------------------------------------


def test_outcome_evidence_event_ids_must_belong_to_the_organization(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome10@example.com")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], evidence_event_ids=[str(uuid.uuid4())]),
        headers=headers,
    )
    assert response.status_code == 404


def test_outcome_evidence_event_ids_round_trip(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome11@example.com")
    event = make_safety_event(
        organization_id=uuid.UUID(org["id"]), event_type="INCIDENT", event_time=AS_OF, ingestion_time=AS_OF,
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(event)
    db_session.commit()

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], evidence_event_ids=[str(event.id)]),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["evidence_event_ids"] == [str(event.id)]


# --- Validation -----------------------------------------------------------------------------


def test_summary_is_required(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome12@example.com")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], summary=""),
        headers=headers,
    )
    assert response.status_code == 422


def test_every_classification_value_is_accepted(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome13@example.com")

    for classification in ("EFFECTIVE", "PARTIALLY_EFFECTIVE", "INEFFECTIVE", "NO_OUTCOME_RECORDED"):
        response = client.post(
            f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
            json=_outcome_body(decision["id"], classification=classification, summary=f"Testing {classification}."),
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["classification"] == classification


def test_future_outcome_at_is_rejected(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome14@example.com")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], outcome_at=(AS_OF + timedelta(days=1)).isoformat()),
        headers=headers,
    )
    assert response.status_code == 422


def test_backdated_outcome_at_is_accepted(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome15@example.com")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], outcome_at=(AS_OF - timedelta(days=60)).isoformat()),
        headers=headers,
    )
    assert response.status_code == 201, response.text


# --- No PUT/PATCH/DELETE (immutability) -------------------------------------------------------


def test_no_put_route_exists_for_outcomes(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome16@example.com")
    created = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}", json=_outcome_body(decision["id"]), headers=headers
    )
    outcome_id = created.json()["id"]

    put_response = client.put(
        f"/api/v1/intelligence/outcomes/{outcome_id}?organization_id={org['id']}",
        json=_outcome_body(decision["id"], classification="INEFFECTIVE"),
        headers=headers,
    )
    assert put_response.status_code in (404, 405)


def test_no_patch_route_exists_for_outcomes(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome17@example.com")
    created = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}", json=_outcome_body(decision["id"]), headers=headers
    )
    outcome_id = created.json()["id"]

    patch_response = client.patch(
        f"/api/v1/intelligence/outcomes/{outcome_id}?organization_id={org['id']}",
        json={"classification": "INEFFECTIVE"},
        headers=headers,
    )
    assert patch_response.status_code in (404, 405)


def test_no_delete_route_exists_for_outcomes(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome18@example.com")
    created = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}", json=_outcome_body(decision["id"]), headers=headers
    )
    outcome_id = created.json()["id"]

    delete_response = client.delete(
        f"/api/v1/intelligence/outcomes/{outcome_id}?organization_id={org['id']}", headers=headers
    )
    assert delete_response.status_code in (404, 405)


def test_a_second_outcome_on_the_same_decision_is_a_new_row_not_an_overwrite(client, db_session):
    """§6 -- a correction is a second row referencing the same
    decision_id, ordered newest-first; the first row is never
    destroyed."""
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome19@example.com")

    first = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], classification="INEFFECTIVE", outcome_at=(AS_OF - timedelta(days=3)).isoformat()),
        headers=headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(
            decision["id"], classification="EFFECTIVE", summary="Day-30 follow-up confirms effective.",
            outcome_at=AS_OF.isoformat(),
        ),
        headers=headers,
    )
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    history = client.get(
        "/api/v1/intelligence/outcomes", params={"organization_id": org["id"], "decision_id": decision["id"]},
        headers=headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2
    returned_ids = {o["id"] for o in history.json()["items"]}
    assert returned_ids == {first.json()["id"], second.json()["id"]}
    # Newest first, by outcome_at.
    assert history.json()["items"][0]["id"] == second.json()["id"]
    assert history.json()["items"][0]["classification"] == "EFFECTIVE"
    assert history.json()["items"][1]["classification"] == "INEFFECTIVE"


# --- Idempotency ---------------------------------------------------------------------------------


def test_duplicate_idempotent_request_does_not_create_a_duplicate_outcome(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome20@example.com")
    idem_headers = {**headers, "Idempotency-Key": "outcome-test-key-1"}
    body = _outcome_body(decision["id"])

    first = client.post(f"/api/v1/intelligence/outcomes?organization_id={org['id']}", json=body, headers=idem_headers)
    second = client.post(f"/api/v1/intelligence/outcomes?organization_id={org['id']}", json=body, headers=idem_headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    list_response = client.get(
        "/api/v1/intelligence/outcomes", params={"organization_id": org["id"], "decision_id": decision["id"]},
        headers=headers,
    )
    assert list_response.json()["total"] == 1


def test_same_idempotency_key_with_a_different_body_conflicts(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome21@example.com")
    idem_headers = {**headers, "Idempotency-Key": "outcome-test-key-2"}

    first = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], classification="INEFFECTIVE"), headers=idem_headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], classification="EFFECTIVE", summary="A genuinely different request."),
        headers=idem_headers,
    )
    assert second.status_code == 409


# --- Tenant isolation --------------------------------------------------------------------------


def test_cannot_read_another_organizations_outcomes(client, db_session):
    org_a, _, headers_a, decision_a = _setup_manager(client, db_session, "manager-outcome22a@example.com")
    org_b = create_org(client, name="Org B outcomes")
    user_b = make_user(db_session, "manager-outcome22b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)

    created = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org_a['id']}", json=_outcome_body(decision_a["id"]),
        headers=headers_a,
    )
    assert created.status_code == 201
    outcome_id = created.json()["id"]

    get_response = client.get(f"/api/v1/intelligence/outcomes/{outcome_id}?organization_id={org_b['id']}", headers=headers_b)
    assert get_response.status_code == 404

    list_response = client.get(f"/api/v1/intelligence/outcomes?organization_id={org_b['id']}", headers=headers_b)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


# --- Point-in-time reads (as_of) -----------------------------------------------------------------


def test_as_of_excludes_outcomes_reported_after_the_cutoff(client, db_session):
    """Even though `outcome_at` predates the cutoff, a row *reported*
    (created) after `as_of` must not leak into a historical
    reconstruction as of that earlier instant -- mirrors
    `events_as_of()`'s own dual-timestamp discipline."""
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome23@example.com")
    cutoff = AS_OF - timedelta(minutes=1)

    # outcome_at predates the cutoff, but created_at (now) does not.
    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], outcome_at=(cutoff - timedelta(days=1)).isoformat()),
        headers=headers,
    )
    assert response.status_code == 201, response.text

    list_response = client.get(
        "/api/v1/intelligence/outcomes",
        params={"organization_id": org["id"], "decision_id": decision["id"], "as_of": cutoff.isoformat()},
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_as_of_includes_outcomes_reported_before_the_cutoff(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome24@example.com")

    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], outcome_at=(AS_OF - timedelta(days=5)).isoformat()),
        headers=headers,
    )
    assert response.status_code == 201, response.text

    future_cutoff = AS_OF + timedelta(days=1)
    list_response = client.get(
        "/api/v1/intelligence/outcomes",
        params={"organization_id": org["id"], "decision_id": decision["id"], "as_of": future_cutoff.isoformat()},
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_omitting_as_of_returns_the_current_unfiltered_view(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome25@example.com")
    response = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}", json=_outcome_body(decision["id"]), headers=headers
    )
    assert response.status_code == 201

    list_response = client.get(
        "/api/v1/intelligence/outcomes", params={"organization_id": org["id"], "decision_id": decision["id"]},
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


# --- Filters --------------------------------------------------------------------------------


def test_list_filters_by_classification(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome26@example.com")
    client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], classification="EFFECTIVE"), headers=headers,
    )
    client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], classification="INEFFECTIVE", outcome_at=(AS_OF - timedelta(days=1)).isoformat()),
        headers=headers,
    )

    response = client.get(
        "/api/v1/intelligence/outcomes",
        params={"organization_id": org["id"], "classification": "EFFECTIVE"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["classification"] == "EFFECTIVE"


def test_list_filters_by_linked_action_id(client, db_session):
    org, _, headers, decision = _setup_manager(client, db_session, "manager-outcome27@example.com")
    action = SafetyAction(
        organization_id=uuid.UUID(org["id"]), title="Reverse-lookup action", action_type="CORRECTIVE",
        priority="HIGH", status="OPEN", attributes={},
    )
    db_session.add(action)
    db_session.commit()

    created = client.post(
        f"/api/v1/intelligence/outcomes?organization_id={org['id']}",
        json=_outcome_body(decision["id"], linked_action_id=str(action.id)), headers=headers,
    )
    assert created.status_code == 201

    response = client.get(
        "/api/v1/intelligence/outcomes",
        params={"organization_id": org["id"], "linked_action_id": str(action.id)},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == created.json()["id"]


# --- Read-only boundary (decisions/attention/context unaffected) --------------------------------


def test_get_outcomes_never_writes(client, db_session):
    from sqlalchemy import func, select

    from app.models.intelligence_outcome import IntelligenceOutcome

    org = create_org(client)
    user = make_user(db_session, "manager-outcome28@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers = dev_auth_headers(user.id)
    before = db_session.execute(select(func.count()).select_from(IntelligenceOutcome)).scalar_one()
    response = client.get(f"/api/v1/intelligence/outcomes?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []
    after = db_session.execute(select(func.count()).select_from(IntelligenceOutcome)).scalar_one()
    assert before == after == 0
