"""SIE Milestone 26: Formal Enterprise Risk Assessment Engine v0.2 —
dedicated regression suite for the M26-specific additions layered onto
the M25/M25A Risk Assessment domain: `assessment_type`/`reference`,
`ARCHIVED` lifecycle, `linked_action_id` (finding <-> SafetyAction),
inherent/residual risk methodology-version snapshots, and machine-
organization pinning on this API. HTTP-level tests run against the
ordinary SQLite `client` fixture, mirroring `tests/test_risk_assessment_api.py`'s
own established shape. (Transactional-integrity coverage for this
milestone's own additions lives in
`tests/test_risk_assessment_transaction_integrity.py`; the migration's
own upgrade/downgrade/re-upgrade round trip lives in
`tests/test_migrations.py`.)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.ontology_concept import OntologyConcept
from app.models.risk_assessment import RiskAssessment
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
        "title": "M26 Test Assessment",
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


def _history_for(db_session, organization_id, *, assessment_id=None, finding_id=None) -> list[RiskAssessmentHistory]:
    db_session.expire_all()
    stmt = select(RiskAssessmentHistory).where(RiskAssessmentHistory.organization_id == organization_id)
    if assessment_id is not None:
        stmt = stmt.where(RiskAssessmentHistory.assessment_id == assessment_id)
    if finding_id is not None:
        stmt = stmt.where(RiskAssessmentHistory.finding_id == finding_id)
    return list(db_session.execute(stmt).scalars().all())


# --- assessment_type / reference round-trip (item 1) --------------------------------------


@pytest.mark.parametrize(
    "assessment_type", ["BASELINE", "PERIODIC", "INCIDENT_TRIGGERED", "CHANGE_TRIGGERED", "TARGETED"]
)
def test_create_accepts_every_assessment_type(client, db_session, assessment_type):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    body = _create(client, dev_auth_headers(manager.id), org.id, assessment_type=assessment_type)
    assert body["assessment_type"] == assessment_type


def test_create_rejects_an_invalid_assessment_type(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    response = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(assessment_type="NOT_A_REAL_TYPE"),
        headers=dev_auth_headers(manager.id),
    )
    assert response.status_code == 422


def test_create_accepts_and_returns_a_reference(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    body = _create(client, dev_auth_headers(manager.id), org.id, reference="RA-2026-0042")
    assert body["reference"] == "RA-2026-0042"


def test_reference_is_optional(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    body = _create(client, dev_auth_headers(manager.id), org.id)
    assert body["reference"] is None


def test_draft_reference_and_assessment_type_can_be_updated(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id, assessment_type="BASELINE")

    response = client.patch(
        f"{_URL}/{created['id']}?organization_id={org.id}",
        json={"reference": "RA-2026-0099", "assessment_type": "PERIODIC"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reference"] == "RA-2026-0099"
    assert body["assessment_type"] == "PERIODIC"


def test_a_superseding_version_can_carry_its_own_reference_and_assessment_type(client, db_session):
    """`reference` and `assessment_type` (a required field) are supplied
    per-version, exactly like `title` already is -- a superseding version
    is free to restate the same reference/type as its predecessor or
    declare new ones (e.g. an initial BASELINE superseded by a later
    INCIDENT_TRIGGERED reassessment)."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    v1 = _create(client, headers, org.id, reference="RA-2026-0001", assessment_type="PERIODIC")
    client.post(f"{_URL}/{v1['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v1['id']}/approve?organization_id={org.id}", headers=headers)

    v2 = _create(
        client, headers, org.id, supersedes_assessment_id=v1["id"],
        reference="RA-2026-0001", assessment_type="INCIDENT_TRIGGERED",
    )
    assert v2["reference"] == "RA-2026-0001"
    assert v2["assessment_type"] == "INCIDENT_TRIGGERED"


# --- ARCHIVED lifecycle (item 1) -----------------------------------------------------------


@pytest.mark.parametrize("via", ["draft", "in_review", "approved"])
def test_archive_succeeds_from_draft_in_review_or_approved(client, db_session, via):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    if via in ("in_review", "approved"):
        client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    if via == "approved":
        client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)

    response = client.post(f"{_URL}/{created['id']}/archive?organization_id={org.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ARCHIVED"


def test_archived_is_terminal_no_further_transition_is_possible(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/archive?organization_id={org.id}", headers=headers)

    for endpoint in ("submit", "approve", "archive"):
        response = client.post(f"{_URL}/{created['id']}/{endpoint}?organization_id={org.id}", headers=headers)
        assert response.status_code == 422, f"{endpoint} unexpectedly succeeded on an ARCHIVED assessment"


def test_archived_assessment_is_immutable(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/archive?organization_id={org.id}", headers=headers)

    response = client.patch(
        f"{_URL}/{created['id']}?organization_id={org.id}", json={"title": "Nope"}, headers=headers
    )
    assert response.status_code == 422


def test_a_superseded_assessment_cannot_be_archived(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    v1 = _create(client, headers, org.id)
    client.post(f"{_URL}/{v1['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v1['id']}/approve?organization_id={org.id}", headers=headers)
    v2 = _create(client, headers, org.id, supersedes_assessment_id=v1["id"])
    # v1 only actually becomes SUPERSEDED once v2 itself is approved (see
    # `test_supersede_opens_a_new_version_in_the_same_lineage`).
    client.post(f"{_URL}/{v2['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v2['id']}/approve?organization_id={org.id}", headers=headers)

    response = client.get(f"{_URL}/{v1['id']}?organization_id={org.id}", headers=headers)
    assert response.json()["status"] == "SUPERSEDED"

    response = client.post(f"{_URL}/{v1['id']}/archive?organization_id={org.id}", headers=headers)
    assert response.status_code == 422


def test_archive_requires_the_approve_permission_not_merely_write(client, db_session):
    """Archiving is gated on RISK_ASSESSMENT_APPROVE (item 1's own,
    more-privileged design), not RISK_ASSESSMENT_WRITE -- an HSE_ANALYST
    (write, no approve) is rejected."""
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    headers = dev_auth_headers(analyst.id)
    created = _create(client, headers, org.id)

    response = client.post(f"{_URL}/{created['id']}/archive?organization_id={org.id}", headers=headers)
    assert response.status_code == 403


def test_archive_writes_an_audit_log_entry(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)

    client.post(f"{_URL}/{created['id']}/archive?organization_id={org.id}", headers=headers)

    entries = db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == uuid.UUID(created["id"]))
    ).scalars().all()
    assert any(e.action == "RISK_ASSESSMENT_ARCHIVED" for e in entries)


def test_archive_writes_a_history_entry(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)

    client.post(f"{_URL}/{created['id']}/archive?organization_id={org.id}", headers=headers)

    history = _history_for(db_session, org.id, assessment_id=uuid.UUID(created["id"]))
    archived_entries = [h for h in history if h.change_type == "ASSESSMENT_ARCHIVED"]
    assert len(archived_entries) == 1
    assert archived_entries[0].from_status == "DRAFT"
    assert archived_entries[0].to_status == "ARCHIVED"


def test_archive_cross_tenant_assessment_is_404(client, db_session):
    org_a = make_org(db_session, "Archive Org A")
    org_b = make_org(db_session, "Archive Org B")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    created = _create(client, dev_auth_headers(manager_a.id), org_a.id)

    response = client.post(
        f"{_URL}/{created['id']}/archive?organization_id={org_b.id}", headers=dev_auth_headers(manager_b.id)
    )
    assert response.status_code == 404


# --- linked_action_id (item 2's "Action") --------------------------------------------------


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


def test_finding_can_be_linked_to_a_safety_action(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()
    assert finding["linked_action_id"] is None

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"linked_action_id": str(action.id)},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["linked_action_id"] == str(action.id)


def test_finding_can_be_unlinked_from_a_safety_action_via_explicit_null(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()
    client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"linked_action_id": str(action.id)},
        headers=headers,
    )

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"linked_action_id": None},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["linked_action_id"] is None


def test_linking_a_cross_tenant_action_is_rejected(client, db_session):
    org_a = make_org(db_session, "Link Org A")
    org_b = make_org(db_session, "Link Org B")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    foreign_action = _make_action(db_session, org_b.id)
    headers = dev_auth_headers(manager_a.id)
    assessment = _create(client, headers, org_a.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org_a.id}",
        json=_finding_body(db_session), headers=headers,
    ).json()

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org_a.id}",
        json={"linked_action_id": str(foreign_action.id)},
        headers=headers,
    )
    assert response.status_code == 404


def test_linking_writes_history_and_audit_action_linked(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()

    client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"linked_action_id": str(action.id)},
        headers=headers,
    )

    history = _history_for(db_session, org.id, finding_id=uuid.UUID(finding["id"]))
    assert any(h.change_type == "FINDING_ACTION_LINKED" for h in history)
    entries = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org.id, AuditLog.action == "RISK_ASSESSMENT_FINDING_ACTION_LINKED"
        )
    ).scalars().all()
    assert len(entries) == 1
    assert entries[0].event_metadata["linked_action_id"] == str(action.id)


def test_unlinking_writes_history_and_audit_action_unlinked(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    action = _make_action(db_session, org.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()
    client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"linked_action_id": str(action.id)},
        headers=headers,
    )

    client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"linked_action_id": None},
        headers=headers,
    )

    history = _history_for(db_session, org.id, finding_id=uuid.UUID(finding["id"]))
    assert any(h.change_type == "FINDING_ACTION_UNLINKED" for h in history)
    entries = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org.id, AuditLog.action == "RISK_ASSESSMENT_FINDING_ACTION_UNLINKED"
        )
    ).scalars().all()
    assert len(entries) == 1
    assert entries[0].event_metadata["linked_action_id"] is None


# --- methodology-version snapshots (item 6's historical integrity) -------------------------


def test_inherent_rating_snapshots_the_methodology_version(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, likelihood=4, consequence=4),
        headers=headers,
    ).json()
    assert finding["inherent_risk_methodology_version"] == "risk-assessment-v1"
    assert finding["residual_risk_methodology_version"] is None


def test_residual_rating_snapshots_the_methodology_version(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, likelihood=4, consequence=4),
        headers=headers,
    ).json()

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"residual_likelihood": 2, "residual_consequence": 2},
        headers=headers,
    )
    assert response.json()["residual_risk_methodology_version"] == "risk-assessment-v1"


def test_unrated_finding_has_no_methodology_version_snapshot(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()
    assert finding["inherent_risk_methodology_version"] is None
    assert finding["residual_risk_methodology_version"] is None


# --- Machine-organization pinning (item 7) --------------------------------------------------


def test_machine_client_scoped_to_org_a_is_rejected_for_org_b(client, db_session):
    org_a = make_org(db_session, "Pin Org A")
    org_b = make_org(db_session, "Pin Org B")
    credential = _make_client_credential(db_session, org_a.id)

    response = client.post(f"{_URL}?organization_id={org_b.id}", json=_create_body(), headers=_bearer(credential))
    assert response.status_code == 403


def test_machine_client_scoped_to_org_a_can_still_manage_its_own_org(client, db_session):
    org_a = make_org(db_session, "Pin Org A2")
    credential = _make_client_credential(db_session, org_a.id)

    response = client.post(f"{_URL}?organization_id={org_a.id}", json=_create_body(), headers=_bearer(credential))
    assert response.status_code == 201


def test_machine_client_pinning_also_applies_to_read(client, db_session):
    org_a = make_org(db_session, "Pin Org A3")
    org_b = make_org(db_session, "Pin Org B3")
    credential = _make_client_credential(db_session, org_a.id)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    foreign = _create(client, dev_auth_headers(manager_b.id), org_b.id)

    response = client.get(f"{_URL}/{foreign['id']}?organization_id={org_b.id}", headers=_bearer(credential))
    assert response.status_code == 403
