"""SIE Milestone 29A: Risk Assessment Control Effectiveness Mutation
Integrity Correction v0.1 — dedicated regression suite proving that
`RiskAssessmentControl.effectiveness` now has exactly one authoritative
mutation path: `POST .../controls/{control_id}/assess-effectiveness`.

The legacy SIE Milestone 25 bulk-replace-via-finding-PATCH path
(`PATCH .../findings/{finding_id}` with a `controls` array) previously
let a client set `effectiveness` directly, with none of the SIE
Milestone 29 governance requirements (explicit rating, non-blank
rationale, attribution, timestamp, history, audit, idempotency) --
a second, ungoverned mutation path for the same semantic field. This
file proves that path is now closed at the schema level (structural
enforcement, not merely "ignored if sent"), that every other legitimate
legacy behavior is unaffected, and that the dedicated SIE Milestone 29
endpoint remains fully functional and is the only place
`RiskAssessmentControl.effectiveness` can ever change.

HTTP-level tests run against the ordinary SQLite `client` fixture,
mirroring `tests/test_risk_assessment_m29.py`'s own established shape
and reusing its helper conventions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.risk_assessment import RiskAssessmentControl
from app.models.risk_assessment_history import RiskAssessmentHistory
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
        "title": "M29A Test Assessment",
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
    from app.models.ontology_concept import OntologyConcept

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


def _setup_finding(client, headers, org_id, db_session, **overrides) -> tuple[dict, dict]:
    assessment = _create(client, headers, org_id)
    finding = _create_finding(client, headers, org_id, assessment["id"], db_session, **overrides)
    return assessment, finding


def _control_body(**overrides) -> dict:
    body = {"description": "Guardrail installed at loading dock", "control_type": "ENGINEERING"}
    body.update(overrides)
    return body


def _create_control(client, headers, org_id, assessment_id, finding_id, **overrides) -> dict:
    response = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org_id}",
        json=_control_body(**overrides), headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assess_body(**overrides) -> dict:
    body = {"effectiveness_rating": "EFFECTIVE", "effectiveness_rationale": "Verified during site walkthrough."}
    body.update(overrides)
    return body


def _assess(client, headers, org_id, assessment_id, finding_id, control_id, **overrides):
    return client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/controls/{control_id}/assess-effectiveness"
        f"?organization_id={org_id}",
        json=_assess_body(**overrides), headers=headers,
    )


def _legacy_patch_controls(client, headers, org_id, assessment_id, finding_id, controls: list[dict]):
    return client.patch(
        f"{_URL}/{assessment_id}/findings/{finding_id}?organization_id={org_id}",
        json={"controls": controls}, headers=headers,
    )


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


# --- 1/2/3: legacy path closed at the schema level, not silently ignored ------------------------


@pytest.mark.parametrize("effectiveness_value", ["EFFECTIVE", "PARTIALLY_EFFECTIVE", "INEFFECTIVE", "NOT_ASSESSED"])
def test_legacy_finding_patch_rejects_effectiveness_in_control_payload(client, db_session, effectiveness_value):
    """Items 1-3: a legacy `controls` payload containing `effectiveness`
    is rejected by schema validation (`422`), never silently discarded
    and never silently applied."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)

    response = _legacy_patch_controls(
        client, headers, org.id, assessment["id"], finding["id"],
        [_control_body(effectiveness=effectiveness_value)],
    )
    assert response.status_code == 422
    # Structural enforcement: the field doesn't exist on the schema at
    # all, so the 422 names it, not some unrelated validation failure.
    assert "effectiveness" in response.text


def test_important_requirement_legacy_update_never_changes_existing_control_effectiveness_db_value(
    client, db_session
):
    """IMPORTANT TEST REQUIREMENT: a legacy finding update containing a
    changed `effectiveness` value must NOT result in
    `RiskAssessmentControl.effectiveness` being changed. Verifies the
    database value remains exactly what it was before the request --
    not merely that the HTTP response looks right."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    # Give the control a real, attributed assessment first via the one
    # authoritative path, so there is a genuine "before" value that a
    # regression would visibly clobber.
    _assess(client, headers, org.id, assessment["id"], finding["id"], control["id"], effectiveness_rating="EFFECTIVE")

    row_before = db_session.get(RiskAssessmentControl, uuid.UUID(control["id"]))
    db_session.expire_all()
    row_before = db_session.get(RiskAssessmentControl, uuid.UUID(control["id"]))
    effectiveness_before = row_before.effectiveness
    rationale_before = row_before.effectiveness_rationale
    assessed_at_before = row_before.assessed_at
    assessed_by_before = row_before.assessed_by_user_id

    response = _legacy_patch_controls(
        client, headers, org.id, assessment["id"], finding["id"],
        [_control_body(description="Attempted override", effectiveness="INEFFECTIVE")],
    )
    assert response.status_code == 422

    db_session.expire_all()
    row_after = db_session.get(RiskAssessmentControl, uuid.UUID(control["id"]))
    assert row_after is not None, "the 422 must not have deleted the original control either"
    assert row_after.effectiveness == effectiveness_before
    assert row_after.effectiveness_rationale == rationale_before
    assert row_after.assessed_at == assessed_at_before
    assert row_after.assessed_by_user_id == assessed_by_before
    assert row_after.description != "Attempted override"  # bulk-replace never even ran


# --- 4: legitimate legacy metadata mutation remains functional -----------------------------------


def test_legacy_finding_patch_still_replaces_legitimate_control_metadata(client, db_session):
    """Item 4: description, control_type, status, owner_user_id, and
    reference remain mutable through the legacy bulk-replace path when
    `effectiveness` is not part of the payload -- this correction closes
    exactly one field, nothing else."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)

    response = _legacy_patch_controls(
        client, headers, org.id, assessment["id"], finding["id"],
        [
            {
                "description": "Fall arrest system",
                "control_type": "PPE",
                "status": "IN_PLACE",
                "owner_user_id": str(owner.id),
                "reference": "SOP-114",
            }
        ],
    )
    assert response.status_code == 200, response.text
    control = response.json()["controls"][0]
    assert control["description"] == "Fall arrest system"
    assert control["control_type"] == "PPE"
    assert control["status"] == "IN_PLACE"
    assert control["owner_user_id"] == str(owner.id)
    assert control["reference"] == "SOP-114"
    assert control["effectiveness"] == "NOT_ASSESSED"  # never silently inherited/guessed


# --- 5-12: dedicated M29 endpoint remains the fully functional, sole authority -------------------


def test_dedicated_endpoint_changes_effectiveness(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = _assess(client, headers, org.id, assessment["id"], finding["id"], control["id"])
    assert response.status_code == 200
    assert response.json()["effectiveness"] == "EFFECTIVE"


def test_dedicated_endpoint_requires_nonblank_rationale(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = _assess(
        client, headers, org.id, assessment["id"], finding["id"], control["id"], effectiveness_rationale="   "
    )
    assert response.status_code == 422


def test_dedicated_endpoint_rejects_not_assessed(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = _assess(
        client, headers, org.id, assessment["id"], finding["id"], control["id"], effectiveness_rating="NOT_ASSESSED"
    )
    assert response.status_code == 422


def test_dedicated_endpoint_records_assessed_at(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = _assess(client, headers, org.id, assessment["id"], finding["id"], control["id"])
    assert response.json()["assessed_at"] is not None


def test_dedicated_endpoint_records_assessed_by_user_id(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = _assess(client, headers, org.id, assessment["id"], finding["id"], control["id"])
    assert response.json()["assessed_by_user_id"] == str(manager.id)


def test_dedicated_endpoint_records_history(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    _assess(client, headers, org.id, assessment["id"], finding["id"], control["id"])

    history = _history_for(db_session, org.id, control_id=uuid.UUID(control["id"]))
    assert any(h.change_type == "CONTROL_EFFECTIVENESS_ASSESSED" for h in history)


def test_dedicated_endpoint_records_audit_log(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])

    _assess(client, headers, org.id, assessment["id"], finding["id"], control["id"])

    rows = _audit_rows(db_session, org.id, "RISK_ASSESSMENT_CONTROL_EFFECTIVENESS_ASSESSED")
    assert len(rows) == 1


def test_dedicated_endpoint_remains_idempotent(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    key_headers = {**headers, "Idempotency-Key": "m29a-assess-replay"}

    first = _assess(client, key_headers, org.id, assessment["id"], finding["id"], control["id"])
    second = _assess(client, key_headers, org.id, assessment["id"], finding["id"], control["id"])
    assert first.status_code == second.status_code == 200
    assert first.json()["assessed_at"] == second.json()["assessed_at"]

    rows = _audit_rows(db_session, org.id, "RISK_ASSESSMENT_CONTROL_EFFECTIVENESS_ASSESSED")
    assert len(rows) == 1  # the replay wrote nothing new


# --- 13: legacy path cannot bypass transaction/audit/history by changing effectiveness -----------


def test_legacy_path_writes_no_effectiveness_history_or_audit_when_rejected(client, db_session):
    """Item 13: since the legacy payload is rejected before the route
    body ever executes, it never enters `assessment_mutation_transaction()`
    -- no CONTROL_EFFECTIVENESS_ASSESSED history row, no matching audit
    row, for any control, anywhere in the organization."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    _create_control(client, headers, org.id, assessment["id"], finding["id"])

    response = _legacy_patch_controls(
        client, headers, org.id, assessment["id"], finding["id"], [_control_body(effectiveness="EFFECTIVE")]
    )
    assert response.status_code == 422

    history = _history_for(db_session, org.id)
    assert not any(h.change_type == "CONTROL_EFFECTIVENESS_ASSESSED" for h in history)
    assert not _audit_rows(db_session, org.id, "RISK_ASSESSMENT_CONTROL_EFFECTIVENESS_ASSESSED")


# --- 14: tenant isolation remains intact ----------------------------------------------------------


def test_cross_tenant_legacy_patch_control_effectiveness_rejected(client, db_session):
    org_a = make_org(db_session, "M29A Org A")
    org_b = make_org(db_session, "M29A Org B")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    headers_a = dev_auth_headers(manager_a.id)
    headers_b = dev_auth_headers(manager_b.id)
    assessment, finding = _setup_finding(client, headers_a, org_a.id, db_session)

    response = _legacy_patch_controls(
        client, headers_b, org_a.id, assessment["id"], finding["id"], [_control_body()]
    )
    assert response.status_code in (403, 404)


def test_cross_tenant_dedicated_assess_effectiveness_rejected(client, db_session):
    org_a = make_org(db_session, "M29A Org C")
    org_b = make_org(db_session, "M29A Org D")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    headers_a = dev_auth_headers(manager_a.id)
    headers_b = dev_auth_headers(manager_b.id)
    assessment, finding = _setup_finding(client, headers_a, org_a.id, db_session)
    control = _create_control(client, headers_a, org_a.id, assessment["id"], finding["id"])

    response = _assess(client, headers_b, org_a.id, assessment["id"], finding["id"], control["id"])
    assert response.status_code in (403, 404)

    row = db_session.get(RiskAssessmentControl, uuid.UUID(control["id"]))
    assert row.effectiveness == "NOT_ASSESSED"


# --- 15/16/17: APPROVED/SUPERSEDED/ARCHIVED effectiveness immutability ---------------------------


def test_approved_assessment_control_effectiveness_immutable(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    client.post(f"{_URL}/{assessment['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{assessment['id']}/approve?organization_id={org.id}", headers=headers)

    legacy = _legacy_patch_controls(
        client, headers, org.id, assessment["id"], finding["id"], [_control_body()]
    )
    dedicated = _assess(client, headers, org.id, assessment["id"], finding["id"], control["id"])
    assert legacy.status_code == 422
    assert dedicated.status_code == 422

    row = db_session.get(RiskAssessmentControl, uuid.UUID(control["id"]))
    assert row.effectiveness == "NOT_ASSESSED"


def test_superseded_assessment_control_effectiveness_immutable(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    v1, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, v1["id"], finding["id"])
    client.post(f"{_URL}/{v1['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v1['id']}/approve?organization_id={org.id}", headers=headers)
    v2 = _create(client, headers, org.id, supersedes_assessment_id=v1["id"])
    client.post(f"{_URL}/{v2['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v2['id']}/approve?organization_id={org.id}", headers=headers)

    refreshed = client.get(f"{_URL}/{v1['id']}?organization_id={org.id}", headers=headers).json()
    assert refreshed["status"] == "SUPERSEDED"

    dedicated = _assess(client, headers, org.id, v1["id"], finding["id"], control["id"])
    assert dedicated.status_code == 422

    row = db_session.get(RiskAssessmentControl, uuid.UUID(control["id"]))
    assert row.effectiveness == "NOT_ASSESSED"


def test_archived_assessment_control_effectiveness_immutable(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)
    control = _create_control(client, headers, org.id, assessment["id"], finding["id"])
    archived = client.post(f"{_URL}/{assessment['id']}/archive?organization_id={org.id}", headers=headers)
    assert archived.status_code == 200

    legacy = _legacy_patch_controls(
        client, headers, org.id, assessment["id"], finding["id"], [_control_body()]
    )
    dedicated = _assess(client, headers, org.id, assessment["id"], finding["id"], control["id"])
    assert legacy.status_code == 422
    assert dedicated.status_code == 422

    row = db_session.get(RiskAssessmentControl, uuid.UUID(control["id"]))
    assert row.effectiveness == "NOT_ASSESSED"


# --- 18/19: pre-M29A/pre-M29 historical data preserved and readable ------------------------------


def test_preexisting_control_with_null_rationale_and_attribution_remains_unchanged(client, db_session):
    """Items 18/19: a control whose `effectiveness` was set through the
    (now-closed) legacy path before this correction shipped is valid
    historical state -- `effectiveness_rationale`/`assessed_at`/
    `assessed_by_user_id` stay `NULL`, and this correction never
    fabricates or backfills them. Simulated here by writing the row
    directly, exactly as it would have looked pre-M29A."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment, finding = _setup_finding(client, headers, org.id, db_session)

    legacy_control = RiskAssessmentControl(
        organization_id=org.id,
        finding_id=uuid.UUID(finding["id"]),
        description="Pre-existing legacy control",
        control_type="ADMINISTRATIVE",
        status="IN_PLACE",
        effectiveness="EFFECTIVE",
    )
    db_session.add(legacy_control)
    db_session.commit()
    db_session.refresh(legacy_control)

    response = client.get(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}/controls/{legacy_control.id}"
        f"?organization_id={org.id}",
        headers=headers,
    )
    assert response.status_code == 200
    control = response.json()
    assert control["effectiveness"] == "EFFECTIVE"
    assert control["effectiveness_rationale"] is None
    assert control["assessed_at"] is None
    assert control["assessed_by_user_id"] is None

    db_session.expire_all()
    row = db_session.get(RiskAssessmentControl, legacy_control.id)
    assert row.effectiveness == "EFFECTIVE"
    assert row.effectiveness_rationale is None
    assert row.assessed_at is None
    assert row.assessed_by_user_id is None
