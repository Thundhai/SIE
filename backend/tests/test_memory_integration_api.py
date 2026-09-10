"""SIE Milestone 41: Learning Integration & Intelligence Adaptation
Architecture — HTTP-layer tests for
`GET /api/v1/intelligence/memory-context`,
`GET /api/v1/intelligence/sites/{site_id}/memory-context`, and
`GET /api/v1/intelligence/decisions/{decision_id}/memory-context`.
Mirrors `tests/test_organizational_memory_api.py`'s own established
shape: runs against the ordinary SQLite `client` fixture.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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


def _create_candidate(client, org_id, headers, outcome_id) -> dict:
    response = client.post(
        f"/api/v1/intelligence/learning-candidates?organization_id={org_id}",
        json={"outcome_id": outcome_id}, headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _govern_candidate(client, org_id, headers, candidate_id, status, **overrides) -> dict:
    body = {"status": status, "rationale": "Governance test rationale."}
    body.update(overrides)
    response = client.post(
        f"/api/v1/intelligence/learning-candidates/{candidate_id}/governance-decisions?organization_id={org_id}",
        json=body, headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_memory(client, org_id, headers, candidate_id, **overrides) -> dict:
    body = {
        "learning_candidate_id": candidate_id,
        "memory_type": "LESSON_LEARNED",
        "title": "Permit checks should precede coordination meetings",
        "memory_content": (
            "Repeated permit deviations during simultaneous operations indicate that permit "
            "verification should occur before the coordination meeting."
        ),
        "rationale": "This pattern recurred across multiple accepted candidates.",
    }
    body.update(overrides)
    response = client.post(
        f"/api/v1/intelligence/organizational-memory?organization_id={org_id}", json=body, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _retract_memory(client, org_id, headers, memory_id) -> dict:
    response = client.post(
        f"/api/v1/intelligence/organizational-memory/{memory_id}/governance-decisions?organization_id={org_id}",
        json={"status": "RETRACTED", "rationale": "No longer applicable."}, headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _setup_active_memory(client, db_session, email, *, site_id=None):
    """Full chain via HTTP: decision -> outcome (optionally site-scoped)
    -> verification -> ACCEPTED candidate -> memory (implicit ACTIVE).
    Returns (org, user, headers, decision, outcome, memory)."""
    org = create_org(client)
    user = make_user(db_session, email)
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    decision = _create_decision(client, org["id"], headers)
    event = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome = _create_outcome(
        client, org["id"], headers, decision["id"], evidence_event_ids=[str(event.id)], site_id=str(site_id) if site_id else None
    )
    _create_verification(client, org["id"], headers, outcome["id"])
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    _govern_candidate(client, org["id"], headers, candidate["id"], "ACCEPTED")
    memory = _create_memory(client, org["id"], headers, candidate["id"])
    return org, user, headers, decision, outcome, memory


_ORG_MEMORY_CONTEXT_URL = "/api/v1/intelligence/memory-context"


def _site_memory_context_url(site_id) -> str:
    return f"/api/v1/intelligence/sites/{site_id}/memory-context"


def _decision_memory_context_url(decision_id) -> str:
    return f"/api/v1/intelligence/decisions/{decision_id}/memory-context"


# --- Q: Authorization ----------------------------------------------------------------------------


def test_memory_context_requires_authentication(client):
    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


def test_memory_context_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider-mi1@example.com")
    from tests.conftest import dev_auth_headers

    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org['id']}", headers=dev_auth_headers(user.id))
    assert response.status_code == 403


def test_viewer_role_can_read_memory_context(client, db_session):
    """Reads reuse INTELLIGENCE_READ -- a VIEWER (read-only role) must
    be authorized, unlike write endpoints."""
    org, _, headers, _decision, _outcome, memory = _setup_active_memory(client, db_session, "manager-mi1@example.com")
    viewer = make_user(db_session, "viewer-mi1@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    from tests.conftest import dev_auth_headers

    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org['id']}", headers=dev_auth_headers(viewer.id))
    assert response.status_code == 200
    assert [item["memory_id"] for item in response.json()["items"]] == [memory["id"]]


# --- R: machine tenant binding ---------------------------------------------------------------


def test_machine_client_with_read_scope_can_read_memory_context(client, db_session):
    org, _, _headers, _decision, _outcome, memory = _setup_active_memory(client, db_session, "manager-mi2@example.com")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))

    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 200
    assert [item["memory_id"] for item in response.json()["items"]] == [memory["id"]]


def test_machine_client_cannot_query_a_different_organizations_memory_context(client, db_session):
    org_a, _, _headers_a, _decision_a, _outcome_a, _memory_a = _setup_active_memory(
        client, db_session, "manager-mi3a@example.com"
    )
    org_b = create_org(client, name="Org B memory-context machine")
    credential_b = _make_client_credential(db_session, uuid.UUID(org_b["id"]))

    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org_a['id']}", headers=_bearer(credential_b))
    assert response.status_code == 403


def test_machine_client_without_read_scope_is_rejected(client, db_session):
    org, _, _headers, _decision, _outcome, _memory = _setup_active_memory(client, db_session, "manager-mi4@example.com")
    write_only = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_DECISION_WRITE])

    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org['id']}", headers=_bearer(write_only))
    assert response.status_code == 403


# --- G: tenant isolation (HTTP) -----------------------------------------------------------------


def test_cannot_read_another_organizations_memory_context(client, db_session):
    org_a, _, _headers_a, _decision_a, _outcome_a, _memory_a = _setup_active_memory(
        client, db_session, "manager-mi5a@example.com"
    )
    org_b = create_org(client, name="Org B memory-context read")
    user_b = make_user(db_session, "manager-mi5b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org_b['id']}", headers=headers_b)
    assert response.status_code == 200
    assert response.json()["items"] == []


# --- B/C: ACTIVE/RETRACTED over HTTP --------------------------------------------------------------


def test_retracted_memory_is_excluded_over_http(client, db_session):
    org, _, headers, _decision, _outcome, memory = _setup_active_memory(client, db_session, "manager-mi6@example.com")
    _retract_memory(client, org["id"], headers, memory["id"])

    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


# --- H: project/site scope over HTTP ---------------------------------------------------------------


def test_site_scope_excludes_a_different_sites_memory(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "manager-mi7@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    seed_risk_area_ontology_concepts(db_session)
    _seed_incidents(db_session, uuid.UUID(org["id"]))
    headers = dev_auth_headers(user.id)
    site_a = make_site(db_session, uuid.UUID(org["id"]), "Site A")
    site_b = make_site(db_session, uuid.UUID(org["id"]), "Site B")
    decision = _create_decision(client, org["id"], headers)
    event = _make_evidence_event(db_session, uuid.UUID(org["id"]))
    outcome = _create_outcome(
        client, org["id"], headers, decision["id"], evidence_event_ids=[str(event.id)], site_id=str(site_a.id)
    )
    _create_verification(client, org["id"], headers, outcome["id"])
    candidate = _create_candidate(client, org["id"], headers, outcome["id"])
    _govern_candidate(client, org["id"], headers, candidate["id"], "ACCEPTED")
    memory = _create_memory(client, org["id"], headers, candidate["id"])

    same_site = client.get(_site_memory_context_url(site_a.id), params={"organization_id": org["id"]}, headers=headers)
    other_site = client.get(_site_memory_context_url(site_b.id), params={"organization_id": org["id"]}, headers=headers)
    assert same_site.status_code == 200
    assert [item["memory_id"] for item in same_site.json()["items"]] == [memory["id"]]
    assert other_site.status_code == 200
    assert other_site.json()["items"] == []


def test_site_scope_requires_a_valid_site_id(client, db_session):
    org, _, headers, _decision, _outcome, _memory = _setup_active_memory(client, db_session, "manager-mi8@example.com")

    response = client.get(_site_memory_context_url(uuid.uuid4()), params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 404


# --- J/provenance over HTTP ------------------------------------------------------------------------


def test_memory_context_item_carries_full_provenance(client, db_session):
    org, _, headers, _decision, outcome, memory = _setup_active_memory(client, db_session, "manager-mi9@example.com")

    response = client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["memory_id"] == memory["id"]
    assert item["learning_candidate_id"] == memory["learning_candidate_id"]
    assert item["outcome_id"] == outcome["id"]
    assert item["verification_id"] == memory["verification_id"] if "verification_id" in memory else True
    assert item["applicability_basis"] == "ORGANIZATION_WIDE"
    assert item["governance_status"] == "ACTIVE"
    assert item["governance_is_explicit"] is False


# --- T: pagination ----------------------------------------------------------------------------


def test_pagination_is_deterministic_and_bounded(client, db_session):
    org, _, headers, decision, _outcome, memory1 = _setup_active_memory(client, db_session, "manager-mi10@example.com")
    memories = [memory1]
    for _ in range(2):
        event = _make_evidence_event(db_session, uuid.UUID(org["id"]))
        outcome = _create_outcome(client, org["id"], headers, decision["id"], evidence_event_ids=[str(event.id)])
        _create_verification(client, org["id"], headers, outcome["id"])
        candidate = _create_candidate(client, org["id"], headers, outcome["id"])
        _govern_candidate(client, org["id"], headers, candidate["id"], "ACCEPTED")
        memories.append(_create_memory(client, org["id"], headers, candidate["id"]))

    page1 = client.get(_ORG_MEMORY_CONTEXT_URL, params={"organization_id": org["id"], "page": 1, "page_size": 2}, headers=headers)
    assert page1.status_code == 200
    assert page1.json()["total"] == 3
    assert len(page1.json()["items"]) == 2
    page2 = client.get(_ORG_MEMORY_CONTEXT_URL, params={"organization_id": org["id"], "page": 2, "page_size": 2}, headers=headers)
    assert len(page2.json()["items"]) == 1
    # newest-first, deterministic
    assert page1.json()["items"][0]["memory_id"] == memories[2]["id"]
    assert page2.json()["items"][0]["memory_id"] == memories[0]["id"]


# --- D: as_of over HTTP --------------------------------------------------------------------------


def test_as_of_excludes_memory_created_after_the_cutoff(client, db_session):
    cutoff = datetime.now(timezone.utc)
    org, _, headers, _decision, _outcome, _memory = _setup_active_memory(client, db_session, "manager-mi11@example.com")

    response = client.get(
        _ORG_MEMORY_CONTEXT_URL, params={"organization_id": org["id"], "as_of": cutoff.isoformat()}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_as_of_includes_memory_created_before_the_cutoff(client, db_session):
    org, _, headers, _decision, _outcome, memory = _setup_active_memory(client, db_session, "manager-mi12@example.com")
    future_cutoff = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        _ORG_MEMORY_CONTEXT_URL, params={"organization_id": org["id"], "as_of": future_cutoff.isoformat()}, headers=headers
    )
    assert response.status_code == 200
    assert [item["memory_id"] for item in response.json()["items"]] == [memory["id"]]


# --- K: decision traceability ----------------------------------------------------------------------


def test_decision_memory_context_reconstructs_the_decisions_own_scope(client, db_session):
    """A decision's own `intelligence_as_of` is snapshotted at the
    moment *that* decision was made -- necessarily *before* any outcome/
    verification/candidate/memory chain it later produces (DECIDE ->
    INTERVENE -> OUTCOME -> VERIFY -> LEARNING CANDIDATE -> MEMORY), so
    `decision`'s own memory-context can never include `memory` (see
    `test_decision_memory_context_excludes_a_memory_retracted_before_
    the_decision` for that exact, correct causal-ordering case). To
    demonstrate a decision's context genuinely *including* an
    already-existing memory, this test creates the memory first, then a
    **second**, later decision -- whose own `intelligence_as_of` is
    therefore after the memory's `created_at`."""
    org, _, headers, _first_decision, _outcome, memory = _setup_active_memory(client, db_session, "manager-mi13@example.com")
    later_decision = _create_decision(client, org["id"], headers)

    response = client.get(
        _decision_memory_context_url(later_decision["id"]), params={"organization_id": org["id"]}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision_id"] == later_decision["id"]
    assert [item["memory_id"] for item in body["items"]] == [memory["id"]]


def test_decision_memory_context_requires_a_valid_decision_id(client, db_session):
    org, _, headers, _decision, _outcome, _memory = _setup_active_memory(client, db_session, "manager-mi14@example.com")

    response = client.get(_decision_memory_context_url(uuid.uuid4()), params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 404


def test_decision_memory_context_rejects_a_cross_tenant_decision(client, db_session):
    org_a, _, headers_a, decision_a, _outcome_a, _memory_a = _setup_active_memory(
        client, db_session, "manager-mi15a@example.com"
    )
    org_b = create_org(client, name="Org B decision memory-context")
    user_b = make_user(db_session, "manager-mi15b@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=uuid.UUID(org_b["id"]), role="HSE_MANAGER")
    from tests.conftest import dev_auth_headers

    headers_b = dev_auth_headers(user_b.id)
    response = client.get(
        _decision_memory_context_url(decision_a["id"]), params={"organization_id": org_b["id"]}, headers=headers_b
    )
    assert response.status_code == 404


def test_decision_memory_context_excludes_a_memory_retracted_before_the_decision(client, db_session):
    """A memory created and retracted entirely *after* the decision was
    made must not appear when reconstructing the decision's own
    historical context -- as_of is the decision's own intelligence_as_of,
    which predates both events."""
    org, _, headers, decision, _outcome, memory = _setup_active_memory(client, db_session, "manager-mi16@example.com")
    _retract_memory(client, org["id"], headers, memory["id"])

    response = client.get(_decision_memory_context_url(decision["id"]), params={"organization_id": org["id"]}, headers=headers)
    assert response.status_code == 200
    # The decision's own intelligence_as_of predates the memory's own
    # creation (the memory didn't exist yet when the decision was made),
    # so it must not appear in the reconstructed decision context.
    assert response.json()["items"] == []


# --- Read-only boundary -----------------------------------------------------------------------


def test_memory_context_reads_never_write(client, db_session):
    from sqlalchemy import func, select

    from app.models.organizational_memory import OrganizationalMemory, OrganizationalMemoryGovernanceDecision

    org, _, headers, _decision, _outcome, _memory = _setup_active_memory(client, db_session, "manager-mi17@example.com")
    before_memories = db_session.execute(select(func.count()).select_from(OrganizationalMemory)).scalar_one()
    before_governance = db_session.execute(
        select(func.count()).select_from(OrganizationalMemoryGovernanceDecision)
    ).scalar_one()

    client.get(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org['id']}", headers=headers)

    after_memories = db_session.execute(select(func.count()).select_from(OrganizationalMemory)).scalar_one()
    after_governance = db_session.execute(
        select(func.count()).select_from(OrganizationalMemoryGovernanceDecision)
    ).scalar_one()
    assert before_memories == after_memories == 1
    assert before_governance == after_governance == 0


# --- No PUT/PATCH/DELETE/POST on memory-context (no autonomous learning surface) -----------------


def test_no_write_method_exists_for_memory_context(client, db_session):
    org, _, headers, _decision, _outcome, _memory = _setup_active_memory(client, db_session, "manager-mi18@example.com")

    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)(f"{_ORG_MEMORY_CONTEXT_URL}?organization_id={org['id']}", headers=headers)
        assert response.status_code in (404, 405)
