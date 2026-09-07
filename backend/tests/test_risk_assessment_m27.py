"""SIE Milestone 27: Risk Assessment & Action Management Integration
v0.1 — dedicated regression suite for the finding <-> action
relationship, closure governance, and everything else this milestone
adds on top of the M25/25A/26 Risk Assessment domain. HTTP-level tests
run against the ordinary SQLite `client` fixture, mirroring
`tests/test_risk_assessment_m26.py`'s own established shape.
(Transactional-integrity coverage lives in
`tests/test_risk_assessment_m27_transaction_integrity.py`; the
migration's own round trip lives in `tests/test_migrations.py`.)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.ontology_concept import OntologyConcept
from app.models.risk_assessment_history import RiskAssessmentHistory
from app.models.safety_action import SafetyAction
from app.models.safety_action_history import SafetyActionHistory
from app.services.api_client_service import api_client_service
from app.services.permissions import OrganizationRole, Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, seed_risk_area_ontology_concepts

_URL = "/api/v1/risk-assessments"
AS_OF = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _risk_area_concepts(db_session) -> dict[str, uuid.UUID]:
    return seed_risk_area_ontology_concepts(db_session)


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _make_client_credential(db_session, org_id, *, scopes=None):
    scopes = scopes if scopes is not None else [Permission.RISK_ASSESSMENT_READ, Permission.RISK_ASSESSMENT_WRITE]
    return api_client_service.create(db_session, organization_id=org_id, name="Test Integration", scopes=scopes)


def _create_body(**overrides) -> dict:
    body = {
        "scope": "ORGANIZATION",
        "title": "M27 Test Assessment",
        "assessment_type": "BASELINE",
        "assessment_date": AS_OF.isoformat(),
        "as_of": AS_OF.isoformat(),
        "generate_candidates": False,
    }
    body.update(overrides)
    return body


def _create(client, headers, org_id, **overrides) -> dict:
    response = client.post(f"{_URL}?organization_id={org_id}", json=_create_body(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _risk_area_concept_id(db_session, concept_key: str = "VEHICLE_INCIDENT") -> str:
    concept = db_session.execute(
        select(OntologyConcept).where(
            OntologyConcept.concept_key == concept_key, OntologyConcept.organization_id.is_(None)
        )
    ).scalar_one()
    return str(concept.id)


def _finding_body(db_session, **overrides) -> dict:
    body = {"risk_area_concept_id": _risk_area_concept_id(db_session), "title": "A finding"}
    body.update(overrides)
    return body


def _create_finding(client, headers, org_id, assessment_id, db_session, **overrides) -> dict:
    response = client.post(
        f"{_URL}/{assessment_id}/findings?organization_id={org_id}",
        json=_finding_body(db_session, **overrides),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _make_action(db_session, org_id, **overrides) -> SafetyAction:
    action = SafetyAction(
        organization_id=org_id, title="Corrective action", action_type="CORRECTIVE", priority="MEDIUM",
        status="OPEN", attributes={},
    )
    for k, v in overrides.items():
        setattr(action, k, v)
    db_session.add(action)
    db_session.commit()
    return action


def _action_create_body(**overrides) -> dict:
    body = {"title": "New corrective action", "action_type": "CORRECTIVE", "priority": "MEDIUM"}
    body.update(overrides)
    return body


def _history_for(db_session, organization_id, *, assessment_id=None, finding_id=None) -> list[RiskAssessmentHistory]:
    db_session.expire_all()
    stmt = select(RiskAssessmentHistory).where(RiskAssessmentHistory.organization_id == organization_id)
    if assessment_id is not None:
        stmt = stmt.where(RiskAssessmentHistory.assessment_id == assessment_id)
    if finding_id is not None:
        stmt = stmt.where(RiskAssessmentHistory.finding_id == finding_id)
    return list(db_session.execute(stmt).scalars().all())


def _rated_finding(client, headers, org_id, assessment_id, db_session, **overrides) -> dict:
    body = {"likelihood": 4, "consequence": 4}
    body.update(overrides)
    return _create_finding(client, headers, org_id, assessment_id, db_session, **body)


# --- Relationship (item: create/link/multiple/unlink/retrieve/navigation) -----------------


def test_create_action_from_finding_creates_and_links(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}",
        json=_action_create_body(title="Fix the guardrail"),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["action_title"] == "Fix the guardrail"
    assert body["action_status"] == "OPEN"
    assert body["finding_id"] == finding["id"]

    action = db_session.get(SafetyAction, uuid.UUID(body["action_id"]))
    assert action.organization_id == org.id
    assert action.attributes["risk_assessment_origin"]["finding_id"] == finding["id"]
    assert action.attributes["risk_assessment_origin"]["assessment_id"] == assessment["id"]


def test_link_existing_action_to_finding(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
        json={"action_id": str(action.id)},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["action_id"] == str(action.id)


def test_multiple_actions_can_be_linked_to_one_finding(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action_a = _make_action(db_session, org.id, title="Action A")
    action_b = _make_action(db_session, org.id, title="Action B")
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    for action in (action_a, action_b):
        response = client.post(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
            json={"action_id": str(action.id)},
            headers=headers,
        )
        assert response.status_code == 200, response.text

    listed = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}", headers=headers
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    assert {item["action_id"] for item in body["items"]} == {str(action_a.id), str(action_b.id)}


def test_unlink_action_removes_relationship(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
        json={"action_id": str(action.id)}, headers=headers,
    )

    response = client.delete(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/{action.id}?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 204

    listed = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}", headers=headers
    )
    assert listed.json()["total"] == 0


def test_action_to_finding_navigation(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
        json={"action_id": str(action.id)}, headers=headers,
    )

    response = client.get(f"{_URL}/actions/{action.id}/findings?organization_id={org.id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action_id"] == str(action.id)
    assert len(body["findings"]) == 1
    assert body["findings"][0]["id"] == finding["id"]
    assert body["findings"][0]["assessment_id"] == assessment["id"]


def test_linking_same_action_twice_is_idempotent(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    for _ in range(2):
        response = client.post(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
            json={"action_id": str(action.id)}, headers=headers,
        )
        assert response.status_code == 200

    listed = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}", headers=headers
    )
    assert listed.json()["total"] == 1


def test_unlinking_unlinked_action_is_idempotent(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    response = client.delete(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/{action.id}?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 204


def test_legacy_linked_action_id_patch_appears_in_relationship_list(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"linked_action_id": str(action.id)}, headers=headers,
    )

    listed = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}", headers=headers
    )
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["action_id"] == str(action.id)


def test_unlinking_via_new_endpoint_clears_legacy_linked_action_id_field(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)
    client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"linked_action_id": str(action.id)}, headers=headers,
    )

    response = client.delete(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/{action.id}?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 204

    refetched = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}", headers=headers
    )
    # No dedicated GET-one-finding route exists -- read it back off the assessment detail.
    detail = client.get(f"{_URL}/{assessment['id']}?organization_id={org.id}", headers=headers).json()
    refetched_finding = next(f for f in detail["findings"] if f["id"] == finding["id"])
    assert refetched_finding["linked_action_id"] is None


# --- Security --------------------------------------------------------------------------


def test_cross_tenant_action_link_rejected(client, db_session):
    org_a = make_org(db_session, "M27 Org A")
    org_b = make_org(db_session, "M27 Org B")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    headers_a = dev_auth_headers(manager_a.id)
    foreign_action = _make_action(db_session, org_b.id)
    assessment = _create(client, headers_a, org_a.id)
    finding = _create_finding(client, headers_a, org_a.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org_a.id}",
        json={"action_id": str(foreign_action.id)}, headers=headers_a,
    )
    assert response.status_code == 404


def test_cross_tenant_finding_access_rejected(client, db_session):
    org_a = make_org(db_session, "M27 Org A2")
    org_b = make_org(db_session, "M27 Org B2")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    headers_b = dev_auth_headers(manager_b.id)
    assessment = _create(client, dev_auth_headers(manager_a.id), org_a.id)
    finding = _create_finding(client, dev_auth_headers(manager_a.id), org_a.id, assessment["id"], db_session)
    action = _make_action(db_session, org_b.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org_b.id}",
        json={"action_id": str(action.id)}, headers=headers_b,
    )
    assert response.status_code == 404


def test_machine_client_pinning_on_relationship_endpoint(client, db_session):
    org_a = make_org(db_session, "M27 Pin Org A")
    org_b = make_org(db_session, "M27 Pin Org B")
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    assessment = _create(client, dev_auth_headers(manager_b.id), org_b.id)
    finding = _create_finding(client, dev_auth_headers(manager_b.id), org_b.id, assessment["id"], db_session)
    action = _make_action(db_session, org_b.id)
    credential = _make_client_credential(db_session, org_a.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org_b.id}",
        json={"action_id": str(action.id)}, headers=_bearer(credential),
    )
    assert response.status_code == 403


def test_create_action_from_finding_requires_intervention_manage(client, db_session):
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    headers = dev_auth_headers(analyst.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}",
        json=_action_create_body(), headers=headers,
    )
    assert response.status_code == 403


def test_link_existing_action_only_requires_risk_assessment_write(client, db_session):
    """Unlike creating a new action, linking an existing one never
    mutates the Actions domain -- HSE_ANALYST (RISK_ASSESSMENT_WRITE,
    no INTERVENTION_MANAGE) can still do it."""
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    headers = dev_auth_headers(analyst.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
        json={"action_id": str(action.id)}, headers=headers,
    )
    assert response.status_code == 200


def test_create_action_with_owner_requires_intervention_assign(client, db_session):
    org = make_org(db_session)
    credential = _make_client_credential(
        db_session, org.id,
        scopes=[Permission.RISK_ASSESSMENT_READ, Permission.RISK_ASSESSMENT_WRITE, Permission.INTERVENTION_MANAGE],
    )
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    assessment = _create(client, dev_auth_headers(manager.id), org.id)
    finding = _create_finding(client, dev_auth_headers(manager.id), org.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}",
        json=_action_create_body(owner_user_id=str(owner.id)), headers=_bearer(credential),
    )
    assert response.status_code == 403


# --- Lifecycle ---------------------------------------------------------------------------


def test_completed_action_does_not_automatically_close_finding(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _rated_finding(client, headers, org.id, assessment["id"], db_session)
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
        json={"action_id": str(action.id)}, headers=headers,
    )

    action.status = "COMPLETED"
    db_session.add(action)
    db_session.commit()

    detail = client.get(f"{_URL}/{assessment['id']}?organization_id={org.id}", headers=headers).json()
    refetched = next(f for f in detail["findings"] if f["id"] == finding["id"])
    assert refetched["status"] == "OPEN"


def test_finding_closure_requires_explicit_operation_not_generic_patch(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = _rated_finding(client, headers, org.id, assessment["id"], db_session)

    generic = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"status": "CLOSED"}, headers=headers,
    )
    assert generic.status_code == 422

    explicit = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
        json={"closure_reason": "Residual risk assessed as acceptable after controls verified."}, headers=headers,
    )
    assert explicit.status_code == 200
    assert explicit.json()["status"] == "CLOSED"


def test_finding_closure_requires_a_closure_reason(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = _rated_finding(client, headers, org.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
        json={"closure_reason": "   "}, headers=headers,
    )
    assert response.status_code == 422


def test_finding_closure_requires_the_finding_to_be_rated(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)  # never rated
    assert finding["likelihood"] is None

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
        json={"closure_reason": "Not actually risky."}, headers=headers,
    )
    assert response.status_code == 422


def test_closed_finding_cannot_be_closed_again(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = _rated_finding(client, headers, org.id, assessment["id"], db_session)
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
        json={"closure_reason": "Resolved."}, headers=headers,
    )

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
        json={"closure_reason": "Resolved again?"}, headers=headers,
    )
    assert response.status_code == 422


def test_finding_closure_requires_the_approve_permission(client, db_session):
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    headers = dev_auth_headers(analyst.id)
    assessment = _create(client, headers, org.id)
    finding = _rated_finding(client, headers, org.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
        json={"closure_reason": "Resolved."}, headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "op",
    ["link", "create", "unlink", "close"],
)
def test_relationship_and_closure_mutations_rejected_on_approved_assessment(client, db_session, op):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _rated_finding(client, headers, org.id, assessment["id"], db_session)
    if op == "unlink":
        client.post(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
            json={"action_id": str(action.id)}, headers=headers,
        )
    client.post(f"{_URL}/{assessment['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{assessment['id']}/approve?organization_id={org.id}", headers=headers)

    if op == "link":
        response = client.post(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
            json={"action_id": str(action.id)}, headers=headers,
        )
    elif op == "create":
        response = client.post(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}",
            json=_action_create_body(), headers=headers,
        )
    elif op == "unlink":
        response = client.delete(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/{action.id}?organization_id={org.id}",
            headers=headers,
        )
    else:
        response = client.post(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
            json={"closure_reason": "Resolved."}, headers=headers,
        )
    assert response.status_code == 422


# --- History / audit ---------------------------------------------------------------------


def test_create_action_from_finding_writes_history_and_audit(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions?organization_id={org.id}",
        json=_action_create_body(), headers=headers,
    )
    action_id = response.json()["action_id"]

    history = _history_for(db_session, org.id, finding_id=uuid.UUID(finding["id"]))
    assert any(h.change_type == "FINDING_ACTION_CREATED" for h in history)
    ra_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org.id, AuditLog.action == "RISK_ASSESSMENT_FINDING_ACTION_CREATED"
        )
    ).scalars().all()
    assert len(ra_audit) == 1
    assert ra_audit[0].event_metadata["action_id"] == action_id

    # The action's own domain trail is written too -- reused, not duplicated.
    action_history = db_session.execute(
        select(SafetyActionHistory).where(SafetyActionHistory.action_id == uuid.UUID(action_id))
    ).scalars().all()
    assert any(h.change_type == "CREATED" for h in action_history)
    action_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org.id, AuditLog.action == "SAFETY_ACTION_CREATED",
            AuditLog.resource_id == uuid.UUID(action_id),
        )
    ).scalars().all()
    assert len(action_audit) == 1


def test_link_writes_history_and_audit(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)

    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
        json={"action_id": str(action.id)}, headers=headers,
    )

    history = _history_for(db_session, org.id, finding_id=uuid.UUID(finding["id"]))
    assert any(h.change_type == "FINDING_ACTION_LINKED" for h in history)
    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org.id, AuditLog.action == "RISK_ASSESSMENT_FINDING_ACTION_LINKED"
        )
    ).scalars().all()
    assert len(audit) == 1


def test_unlink_writes_history_and_audit(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
        json={"action_id": str(action.id)}, headers=headers,
    )

    client.delete(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/actions/{action.id}?organization_id={org.id}",
        headers=headers,
    )

    history = _history_for(db_session, org.id, finding_id=uuid.UUID(finding["id"]))
    assert any(h.change_type == "FINDING_ACTION_UNLINKED" for h in history)
    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org.id, AuditLog.action == "RISK_ASSESSMENT_FINDING_ACTION_UNLINKED"
        )
    ).scalars().all()
    assert len(audit) == 1


def test_close_writes_history_and_audit_with_reason(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = _rated_finding(client, headers, org.id, assessment["id"], db_session)

    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
        json={"closure_reason": "Verified controls address the residual risk."}, headers=headers,
    )

    history = _history_for(db_session, org.id, finding_id=uuid.UUID(finding["id"]))
    closed_entries = [h for h in history if h.change_type == "FINDING_CLOSED"]
    assert len(closed_entries) == 1
    assert closed_entries[0].comment == "Verified controls address the residual risk."
    assert closed_entries[0].from_status == "OPEN"
    assert closed_entries[0].to_status == "CLOSED"
    audit = db_session.execute(
        select(AuditLog).where(AuditLog.organization_id == org.id, AuditLog.action == "RISK_ASSESSMENT_FINDING_CLOSED")
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].event_metadata["closure_reason"] == "Verified controls address the residual risk."


# --- Historical integrity -----------------------------------------------------------------


def test_previous_approved_assessment_unchanged_by_later_relationship_operations(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    v1 = _create(client, headers, org.id)
    finding = _rated_finding(client, headers, org.id, v1["id"], db_session)
    client.post(
        f"{_URL}/{v1['id']}/findings/{finding['id']}/actions/link?organization_id={org.id}",
        json={"action_id": str(action.id)}, headers=headers,
    )
    client.post(f"{_URL}/{v1['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v1['id']}/approve?organization_id={org.id}", headers=headers)

    before = client.get(f"{_URL}/{v1['id']}?organization_id={org.id}", headers=headers).json()

    # Opening (but not approving) a new version must not touch v1 at all --
    # v2 starts with no findings of its own (existing M25 behavior, unmodified).
    v2 = _create(client, headers, org.id, supersedes_assessment_id=v1["id"])
    assert v2["findings"] == []

    after = client.get(f"{_URL}/{v1['id']}?organization_id={org.id}", headers=headers).json()
    assert after["status"] == "APPROVED"
    assert before["findings"] == after["findings"]

    # The relationship itself is still attributable to the correct
    # (v1) assessment/finding.
    findings_for_action = client.get(f"{_URL}/actions/{action.id}/findings?organization_id={org.id}", headers=headers).json()
    assert findings_for_action["findings"][0]["assessment_id"] == v1["id"]
