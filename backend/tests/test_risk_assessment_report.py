"""SIE Milestone 28: Enterprise Risk Assessment Reporting & Decision
Intelligence v0.1 — dedicated regression suite for
`GET /risk-assessments/{id}/report` and `/readiness`. HTTP-level tests
run against the ordinary SQLite `client` fixture, mirroring
`tests/test_risk_assessment_m27.py`'s own established shape.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select

from app.models.audit_log import AuditLog  # noqa: F401 (kept for parity with sibling test files)
from app.models.ontology_concept import OntologyConcept
from app.models.safety_action import SafetyAction
from app.services import ontology_governance_service as ogs
from app.services.api_client_service import api_client_service
from app.services.permissions import OrganizationRole, Permission
from tests.conftest import dev_auth_headers, engine as _test_engine
from tests.intelligence_test_helpers import (
    make_org,
    make_org_member,
    make_platform_admin_user,
    seed_risk_area_ontology_concepts,
)

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
        "title": "M28 Report Test Assessment",
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


def _finding_body(db_session, concept_key: str = "VEHICLE_INCIDENT", **overrides) -> dict:
    body = {"risk_area_concept_id": _risk_area_concept_id(db_session, concept_key), "title": "A finding"}
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


def _link(client, headers, org_id, assessment_id, finding_id, action_id) -> None:
    response = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/actions/link?organization_id={org_id}",
        json={"action_id": str(action_id)}, headers=headers,
    )
    assert response.status_code == 200, response.text


def _report(client, headers, org_id, assessment_id) -> dict:
    response = client.get(f"{_URL}/{assessment_id}/report?organization_id={org_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _readiness(client, headers, org_id, assessment_id):
    return client.get(f"{_URL}/{assessment_id}/readiness?organization_id={org_id}", headers=headers)


@contextmanager
def _count_queries():
    count = 0

    def _before_cursor_execute(*args, **kwargs):
        nonlocal count
        count += 1

    event.listen(_test_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield lambda: count
    finally:
        event.remove(_test_engine, "before_cursor_execute", _before_cursor_execute)


# --- Functional: assessment summary / empty / unrated --------------------------------------


def test_empty_assessment_report(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    report = _report(client, headers, org.id, assessment["id"])
    assert report["assessment_summary"]["finding_count"] == 0
    assert report["assessment_summary"]["findings_by_status"] == {"OPEN": 0, "ADDRESSED": 0, "CLOSED": 0}
    assert report["risk_distribution"]["inherent"] == {"critical": 0, "high": 0, "moderate": 0, "low": 0, "unrated": 0}
    assert report["risk_distribution"]["residual"] == {"critical": 0, "high": 0, "moderate": 0, "low": 0, "unrated": 0}
    assert report["risk_areas"] == []
    assert report["evidence_coverage"]["total_findings"] == 0
    assert report["evidence_coverage"]["findings_with_no_evidence"] == 0
    assert report["action_response_summary"]["total_response_actions"] == 0
    assert report["readiness"]["status"] == "NOT_READY"
    assert report["readiness"]["has_no_findings"] is True
    assert any("no findings" in r.lower() for r in report["readiness"]["reasons"])


def test_assessment_summary_identity_fields(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id, reference="RA-2026-0777", assessment_type="PERIODIC")

    report = _report(client, headers, org.id, assessment["id"])
    assert report["id"] == assessment["id"]
    assert report["reference"] == "RA-2026-0777"
    assert report["assessment_type"] == "PERIODIC"
    assert report["status"] == "DRAFT"
    assert report["methodology_version"] == assessment["methodology_version"]
    assert report["version"] == 1
    assert report["lineage_id"] == assessment["lineage_id"]


def test_unrated_findings_counted_correctly(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    _create_finding(client, headers, org.id, assessment["id"], db_session)  # unrated
    _create_finding(client, headers, org.id, assessment["id"], db_session, likelihood=4, consequence=4)  # rated

    report = _report(client, headers, org.id, assessment["id"])
    assert report["assessment_summary"]["finding_count"] == 2
    assert report["assessment_summary"]["unrated_finding_count"] == 1
    assert report["risk_distribution"]["inherent"]["unrated"] == 1
    assert report["risk_distribution"]["inherent"]["high"] == 1


# --- Functional: risk distribution ---------------------------------------------------------


def test_risk_distribution_distinguishes_inherent_and_residual(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    critical = _create_finding(client, headers, org.id, assessment["id"], db_session, likelihood=5, consequence=5)
    client.patch(
        f"{_URL}/{assessment['id']}/findings/{critical['id']}?organization_id={org.id}",
        json={"residual_likelihood": 2, "residual_consequence": 2}, headers=headers,
    )
    _create_finding(client, headers, org.id, assessment["id"], db_session, likelihood=1, consequence=1)  # LOW, no residual

    report = _report(client, headers, org.id, assessment["id"])
    assert report["risk_distribution"]["inherent"]["critical"] == 1
    assert report["risk_distribution"]["inherent"]["low"] == 1
    assert report["risk_distribution"]["inherent"]["unrated"] == 0
    # Residual: one finding rated LOW (2x2=4), one never given a residual rating at all.
    assert report["risk_distribution"]["residual"]["low"] == 1
    assert report["risk_distribution"]["residual"]["critical"] == 0
    assert report["risk_distribution"]["residual"]["unrated"] == 1


# --- Functional: risk-area aggregation ------------------------------------------------------


def test_risk_area_aggregation(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    f1 = _create_finding(
        client, headers, org.id, assessment["id"], db_session, concept_key="VEHICLE_INCIDENT",
        likelihood=4, consequence=4,
    )
    f2 = _create_finding(
        client, headers, org.id, assessment["id"], db_session, concept_key="VEHICLE_INCIDENT",
        likelihood=2, consequence=2,
    )
    close_response = client.post(
        f"{_URL}/{assessment['id']}/findings/{f2['id']}/close?organization_id={org.id}",
        json={"closure_reason": "Residual risk assessed as acceptable after controls verified."},
        headers=headers,
    )
    assert close_response.status_code == 200
    _create_finding(
        client, headers, org.id, assessment["id"], db_session, concept_key="PPE_COMPLIANCE",
        likelihood=1, consequence=1,
    )
    _link(client, headers, org.id, assessment["id"], f1["id"], action.id)

    report = _report(client, headers, org.id, assessment["id"])
    areas = {a["concept_key"]: a for a in report["risk_areas"]}
    assert set(areas) == {"VEHICLE_INCIDENT", "PPE_COMPLIANCE"}
    vehicle = areas["VEHICLE_INCIDENT"]
    assert vehicle["finding_count"] == 2
    assert vehicle["highest_inherent_risk_score"] == 16
    assert vehicle["highest_inherent_risk_classification"] == "HIGH"
    assert vehicle["open_finding_count"] == 1
    assert vehicle["closed_finding_count"] == 1
    assert vehicle["associated_action_count"] == 1
    ppe = areas["PPE_COMPLIANCE"]
    assert ppe["finding_count"] == 1
    assert ppe["associated_action_count"] == 0


# --- Functional: action response summary / multiple actions --------------------------------


def test_action_response_summary_no_one_multiple(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action_a = _make_action(db_session, org.id, title="A")
    action_b = _make_action(db_session, org.id, title="B")
    assessment = _create(client, headers, org.id)
    no_action = _create_finding(client, headers, org.id, assessment["id"], db_session)
    one_action = _create_finding(client, headers, org.id, assessment["id"], db_session)
    multi_action = _create_finding(client, headers, org.id, assessment["id"], db_session)
    _link(client, headers, org.id, assessment["id"], one_action["id"], action_a.id)
    _link(client, headers, org.id, assessment["id"], multi_action["id"], action_a.id)
    _link(client, headers, org.id, assessment["id"], multi_action["id"], action_b.id)

    report = _report(client, headers, org.id, assessment["id"])
    summary = report["action_response_summary"]
    assert summary["findings_with_no_response_action"] == 1
    assert summary["findings_with_one_response_action"] == 1
    assert summary["findings_with_multiple_response_actions"] == 1
    assert summary["total_response_actions"] == 2


def test_action_response_summary_completed_outstanding_overdue(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    now = datetime.now(timezone.utc)
    completed = _make_action(db_session, org.id, title="Completed", status="COMPLETED")
    cancelled = _make_action(db_session, org.id, title="Cancelled", status="CANCELLED")
    outstanding = _make_action(db_session, org.id, title="Outstanding", due_date=now + timedelta(days=5))
    overdue = _make_action(db_session, org.id, title="Overdue", due_date=now - timedelta(days=5))
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session)
    for action in (completed, cancelled, outstanding, overdue):
        _link(client, headers, org.id, assessment["id"], finding["id"], action.id)

    report = _report(client, headers, org.id, assessment["id"])
    summary = report["action_response_summary"]
    assert summary["completed_response_actions"] == 1
    assert summary["cancelled_response_actions"] == 1
    assert summary["outstanding_response_actions"] == 1
    assert summary["overdue_response_actions"] == 1
    assert summary["total_response_actions"] == 4


# --- Functional: evidence coverage ----------------------------------------------------------


def test_evidence_coverage(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    action = _make_action(db_session, org.id)

    no_evidence = _create_finding(client, headers, org.id, assessment["id"], db_session)
    event_only = _create_finding(
        client, headers, org.id, assessment["id"], db_session,
        evidence=[{"evidence_type": "ANOMALY", "reference_label": "anomaly:incident_count"}],
    )
    action_only = _create_finding(
        client, headers, org.id, assessment["id"], db_session,
        evidence=[{"evidence_type": "ACTION", "reference_id": str(action.id)}],
    )
    multi = _create_finding(
        client, headers, org.id, assessment["id"], db_session,
        evidence=[
            {"evidence_type": "ACTION", "reference_id": str(action.id)},
            {"evidence_type": "ANOMALY", "reference_label": "anomaly:incident_count"},
        ],
    )

    report = _report(client, headers, org.id, assessment["id"])
    coverage = report["evidence_coverage"]
    assert coverage["total_findings"] == 4
    assert coverage["findings_with_no_evidence"] == 1
    assert coverage["findings_with_intelligence_evidence"] == 2  # event_only (ANOMALY) + multi
    assert coverage["findings_with_action_evidence"] == 2  # action_only + multi
    assert coverage["findings_with_multiple_evidence_types"] == 1  # multi only
    assert coverage["findings_with_event_evidence"] == 0
    assert coverage["findings_with_knowledge_evidence"] == 0


# --- Functional: readiness -------------------------------------------------------------------


def test_readiness_ready_when_all_conditions_met(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(
        client, headers, org.id, assessment["id"], db_session, likelihood=2, consequence=2,
        evidence=[{"evidence_type": "ACTION", "reference_id": str(action.id)}],
    )
    _link(client, headers, org.id, assessment["id"], finding["id"], action.id)

    report = _report(client, headers, org.id, assessment["id"])
    assert report["readiness"]["status"] == "READY"
    assert report["readiness"]["reasons"] == []


def test_readiness_not_ready_unrated_finding(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    _create_finding(client, headers, org.id, assessment["id"], db_session)

    report = _report(client, headers, org.id, assessment["id"])
    assert report["readiness"]["status"] == "NOT_READY"
    assert report["readiness"]["unrated_finding_count"] == 1
    assert any("unrated" in r.lower() for r in report["readiness"]["reasons"])


def test_readiness_not_ready_high_risk_finding_without_action(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    _create_finding(
        client, headers, org.id, assessment["id"], db_session, likelihood=5, consequence=5,
        evidence=[{"evidence_type": "ANOMALY", "reference_label": "anomaly:incident_count"}],
    )

    report = _report(client, headers, org.id, assessment["id"])
    assert report["readiness"]["status"] == "NOT_READY"
    assert report["readiness"]["unresolved_high_risk_finding_count"] == 1
    assert report["readiness"]["high_risk_findings_without_action_count"] == 1


def test_readiness_never_recommends_approval(client, db_session):
    """Item 6's own explicit boundary: the readiness result states facts,
    never a recommendation."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    _create_finding(client, headers, org.id, assessment["id"], db_session)

    report = _report(client, headers, org.id, assessment["id"])
    joined = " ".join(report["readiness"]["reasons"]).lower()
    assert "recommend" not in joined
    assert "approv" not in joined
    assert report["readiness"]["status"] in ("READY", "NOT_READY")


def test_readiness_dedicated_endpoint(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    response = _readiness(client, headers, org.id, assessment["id"])
    assert response.status_code == 200
    body = response.json()
    assert body["assessment_id"] == assessment["id"]
    assert body["readiness"]["status"] == "NOT_READY"
    assert body["readiness"]["has_no_findings"] is True


# --- Functional: closed findings -------------------------------------------------------------


def test_closed_findings_excluded_from_unresolved_high_risk(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session, likelihood=5, consequence=5)
    close = client.post(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/close?organization_id={org.id}",
        json={"closure_reason": "Residual risk verified acceptable."}, headers=headers,
    )
    assert close.status_code == 200

    report = _report(client, headers, org.id, assessment["id"])
    assert report["assessment_summary"]["findings_by_status"]["CLOSED"] == 1
    assert report["readiness"]["unresolved_high_risk_finding_count"] == 0


# --- Security -------------------------------------------------------------------------------


def test_report_same_tenant_access_succeeds(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    viewer = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    assessment = _create(client, dev_auth_headers(manager.id), org.id)

    response = client.get(
        f"{_URL}/{assessment['id']}/report?organization_id={org.id}", headers=dev_auth_headers(viewer.id)
    )
    assert response.status_code == 200


def test_report_cross_tenant_is_404(client, db_session):
    org_a = make_org(db_session, "M28 Org A")
    org_b = make_org(db_session, "M28 Org B")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    assessment = _create(client, dev_auth_headers(manager_a.id), org_a.id)

    response = client.get(
        f"{_URL}/{assessment['id']}/report?organization_id={org_b.id}", headers=dev_auth_headers(manager_b.id)
    )
    assert response.status_code == 404


def test_report_nonexistent_assessment_is_404(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    response = client.get(
        f"{_URL}/{uuid.uuid4()}/report?organization_id={org.id}", headers=dev_auth_headers(manager.id)
    )
    assert response.status_code == 404


def test_report_machine_client_pinning(client, db_session):
    org_a = make_org(db_session, "M28 Pin Org A")
    org_b = make_org(db_session, "M28 Pin Org B")
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    assessment = _create(client, dev_auth_headers(manager_b.id), org_b.id)
    credential = _make_client_credential(db_session, org_a.id)

    response = client.get(
        f"{_URL}/{assessment['id']}/report?organization_id={org_b.id}", headers=_bearer(credential)
    )
    assert response.status_code == 403


def test_report_machine_client_with_read_scope_succeeds(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    assessment = _create(client, dev_auth_headers(manager.id), org.id)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.RISK_ASSESSMENT_READ])

    response = client.get(f"{_URL}/{assessment['id']}/report?organization_id={org.id}", headers=_bearer(credential))
    assert response.status_code == 200


def test_report_permission_enforcement_machine_without_read_scope(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    assessment = _create(client, dev_auth_headers(manager.id), org.id)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.INTELLIGENCE_READ])

    response = client.get(f"{_URL}/{assessment['id']}/report?organization_id={org.id}", headers=_bearer(credential))
    assert response.status_code == 403


def test_readiness_cross_tenant_is_404(client, db_session):
    org_a = make_org(db_session, "M28 Readiness Org A")
    org_b = make_org(db_session, "M28 Readiness Org B")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    assessment = _create(client, dev_auth_headers(manager_a.id), org_a.id)

    response = _readiness(client, dev_auth_headers(manager_b.id), org_b.id, assessment["id"])
    assert response.status_code == 404


# --- Historical integrity ---------------------------------------------------------------------


def test_approved_assessment_report_remains_stable(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    _create_finding(client, headers, org.id, assessment["id"], db_session, likelihood=3, consequence=3)
    client.post(f"{_URL}/{assessment['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{assessment['id']}/approve?organization_id={org.id}", headers=headers)

    first = _report(client, headers, org.id, assessment["id"])
    second = _report(client, headers, org.id, assessment["id"])
    # generated_at legitimately differs between the two calls -- strip it
    # before comparing everything else, which must be byte-identical.
    first.pop("generated_at")
    second.pop("generated_at")
    first["action_response_summary"].pop("computed_at")
    second["action_response_summary"].pop("computed_at")
    assert first == second


def test_new_assessment_version_does_not_alter_previous_findings_report(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    v1 = _create(client, headers, org.id)
    _create_finding(client, headers, org.id, v1["id"], db_session, likelihood=4, consequence=4)
    client.post(f"{_URL}/{v1['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v1['id']}/approve?organization_id={org.id}", headers=headers)

    before = _report(client, headers, org.id, v1["id"])

    # Opening a new version (existing M25 behavior: v2 starts with zero
    # findings of its own) must not alter v1's own report in any way.
    v2 = _create(client, headers, org.id, supersedes_assessment_id=v1["id"])
    assert v2["findings"] == []

    after = _report(client, headers, org.id, v1["id"])
    before.pop("generated_at")
    after.pop("generated_at")
    before["action_response_summary"].pop("computed_at")
    after["action_response_summary"].pop("computed_at")
    assert before == after
    assert after["assessment_summary"]["finding_count"] == 1


def test_deprecated_ontology_concept_still_correctly_represented(client, db_session):
    org = make_org(db_session)
    admin = make_platform_admin_user(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    concept = ogs.propose_concept(
        db_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="M28_DEPRECATION_TEST",
        definition="d", justification="j", acting_user_id=admin.id, is_risk_area_eligible=True,
    )
    ogs.approve_concept(db_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)

    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json={"risk_area_concept_id": str(concept.id), "title": "Finding on a soon-to-be-deprecated concept"},
        headers=headers,
    )
    assert finding.status_code == 201

    ogs.deprecate_concept(db_session, concept_id=concept.id, acting_user_id=admin.id, reason="No longer needed.")

    report = _report(client, headers, org.id, assessment["id"])
    areas = {a["concept_key"]: a for a in report["risk_areas"]}
    assert "M28_DEPRECATION_TEST" in areas
    assert areas["M28_DEPRECATION_TEST"]["finding_count"] == 1
    assert areas["M28_DEPRECATION_TEST"]["label"] == "M28 Deprecation Test"


def test_methodology_version_remains_correct(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    original_version = assessment["methodology_version"]

    monkeypatch.setattr("app.core.config.settings.RISK_ASSESSMENT_METHODOLOGY_VERSION", "risk-assessment-v99")

    report = _report(client, headers, org.id, assessment["id"])
    assert report["methodology_version"] == original_version
    assert report["methodology_version"] != "risk-assessment-v99"


# --- Action semantics -------------------------------------------------------------------------


def test_completed_action_never_automatically_closes_finding(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = _create_finding(client, headers, org.id, assessment["id"], db_session, likelihood=4, consequence=4)
    _link(client, headers, org.id, assessment["id"], finding["id"], action.id)

    action.status = "COMPLETED"
    db_session.add(action)
    db_session.commit()

    report = _report(client, headers, org.id, assessment["id"])
    assert report["assessment_summary"]["findings_by_status"]["OPEN"] == 1
    assert report["assessment_summary"]["findings_by_status"]["CLOSED"] == 0
    assert report["action_response_summary"]["completed_response_actions"] == 1


def test_current_action_status_distinct_from_historical_assessment_state(client, db_session):
    """Item 7: `action_response_summary.computed_at` is the *current*
    instant this section was computed at -- never pinned to the
    assessment's own, historical `as_of`."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    past_as_of = datetime.now(timezone.utc) - timedelta(days=180)
    assessment = _create(client, headers, org.id, as_of=past_as_of.isoformat())

    report = _report(client, headers, org.id, assessment["id"])
    computed_at = datetime.fromisoformat(report["action_response_summary"]["computed_at"])
    assessment_as_of = datetime.fromisoformat(report["as_of"])
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    if assessment_as_of.tzinfo is None:
        assessment_as_of = assessment_as_of.replace(tzinfo=timezone.utc)
    assert (computed_at - assessment_as_of) > timedelta(days=170)


# --- Performance ------------------------------------------------------------------------------


def test_report_query_count_does_not_grow_with_finding_count(client, db_session):
    from app.api.v1.risk_assessments import _get_owned_assessment_or_404
    from app.risk_assessment.reporting import compute_risk_assessment_report

    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)

    def _build_assessment(finding_count: int) -> str:
        assessment = _create(client, headers, org.id, title=f"Perf test {finding_count}")
        action = _make_action(db_session, org.id, title=f"Action for {finding_count}")
        for i in range(finding_count):
            finding = _create_finding(
                client, headers, org.id, assessment["id"], db_session, likelihood=(i % 5) + 1, consequence=(i % 5) + 1,
                evidence=[{"evidence_type": "ACTION", "reference_id": str(action.id)}],
            )
            _link(client, headers, org.id, assessment["id"], finding["id"], action.id)
        return assessment["id"]

    small_id = _build_assessment(3)
    large_id = _build_assessment(20)

    def _query_count(assessment_id: str) -> int:
        with _count_queries() as get_count:
            assessment = _get_owned_assessment_or_404(
                db_session, organization_id=org.id, assessment_id=uuid.UUID(assessment_id)
            )
            compute_risk_assessment_report(db_session, assessment)
        return get_count()

    small_count = _query_count(small_id)
    large_count = _query_count(large_id)

    assert small_count == large_count, (
        f"query count grew with finding count: {small_count} (3 findings) vs {large_count} (20 findings) -- "
        "an N+1 query almost certainly crept in"
    )
    # Exactly two: one for the assessment+findings+evidence+controls+
    # risk_area_concept join, one for the finding<->action relationship
    # join -- see app/risk_assessment/reporting.py's own module docstring.
    assert small_count <= 2
