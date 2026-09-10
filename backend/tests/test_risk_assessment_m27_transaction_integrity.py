"""Transactional-integrity regression tests — SIE Milestone 27: Risk
Assessment & Action Management Integration v0.1, "Relationship mutations
use one transaction." Mirrors
`tests/test_risk_assessment_transaction_integrity.py`'s (SIE Milestone
26) own established pattern exactly: failure is injected with
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
from app.models.risk_assessment import RiskAssessmentFinding
from app.models.risk_assessment_finding_action import RiskAssessmentFindingAction
from app.models.risk_assessment_history import RiskAssessmentHistory
from app.models.safety_action import SafetyAction
from app.services.permissions import OrganizationRole
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, seed_risk_area_ontology_concepts

_URL = "/api/v1/risk-assessments"
AS_OF = datetime.now(timezone.utc)


def _create_body(**overrides) -> dict:
    body = {
        "scope": "ORGANIZATION",
        "title": "M27 Transaction Integrity Test Assessment",
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


def _action_create_body(**overrides) -> dict:
    body = {"title": "New corrective action", "action_type": "CORRECTIVE", "priority": "MEDIUM"}
    body.update(overrides)
    return body


def _relationships_for_org(db_session, organization_id) -> list[RiskAssessmentFindingAction]:
    db_session.expire_all()
    return list(
        db_session.execute(
            select(RiskAssessmentFindingAction).where(RiskAssessmentFindingAction.organization_id == organization_id)
        ).scalars().all()
    )


def _actions_for_org(db_session, organization_id) -> list[SafetyAction]:
    db_session.expire_all()
    return list(db_session.execute(select(SafetyAction).where(SafetyAction.organization_id == organization_id)).scalars().all())


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


# --- CREATE ACTION FROM FINDING: history write fails ---------------------------------------


def test_create_finding_action_history_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated RiskAssessmentHistory write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.record_history", _boom)

    key_headers = {**headers, "Idempotency-Key": "m27-create-action-history-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
            json=_action_create_body(), headers=key_headers,
        )
        assert failed.status_code == 500

        assert _actions_for_org(db_session, org.id) == []
        assert _relationships_for_org(db_session, org.id) == []
        assert _audit_rows(db_session, org.id, "RISK_ASSESSMENT_FINDING_ACTION_CREATED") == []
        assert _audit_rows(db_session, org.id, "SAFETY_ACTION_CREATED") == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
            json=_action_create_body(), headers=key_headers,
        )
        assert retry.status_code == 201

    assert len(_actions_for_org(db_session, org.id)) == 1
    assert len(_relationships_for_org(db_session, org.id)) == 1


# --- CREATE ACTION FROM FINDING: audit write fails ------------------------------------------


def test_create_finding_action_audit_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.audit_assessment_event", _boom)

    key_headers = {**headers, "Idempotency-Key": "m27-create-action-audit-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
            json=_action_create_body(), headers=key_headers,
        )
        assert failed.status_code == 500

        # The SafetyAction row (and its own history/audit, written before
        # the injected failure) must not survive either -- proving the
        # rollback undoes an already-flushed write too.
        assert _actions_for_org(db_session, org.id) == []
        assert _relationships_for_org(db_session, org.id) == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
            json=_action_create_body(), headers=key_headers,
        )
        assert retry.status_code == 201

    assert len(_actions_for_org(db_session, org.id)) == 1


# --- CREATE ACTION FROM FINDING: idempotency response persistence fails ---------------------


def test_create_finding_action_idempotency_store_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated IdempotencyKey write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.store_response", _boom)

    key_headers = {**headers, "Idempotency-Key": "m27-create-action-idempotency-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
            json=_action_create_body(), headers=key_headers,
        )
        assert failed.status_code == 500

        assert _actions_for_org(db_session, org.id) == []
        assert _relationships_for_org(db_session, org.id) == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
            json=_action_create_body(), headers=key_headers,
        )
        assert retry.status_code == 201

    assert len(_actions_for_org(db_session, org.id)) == 1
    assert len(_idempotency_rows(db_session)) == 1


def test_create_finding_action_replay_after_a_successful_create_still_works(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)
    key_headers = {**headers, "Idempotency-Key": "m27-create-action-normal-replay"}

    first = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
        json=_action_create_body(), headers=key_headers,
    )
    second = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
        json=_action_create_body(), headers=key_headers,
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["action_id"] == second.json()["action_id"]
    assert len(_actions_for_org(db_session, org.id)) == 1


def test_create_finding_action_same_key_different_body_is_a_conflict(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)
    key_headers = {**headers, "Idempotency-Key": "m27-create-action-conflict"}

    first = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
        json=_action_create_body(), headers=key_headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"{_URL}/{assessment_id}/findings/{finding_id}/actions?organization_id={org.id}",
        json=_action_create_body(title="A materially different title"), headers=key_headers,
    )
    assert second.status_code == 409


# --- LINK EXISTING ACTION: history write fails -----------------------------------------------


def test_link_finding_action_history_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)
    action = SafetyAction(
        organization_id=org.id, title="Pre-existing action", action_type="CORRECTIVE", priority="MEDIUM",
        status="OPEN", attributes={},
    )
    db_session.add(action)
    db_session.commit()

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated RiskAssessmentHistory write failure during link")

    monkeypatch.setattr("app.api.v1.risk_assessments.record_history", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/actions/link?organization_id={org.id}",
            json={"action_id": str(action.id)}, headers=headers,
        )
        assert failed.status_code == 500

    assert _relationships_for_org(db_session, org.id) == []
    assert _audit_rows(db_session, org.id, "RISK_ASSESSMENT_FINDING_ACTION_LINKED") == []


# --- CLOSE FINDING: audit write fails must not leave a partial status change ----------------


def test_close_finding_audit_failure_leaves_status_unchanged(client, db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(manager.id)
    assessment_id, finding_id = _setup_finding(client, db_session, headers, org.id)
    rated = client.patch(
        f"{_URL}/{assessment_id}/findings/{finding_id}?organization_id={org.id}",
        json={"likelihood": 4, "consequence": 4}, headers=headers,
    )
    assert rated.status_code == 200

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure during close")

    monkeypatch.setattr("app.api.v1.risk_assessments.audit_assessment_event", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings/{finding_id}/close?organization_id={org.id}",
            json={"closure_reason": "Resolved."}, headers=headers,
        )
        assert failed.status_code == 500

    db_session.expire_all()
    persisted = db_session.get(RiskAssessmentFinding, uuid.UUID(finding_id))
    assert persisted.status.value == "OPEN"
    closed_entries = [e for e in _history_for_org(db_session, org.id) if e.change_type == "FINDING_CLOSED"]
    assert closed_entries == []
