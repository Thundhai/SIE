"""Transactional-integrity regression tests — SIE Milestone 26: Formal
Enterprise Risk Assessment Engine v0.2, item 9 ("the lesson from
Milestone 17"). Mirrors `tests/test_actions_transaction_integrity.py`'s
own established pattern exactly: failure is injected with
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
from app.models.risk_assessment import RiskAssessment, RiskAssessmentFinding
from app.models.risk_assessment_history import RiskAssessmentHistory
from app.services.permissions import OrganizationRole
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, seed_risk_area_ontology_concepts

_URL = "/api/v1/risk-assessments"
AS_OF = datetime.now(timezone.utc)


def _create_body(**overrides) -> dict:
    body = {
        "scope": "ORGANIZATION",
        "title": "Transaction Integrity Test Assessment",
        "assessment_type": "BASELINE",
        "assessment_date": AS_OF.isoformat(),
        "as_of": AS_OF.isoformat(),
        "generate_candidates": False,
    }
    body.update(overrides)
    return body


def _assessments_for_org(db_session, organization_id) -> list[RiskAssessment]:
    db_session.expire_all()
    return list(
        db_session.execute(select(RiskAssessment).where(RiskAssessment.organization_id == organization_id))
        .scalars()
        .all()
    )


def _findings_for_org(db_session, organization_id) -> list[RiskAssessmentFinding]:
    db_session.expire_all()
    return list(
        db_session.execute(select(RiskAssessmentFinding).where(RiskAssessmentFinding.organization_id == organization_id))
        .scalars()
        .all()
    )


def _history_for_org(db_session, organization_id) -> list[RiskAssessmentHistory]:
    db_session.expire_all()
    return list(
        db_session.execute(select(RiskAssessmentHistory).where(RiskAssessmentHistory.organization_id == organization_id))
        .scalars()
        .all()
    )


def _audit_rows(db_session, organization_id, action_name) -> list[AuditLog]:
    db_session.expire_all()
    return list(
        db_session.execute(
            select(AuditLog).where(AuditLog.organization_id == organization_id, AuditLog.action == action_name)
        )
        .scalars()
        .all()
    )


def _idempotency_rows(db_session) -> list[IdempotencyKey]:
    db_session.expire_all()
    return list(db_session.execute(select(IdempotencyKey)).scalars().all())


# --- CREATE ASSESSMENT: history write fails ------------------------------------------------


def test_create_assessment_history_failure_leaves_no_partial_state(db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated RiskAssessmentHistory write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.record_history", _boom)

    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "ra-create-history-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
        assert failed.status_code == 500

        assert _assessments_for_org(db_session, org.id) == []
        assert _history_for_org(db_session, org.id) == []
        assert _audit_rows(db_session, org.id, "RISK_ASSESSMENT_CREATED") == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
        assert retry.status_code == 201

    assessments = _assessments_for_org(db_session, org.id)
    assert len(assessments) == 1
    assert str(assessments[0].id) == retry.json()["id"]


# --- CREATE ASSESSMENT: audit write fails --------------------------------------------------


def test_create_assessment_audit_failure_leaves_no_partial_state(db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.audit_assessment_event", _boom)

    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "ra-create-audit-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
        assert failed.status_code == 500

        # record_history() ran (and flushed) successfully before the
        # injected audit failure -- proving the rollback undoes an
        # already-flushed, not-yet-committed write too.
        assert _assessments_for_org(db_session, org.id) == []
        assert _history_for_org(db_session, org.id) == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
        assert retry.status_code == 201

    assert len(_assessments_for_org(db_session, org.id)) == 1


# --- CREATE ASSESSMENT: idempotency response persistence fails ----------------------------


def test_create_assessment_idempotency_store_failure_leaves_no_partial_state(db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated IdempotencyKey write failure")

    monkeypatch.setattr("app.api.v1.risk_assessments.store_response", _boom)

    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "ra-create-idempotency-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
        assert failed.status_code == 500

        assert _assessments_for_org(db_session, org.id) == []
        assert _history_for_org(db_session, org.id) == []
        assert _audit_rows(db_session, org.id, "RISK_ASSESSMENT_CREATED") == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
        assert retry.status_code == 201

    assert len(_assessments_for_org(db_session, org.id)) == 1
    assert len(_idempotency_rows(db_session)) == 1


def test_create_assessment_replay_after_a_successful_create_still_works(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "ra-create-normal-replay"}

    first = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
    second = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(_assessments_for_org(db_session, org.id)) == 1
    assert len(_idempotency_rows(db_session)) == 1


def test_create_assessment_same_key_different_body_is_a_conflict(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "ra-create-conflict"}

    first = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
    assert first.status_code == 201
    second = client.post(
        f"{_URL}?organization_id={org.id}", json=_create_body(title="A materially different title"), headers=headers
    )
    assert second.status_code == 409


# --- CREATE FINDING: history write fails ---------------------------------------------------


def test_create_finding_history_failure_leaves_no_partial_state(client, db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    concept_ids = seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(user.id)
    created = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
    assert created.status_code == 201
    assessment_id = created.json()["id"]

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated RiskAssessmentHistory write failure during finding creation")

    monkeypatch.setattr("app.api.v1.risk_assessments.record_history", _boom)

    finding_body = {"risk_area_concept_id": str(concept_ids["VEHICLE_SAFETY"]), "title": "Rollback test finding"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_URL}/{assessment_id}/findings?organization_id={org.id}", json=finding_body, headers=headers
        )
        assert failed.status_code == 500

    assert _findings_for_org(db_session, org.id) == []
    finding_history = [e for e in _history_for_org(db_session, org.id) if e.finding_id is not None]
    assert finding_history == []
    assert _audit_rows(db_session, org.id, "RISK_ASSESSMENT_FINDING_CREATED") == []


# --- UPDATE FINDING: a downstream failure must not leave a partial rating change -----------


def test_update_finding_rating_failure_leaves_original_values_intact(client, db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    concept_ids = seed_risk_area_ontology_concepts(db_session)
    headers = dev_auth_headers(user.id)
    created = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=headers)
    assessment_id = created.json()["id"]
    finding_body = {"risk_area_concept_id": str(concept_ids["VEHICLE_SAFETY"]), "title": "Original title"}
    finding = client.post(
        f"{_URL}/{assessment_id}/findings?organization_id={org.id}", json=finding_body, headers=headers
    ).json()
    assert finding["likelihood"] is None

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure during rating")

    monkeypatch.setattr("app.api.v1.risk_assessments.audit_assessment_event", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        response = unsafe_client.patch(
            f"{_URL}/{assessment_id}/findings/{finding['id']}?organization_id={org.id}",
            json={"likelihood": 4, "consequence": 5},
            headers=headers,
        )
        assert response.status_code == 500

    db_session.expire_all()
    persisted = db_session.get(RiskAssessmentFinding, uuid.UUID(finding["id"]))
    assert persisted.likelihood is None
    assert persisted.inherent_risk_score is None
    # Only the earlier, already-committed FINDING_CREATED entry exists --
    # the failed PATCH's own FINDING_RISK_RATED entry never persisted.
    finding_history = [e for e in _history_for_org(db_session, org.id) if e.finding_id is not None]
    assert [e.change_type for e in finding_history] == ["FINDING_CREATED"]
