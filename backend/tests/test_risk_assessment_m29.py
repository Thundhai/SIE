"""SIE Milestone 29: Enterprise Risk Assessment Evidence & Control
Effectiveness Foundation v0.1 — dedicated regression suite for the
control management API (create/list/retrieve/update), the dedicated
effectiveness-assessment endpoint, control<->evidence linking, and the
M28 report's new `control_effectiveness` section. HTTP-level tests run
against the ordinary SQLite `client` fixture, mirroring
`tests/test_risk_assessment_m27.py`'s own established shape.
(Transactional-integrity coverage lives in
`tests/test_risk_assessment_m29_transaction_integrity.py`; the
migration's own round trip and downgrade guards live in
`tests/test_migrations.py`.)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.ontology_concept import OntologyConcept
from app.models.risk_assessment import RiskAssessmentControl
from app.models.risk_assessment_history import RiskAssessmentHistory
from app.models.safety_action import SafetyAction
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
        "title": "M29 Test Assessment",
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


def _control_body(**overrides) -> dict:
    body = {"description": "Guardrail installed at loading dock", "control_type": "ENGINEERING"}
    body.update(overrides)
    return body


def _create_control(client, headers, org_id, assessment_id, finding_id, **overrides) -> dict:
    response = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org_id}",
        json=_control_body(**overrides),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assess_body(**overrides) -> dict:
    body = {"effectiveness_rating": "EFFECTIVE", "effectiveness_rationale": "Verified during site walkthrough."}
    body.update(overrides)
    return body


def _add_finding_evidence(client, headers, org_id, assessment_id, finding_id, **overrides) -> str:
    body = {"evidence_type": "OTHER", "reference_label": "Inspection log #42"}
    body.update(overrides)
    response = client.patch(
        f"{_URL}/{assessment_id}/findings/{finding_id}?organization_id={org_id}",
        json={"evidence_add": [body]}, headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["evidence"][-1]["id"]


def _history_for(db_session, organization_id, *, control_id=None) -> list[RiskAssessmentHistory]:
    db_session.expire_all()
    stmt = select(RiskAssessmentHistory).where(RiskAssessmentHistory.organization_id == organization_id)
    if control_id is not None:
        stmt = stmt.where(RiskAssessmentHistory.control_id == control_id)
    return list(db_session.execute(stmt).scalars().all())


def _audit_rows(db_session, organization_id, action_name) -> list[AuditLog]:
    db_session.expire_all()
    return list(
        db_session.execute(
            select(AuditLog).where(AuditLog.organization_id == organization_id, AuditLog.action == action_name)
        ).scalars().all()
    )


def _setup_finding(client, headers, org_id, db_session, **overrides) -> tuple[dict, dict]:
    assessment = _create(client, headers, org_id)
    finding = _create_finding(client, headers, org_id, assessment["id"], db_session, **overrides)
    return assessment, finding


# --- Schema/model validation ------------------------------------------------------------------


def test_control_create_rejects_extra_fields(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls?organization_id={org.id}",
        json=_control_body(effectiveness="EFFECTIVE"), headers=headers,
    )
    assert response.status_code == 422


def test_control_create_rejects_invalid_control_type(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls?organization_id={org.id}",
        json=_control_body(control_type="NOT_A_REAL_TYPE"), headers=headers,
    )
    assert response.status_code == 422


def test_assess_effectiveness_rejects_not_assessed_rating(client, db_session):
    """NOT_ASSESSED must not masquerade as an assessed conclusion."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(effectiveness_rating="NOT_ASSESSED"), headers=headers,
    )
    assert response.status_code == 422


# --- Create / list / retrieve / update ---------------------------------------------------------


def test_create_control(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)

    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    assert control["finding_id"] == finding["id"]
    assert control["description"] == "Guardrail installed at loading dock"
    assert control["control_type"] == "ENGINEERING"
    assert control["status"] == "PROPOSED"
    assert control["effectiveness"] == "NOT_ASSESSED"
    assert control["effectiveness_rationale"] is None
    assert control["assessed_at"] is None
    assert control["assessed_by_user_id"] is None
    assert control["evidence"] == []

    row = db_session.get(RiskAssessmentControl, uuid.UUID(control["id"]))
    assert row.organization_id == org.id


def test_list_controls(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    _create_control(client, headers, org.id, assessment["id"], finding["id"], description="Control A")
    _create_control(client, headers, org.id, assessment["id"], finding["id"], description="Control B")

    response = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls?organization_id={org.id}", headers=headers
    )
    assert response.status_code == 200
    descriptions = {c["description"] for c in response.json()}
    assert descriptions == {"Control A", "Control B"}


def test_get_control(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["id"] == control["id"]


def test_get_nonexistent_control_is_404(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)

    response = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{uuid.uuid4()}?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 404


def test_update_control_metadata(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        json={"status": "IN_PLACE", "reference": "WO-1234"}, headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "IN_PLACE"
    assert body["reference"] == "WO-1234"
    # Untouched by this update.
    assert body["effectiveness"] == "NOT_ASSESSED"


def test_update_control_new_implementation_status_values(client, db_session):
    """SIE Milestone 29's own additive ControlStatus values."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    for new_status in ("PARTIALLY_IMPLEMENTED", "NOT_VERIFIED"):
        response = client.patch(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
            json={"status": new_status}, headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == new_status


def test_create_control_with_other_type(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)

    control = _create_control(client, headers, org.id, assessment["id"], finding["id"], control_type="OTHER")
    assert control["control_type"] == "OTHER"


def test_generic_patch_cannot_set_effectiveness(client, db_session):
    """The spec's own "do not allow effectiveness to be changed silently
    through generic PATCH" -- the field isn't even on the schema."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        json={"effectiveness": "EFFECTIVE"}, headers=headers,
    )
    assert response.status_code == 422


# --- Effectiveness assessment -------------------------------------------------------------------


def test_assess_control_effectiveness(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(), headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["effectiveness"] == "EFFECTIVE"
    assert body["effectiveness_rationale"] == "Verified during site walkthrough."
    assert body["assessed_at"] is not None
    assert body["assessed_by_user_id"] == str(manager.id)


def test_assess_control_effectiveness_blank_rationale_rejected(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(effectiveness_rationale="   "), headers=headers,
    )
    assert response.status_code == 422


def test_assess_control_effectiveness_explicit_assessed_at(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    explicit = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(assessed_at=explicit), headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["assessed_at"][:10] == explicit[:10]


# --- Control evidence ----------------------------------------------------------------------------


def test_link_control_evidence(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    evidence_id = _add_finding_evidence(client, headers, org.id, assessment["id"], finding["id"])

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["control_id"] == control["id"]
    assert body["finding_evidence_id"] == evidence_id
    assert body["evidence"]["id"] == evidence_id

    fetched = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        headers=headers,
    ).json()
    assert [e["id"] for e in fetched["evidence"]] == [evidence_id]


def test_link_control_evidence_twice_is_idempotent(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    evidence_id = _add_finding_evidence(client, headers, org.id, assessment["id"], finding["id"])
    url = (
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}"
    )

    first = client.post(url, headers=headers)
    second = client.post(url, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    fetched = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        headers=headers,
    ).json()
    assert len(fetched["evidence"]) == 1


def test_link_control_evidence_from_different_finding_rejected(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding_a = _create_finding(client, headers, org.id, assessment["id"], db_session)
    finding_b = _create_finding(client, headers, org.id, assessment["id"], db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding_a["id"])
    evidence_id = _add_finding_evidence(client, headers, org.id, assessment["id"], finding_b["id"])

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding_a['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 404


def test_unlink_control_evidence(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    evidence_id = _add_finding_evidence(client, headers, org.id, assessment["id"], finding["id"])
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}",
        headers=headers,
    )

    response = client.delete(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 204

    fetched = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        headers=headers,
    ).json()
    assert fetched["evidence"] == []


def test_unlink_never_linked_evidence_is_idempotent(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    evidence_id = _add_finding_evidence(client, headers, org.id, assessment["id"], finding["id"])

    response = client.delete(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 204


# --- History / audit -------------------------------------------------------------------------


def test_control_lifecycle_writes_history(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    control_id = uuid.UUID(control["id"])

    client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        json={"status": "IN_PLACE"}, headers=headers,
    )
    evidence_id = _add_finding_evidence(client, headers, org.id, assessment["id"], finding["id"])
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}",
        headers=headers,
    )
    client.delete(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}",
        headers=headers,
    )
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(), headers=headers,
    )

    change_types = {h.change_type for h in _history_for(db_session, org.id, control_id=control_id)}
    assert change_types == {
        "CONTROL_CREATED", "CONTROL_UPDATED", "CONTROL_EVIDENCE_LINKED", "CONTROL_EVIDENCE_UNLINKED",
        "CONTROL_EFFECTIVENESS_ASSESSED",
    }
    for entry in _history_for(db_session, org.id, control_id=control_id):
        assert entry.finding_id == uuid.UUID(finding["id"])


def test_control_lifecycle_writes_audit_log(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(), headers=headers,
    )

    assert len(_audit_rows(db_session, org.id, "RISK_ASSESSMENT_CONTROL_CREATED")) == 1
    assert len(_audit_rows(db_session, org.id, "RISK_ASSESSMENT_CONTROL_EFFECTIVENESS_ASSESSED")) == 1


# --- Idempotent create/retry -------------------------------------------------------------------


def test_create_control_idempotency_replay(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    key_headers = {**headers, "Idempotency-Key": "m29-create-control-replay"}

    first = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls?organization_id={org.id}",
        json=_control_body(), headers=key_headers,
    )
    second = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls?organization_id={org.id}",
        json=_control_body(), headers=key_headers,
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    listed = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls?organization_id={org.id}", headers=headers
    ).json()
    assert len(listed) == 1


def test_assess_effectiveness_idempotency_replay(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    key_headers = {**headers, "Idempotency-Key": "m29-assess-replay"}
    url = (
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}"
    )

    first = client.post(url, json=_assess_body(), headers=key_headers)
    second = client.post(url, json=_assess_body(), headers=key_headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["assessed_at"] == second.json()["assessed_at"]


# --- Tenant isolation / hierarchy / permissions -------------------------------------------------


def test_cross_tenant_control_read_rejected(client, db_session):
    org_a = make_org(db_session, "M29 Org A")
    org_b = make_org(db_session, "M29 Org B")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    headers_a = dev_auth_headers(manager_a.id)
    assessment, finding = _setup_finding(client, headers_a, org_a.id, db_session)
    control = _create_control(client, headers_a, org_a.id, assessment["id"], finding["id"])

    response = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org_b.id}",
        headers=dev_auth_headers(manager_b.id),
    )
    assert response.status_code == 404


def test_cross_tenant_control_mutation_rejected(client, db_session):
    org_a = make_org(db_session, "M29 Org A2")
    org_b = make_org(db_session, "M29 Org B2")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    headers_a = dev_auth_headers(manager_a.id)
    assessment, finding = _setup_finding(client, headers_a, org_a.id, db_session)
    control = _create_control(client, headers_a, org_a.id, assessment["id"], finding["id"])

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org_b.id}",
        json={"status": "IN_PLACE"}, headers=dev_auth_headers(manager_b.id),
    )
    assert response.status_code == 404


def test_machine_client_pinning_on_control_endpoint(client, db_session):
    org_a = make_org(db_session, "M29 Pin Org A")
    org_b = make_org(db_session, "M29 Pin Org B")
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    headers_b = dev_auth_headers(manager_b.id)
    assessment, finding = _setup_finding(client, headers_b, org_b.id, db_session)
    control = _create_control(client, headers_b, org_b.id, assessment["id"], finding["id"])
    credential = _make_client_credential(db_session, org_a.id)

    response = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org_b.id}",
        headers=_bearer(credential),
    )
    assert response.status_code == 403


def test_control_hierarchy_mismatch_wrong_finding_is_404(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding_a = _create_finding(client, headers, org.id, assessment["id"], db_session)
    finding_b = _create_finding(client, headers, org.id, assessment["id"], db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding_a["id"])

    response = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding_b['id']}/controls/{control['id']}?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 404


def test_control_hierarchy_mismatch_wrong_assessment_is_404(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment_a, finding_a = _setup_finding(client, headers, org.id, db_session)
    assessment_b, _finding_b = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment_a["id"], finding_a["id"])

    response = client.get(
        f"{_URL}/{assessment_b['id']}/findings/{finding_a['id']}/controls/{control['id']}?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 404


def test_create_control_requires_write_permission(client, db_session):
    org = make_org(db_session)
    viewer = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    assessment, finding = _setup_finding(client, dev_auth_headers(manager.id), org.id, db_session)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls?organization_id={org.id}",
        json=_control_body(), headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_read_control_allows_viewer(client, db_session):
    org = make_org(db_session)
    viewer = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    assessment, finding = _setup_finding(client, dev_auth_headers(manager.id), org.id, db_session)
    control = _create_control(client, dev_auth_headers(manager.id), org.id, assessment["id"], finding["id"])

    response = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 200


def test_assess_effectiveness_only_requires_write_not_approve(client, db_session):
    """Mirrors finding risk-rating's own precedent: an assessor's expert
    judgment is RISK_ASSESSMENT_WRITE, not the more privileged
    RISK_ASSESSMENT_APPROVE closure/archival requires."""
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    headers = dev_auth_headers(analyst.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(), headers=headers,
    )
    assert response.status_code == 200


# --- Risk semantics --------------------------------------------------------------------------


def _get_finding(client, headers, org_id, assessment_id, finding_id) -> dict:
    listed = client.get(f"{_URL}/{assessment_id}/findings?organization_id={org_id}", headers=headers).json()
    return next(f for f in listed["items"] if f["id"] == finding_id)


def test_assessing_effectiveness_does_not_change_residual_risk(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session, likelihood=4, consequence=4)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    before = _get_finding(client, headers, org.id, assessment["id"], finding["id"])
    assert before["residual_risk_score"] is None

    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(effectiveness_rating="EFFECTIVE"), headers=headers,
    )

    after = _get_finding(client, headers, org.id, assessment["id"], finding["id"])
    assert after["inherent_risk_score"] == before["inherent_risk_score"]
    assert after["residual_risk_score"] is None  # never auto-derived from an effective control


def test_completed_action_does_not_mark_control_effective(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    action = SafetyAction(
        organization_id=org.id, title="Install guardrail", action_type="CORRECTIVE", priority="MEDIUM",
        status="COMPLETED", attributes={},
    )
    db_session.add(action)
    db_session.commit()

    fetched = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
        headers=headers,
    ).json()
    assert fetched["effectiveness"] == "NOT_ASSESSED"


def test_control_mutation_rejected_on_approved_assessment(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session, likelihood=4, consequence=4)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    submitted = client.post(f"{_URL}/{assessment['id']}/submit?organization_id={org.id}", headers=headers)
    assert submitted.status_code == 200
    approved = client.post(f"{_URL}/{assessment['id']}/approve?organization_id={org.id}", headers=headers)
    assert approved.status_code == 200

    for response in (
        client.post(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls?organization_id={org.id}",
            json=_control_body(), headers=headers,
        ),
        client.patch(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}?organization_id={org.id}",
            json={"status": "IN_PLACE"}, headers=headers,
        ),
        client.post(
            f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
            f"?organization_id={org.id}",
            json=_assess_body(), headers=headers,
        ),
    ):
        assert response.status_code == 422


# --- Reporting integration (M28 report's new control_effectiveness section) -------------------


def test_report_findings_with_no_controls(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, _finding = _setup_finding(client, headers, org.id, db_session)

    report = client.get(f"{_URL}/{assessment['id']}/report?organization_id={org.id}", headers=headers).json()
    ce = report["control_effectiveness"]
    assert ce["total_controls"] == 0
    assert ce["findings_with_no_controls"] == 1
    assert ce["findings_with_controls_but_no_effectiveness_assessment"] == 0
    assert ce["findings_with_ineffective_or_partially_effective_controls"] == 0


def test_report_controls_not_assessed(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    _create_control(client, headers, org.id, assessment["id"], finding["id"])

    report = client.get(f"{_URL}/{assessment['id']}/report?organization_id={org.id}", headers=headers).json()
    ce = report["control_effectiveness"]
    assert ce["total_controls"] == 1
    assert ce["effectiveness_rating_counts"]["NOT_ASSESSED"] == 1
    assert ce["findings_with_no_controls"] == 0
    assert ce["findings_with_controls_but_no_effectiveness_assessment"] == 1
    assert ce["assessed_controls_with_evidence"] == 0
    assert ce["assessed_controls_without_evidence"] == 0


def test_report_ineffective_control_and_evidence_coverage(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    evidence_id = _add_finding_evidence(client, headers, org.id, assessment["id"], finding["id"])
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/evidence/{evidence_id}"
        f"?organization_id={org.id}",
        headers=headers,
    )
    client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{control['id']}/assess-effectiveness"
        f"?organization_id={org.id}",
        json=_assess_body(effectiveness_rating="INEFFECTIVE"), headers=headers,
    )

    report = client.get(f"{_URL}/{assessment['id']}/report?organization_id={org.id}", headers=headers).json()
    ce = report["control_effectiveness"]
    assert ce["effectiveness_rating_counts"]["INEFFECTIVE"] == 1
    assert ce["findings_with_ineffective_or_partially_effective_controls"] == 1
    assert ce["findings_with_controls_but_no_effectiveness_assessment"] == 0
    assert ce["assessed_controls_with_evidence"] == 1
    assert ce["assessed_controls_without_evidence"] == 0


def test_report_implementation_status_distribution(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    _create_control(client, headers, org.id, assessment["id"], finding["id"], status="PROPOSED")
    _create_control(client, headers, org.id, assessment["id"], finding["id"], status="PARTIALLY_IMPLEMENTED")

    report = client.get(f"{_URL}/{assessment['id']}/report?organization_id={org.id}", headers=headers).json()
    counts = report["control_effectiveness"]["implementation_status_counts"]
    assert counts["PROPOSED"] == 1
    assert counts["PARTIALLY_IMPLEMENTED"] == 1


def test_report_query_count_does_not_grow_with_control_count(client, db_session):
    """Extends M28's own zero-query-growth guarantee: controls (and
    their evidence links) are already eager-loaded by
    `_get_owned_assessment_or_404()`, so a report with many controls
    costs the same as one with a few."""
    from sqlalchemy import event

    from app.api.v1.risk_assessments import _get_owned_assessment_or_404
    from app.risk_assessment.reporting import compute_risk_assessment_report
    from tests.conftest import engine as _test_engine

    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)

    def _assessment_with_n_controls(n: int) -> str:
        assessment, finding = _setup_finding(client, headers, org.id, db_session)
        for i in range(n):
            _create_control(client, headers, org.id, assessment["id"], finding["id"], description=f"Control {i}")
        return assessment["id"]

    small_id = _assessment_with_n_controls(2)
    large_id = _assessment_with_n_controls(15)

    def _count_for(assessment_id: str) -> int:
        count = 0

        def _listener(*args, **kwargs):
            nonlocal count
            count += 1

        event.listen(_test_engine, "before_cursor_execute", _listener)
        try:
            assessment = _get_owned_assessment_or_404(db_session, organization_id=org.id, assessment_id=uuid.UUID(assessment_id))
            compute_risk_assessment_report(db_session, assessment)
        finally:
            event.remove(_test_engine, "before_cursor_execute", _listener)
        return count

    small_count = _count_for(small_id)
    large_count = _count_for(large_id)
    assert small_count == large_count
    assert small_count <= 2
