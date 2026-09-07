"""Transactional-integrity regression tests — SIE Milestone 29:
Enterprise Risk Assessment Evidence & Control Effectiveness Foundation
v0.1, "control mutations use one transaction." Mirrors
`tests/test_risk_assessment_m27_transaction_integrity.py`'s own
established pattern exactly: failure is injected with
`monkeypatch.setattr()` on the exact names `app/api/v1/risk_assessments.py`
imported, every assertion re-reads from the database through a session
independent of the one the failing request used (`db_session`, expired
before each read), and a standalone `TestClient(app,
raise_server_exceptions=False)` is used so the deliberately-injected
failure surfaces as the `500` response this module asserts on rather
than a test error.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from starlette.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.idempotency_key import IdempotencyKey
from app.models.ontology_concept import OntologyConcept
from app.models.risk_assessment import RiskAssessmentControl
from app.models.risk_assessment_control_evidence import RiskAssessmentControlEvidence
from app.models.risk_assessment_history import RiskAssessmentHistory
from app.services.permissions import OrganizationRole
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, seed_risk_area_ontology_concepts

_URL = "/api/v1/risk-assessments"
AS_OF = datetime.now(timezone.utc)


def _create_body(**overrides) -> dict:
    body = {
        "scope": "ORGANIZATION",
        "title": "M29 Transaction Integrity Test Assessment",
        "assessment_type": "BASELINE",
        "assessment_date": AS_OF.isoformat(),
        "as_of": AS_OF.isoformat(),
        "generate_candidates": False,
    }
    body.update(overrides)
    return body


def _risk_area_concept_id(db_session) -> str:
    concept = db_session.execute(
        select(OntologyConcept).where(
            OntologyConcept.concept_key == "VEHICLE_INCIDENT", OntologyConcept.organization_id.is_(None)
        )
    ).scalar_one()
    return str(concept.id)


def _control_create_body(**overrides) -> dict:
    body = {"description": "Rollback test control", "control_type": "ENGINEERING"}
    body.update(overrides)
    return body


def _assess_body(**overrides) -> dict:
    body = {"effectiveness_rating": "EFFECTIVE", "effectiveness_rationale": "Verified on-site."}
    body.update(overrides)
    return body


def _controls_for_org(db_session, organization_id) -> list[RiskAssessmentControl]:
    db_session.expire_all()
    return list(
        db_session.execute(
            select(RiskAssessmentControl).where(RiskAssessmentControl.organization_id == organization_id)
        ).scalars().all()
    )


def _control_evidence_links_for_org(db_session, organization_id) -> list[RiskAssessmentControlEvidence]:
    db_session.expire_all()
    return list(
        db_session.execute(
            select(RiskAssessmentControlEvidence).where(RiskAssessmentControlEvidence.organization_id == organization_id)
        ).scalars().all()
    )


def _history_for_org(db_session, organization_id) -> list[RiskAssessmentHistory]:
    db_session.expire_all()
    return list(
        db_session.execute(
            select(RiskAssessmentHistory).where(RiskAssessmentHistory.organization_id == organization_id)
        ).scalars().all()
    )


def _audit_rows(db_session, organization_id, action_name) -> list[AuditLog]:
    db_session.expire_all()
    return list(
        db_session.execute(
            select(AuditLog).where(AuditLog.organization_id == organization_id, AuditLog.action == action_name)
        ).scalars().all()
    )


def _idempotency_rows(db_session) -> list[IdempotencyKey]:
    db_session.expire_all()
    return list(db_session.execute(select(IdempotencyKey)).scalars().all())


def _setup_finding(client, db_session, headers, org_id) -> tuple[str, str]:
    created = client.post(f"{_URL}?organization_id={org_id}", json=_create_body(), headers=headers)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]
    finding_body = {"risk_area_concept_id": _risk_area_concept_id(db_session), "title": "Rollback test finding"}
    finding = client.post(
        f"{_URL}/{assessment_id}/findings?organization_id={org_id}", json=finding_body, headers=headers
    )
    assert finding.status_code == 201, finding.text
    return assessment_id, finding.json()["id"]


def _setup_control(client, db_session, headers, org_id) -> tuple[str, str, str]:
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org_id)
    control = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org_id}",
        json=_control_create_body(), headers=headers,
    )
    assert control.status_code == 201, control.text
    return assessment_id, finding_id, control.json()["id"]


# --- CREATE CONTROL: history write fails ------------------------------------------------------


def test_create_control_history_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated RiskAssessmentHistory write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.record_history", _boom)

    key_headers = {**headers, "Idempotency-Key": "m29-create-control-history-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
            json=_control_create_body(), headers=key_headers,
        )
        assert failed.status_code == 500

        assert _controls_for_org(db_session, org.id) == []
        assert _audit_rows(db_session, org.id, "RISK_ASSESSMENT_CONTROL_CREATED") == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
            json=_control_create_body(), headers=key_headers,
        )
        assert retry.status_code == 201

    assert len(_controls_for_org(db_session, org.id)) == 1


# --- CREATE CONTROL: audit write fails ---------------------------------------------------------


def test_create_control_audit_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.audit_assessment_event", _boom)

    key_headers = {**headers, "Idempotency-Key": "m29-create-control-audit-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
            json=_control_create_body(), headers=key_headers,
        )
        assert failed.status_code == 500

        assert _controls_for_org(db_session, org.id) == []
        assert [h for h in _history_for_org(db_session, org.id) if h.change_type == "CONTROL_CREATED"] == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
            json=_control_create_body(), headers=key_headers,
        )
        assert retry.status_code == 201

    assert len(_controls_for_org(db_session, org.id)) == 1


# --- CREATE CONTROL: idempotency response persistence fails ------------------------------------


def test_create_control_idempotency_store_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated IdempotencyKey write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.store_response", _boom)

    key_headers = {**headers, "Idempotency-Key": "m29-create-control-idempotency-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
            json=_control_create_body(), headers=key_headers,
        )
        assert failed.status_code == 500

        assert _controls_for_org(db_session, org.id) == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
            json=_control_create_body(), headers=key_headers,
        )
        assert retry.status_code == 201

    assert len(_controls_for_org(db_session, org.id)) == 1
    assert len(_idempotency_rows(db_session)) == 1


def test_create_control_replay_after_a_successful_create_still_works(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)
    key_headers = {**headers, "Idempotency-Key": "m29-create-control-normal-replay"}

    first = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
        json=_control_create_body(), headers=key_headers,
    )
    second = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
        json=_control_create_body(), headers=key_headers,
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(_controls_for_org(db_session, org.id)) == 1


def test_create_control_same_key_different_body_is_a_conflict(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)
    key_headers = {**headers, "Idempotency-Key": "m29-create-control-conflict"}

    first = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
        json=_control_create_body(), headers=key_headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/controls?organization_id={org.id}",
        json=_control_create_body(description="A materially different description"), headers=key_headers,
    )
    assert second.status_code == 409


# --- ASSESS EFFECTIVENESS: history write fails must not leave a partial rating -----------------


def test_assess_effectiveness_history_failure_leaves_rating_unchanged(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id, control_id = _setup_control(client, db_session, headers, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated RiskAssessmentHistory write failure during assessment")

    monkeypatch.setattr("app.api.v1.risk_assessments.record_history", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls/{control_id}/assess-effectiveness"
            f"?organization_id={org.id}",
            json=_assess_body(), headers=headers,
        )
        assert failed.status_code == 500

    db_session.expire_all()
    persisted = db_session.get(RiskAssessmentControl, uuid.UUID(control_id))
    assert persisted.effectiveness.value == "NOT_ASSESSED"
    assert persisted.effectiveness_rationale is None
    assert persisted.assessed_at is None
    assert persisted.assessed_by_user_id is None
    assert _audit_rows(db_session, org.id, "RISK_ASSESSMENT_CONTROL_EFFECTIVENESS_ASSESSED") == []


# --- ASSESS EFFECTIVENESS: audit write fails ----------------------------------------------------


def test_assess_effectiveness_audit_failure_leaves_rating_unchanged(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id, control_id = _setup_control(client, db_session, headers, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure during assessment")

    monkeypatch.setattr("app.api.v1.risk_assessments.audit_assessment_event", _boom)

    key_headers = {**headers, "Idempotency-Key": "m29-assess-audit-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls/{control_id}/assess-effectiveness"
            f"?organization_id={org.id}",
            json=_assess_body(), headers=key_headers,
        )
        assert failed.status_code == 500

        db_session.expire_all()
        persisted = db_session.get(RiskAssessmentControl, uuid.UUID(control_id))
        assert persisted.effectiveness.value == "NOT_ASSESSED"
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls/{control_id}/assess-effectiveness"
            f"?organization_id={org.id}",
            json=_assess_body(), headers=key_headers,
        )
        assert retry.status_code == 200

    db_session.expire_all()
    persisted = db_session.get(RiskAssessmentControl, uuid.UUID(control_id))
    assert persisted.effectiveness.value == "EFFECTIVE"


# --- LINK CONTROL EVIDENCE: history write fails --------------------------------------------------


def test_link_control_evidence_history_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id, control_id = _setup_control(client, db_session, headers, org.id)
    evidence = client.patch(
        f"{_URL}/{assessment_id}/findings/{finding_id}?organization_id={org.id}",
        json={"evidence_add": [{"evidence_type": "OTHER", "reference_label": "Rollback evidence"}]}, headers=headers,
    )
    assert evidence.status_code == 200
    evidence_id = evidence.json()["evidence"][-1]["id"]

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated RiskAssessmentHistory write failure during evidence link")

    monkeypatch.setattr("app.api.v1.risk_assessments.record_history", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/controls/{control_id}/evidence/{evidence_id}"
            f"?organization_id={org.id}",
            headers=headers,
        )
        assert failed.status_code == 500

    assert _control_evidence_links_for_org(db_session, org.id) == []
    assert _audit_rows(db_session, org.id, "RISK_ASSESSMENT_CONTROL_EVIDENCE_LINKED") == []
