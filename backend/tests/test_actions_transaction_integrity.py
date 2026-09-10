"""Transactional-integrity regression tests — SIE Milestone 17
corrective patch. Proves the specific guarantee
`app/services/safety_action_service.py::action_mutation_transaction()`
exists for: a `SafetyAction` mutation, its `SafetyActionHistory` entry,
its `AuditLog` entry, and (create only) its `IdempotencyKey` response
either all persist together or none of them do — verified by actually
querying the database after a failure, not merely asserting an
exception was raised.

Failure is injected with `monkeypatch.setattr()` on the exact names
`app/api/v1/actions.py` imported (mirrors
`tests/test_error_contract_and_health.py`'s own established pattern for
this), and every assertion re-reads from the database through a session
independent of the one the failing request used (`db_session`, expired
before each read so nothing is served from a stale identity-map cache).

Uses a standalone `TestClient(app, raise_server_exceptions=False)`
rather than the shared `client` fixture, exactly like
`tests/test_error_contract_and_health.py::
test_never_leaks_the_real_exception_message_or_type` — the shared
fixture's default `raise_server_exceptions=True` would otherwise turn
the deliberately-injected failure into a test error instead of the
`500` response this module asserts on.
"""

import uuid

from sqlalchemy import select
from starlette.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.idempotency_key import IdempotencyKey
from app.models.safety_action import SafetyAction
from app.models.safety_action_history import SafetyActionHistory
from app.services.permissions import OrganizationRole
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member

_ACTIONS_URL = "/api/v1/actions"


def _valid_create_payload(**overrides) -> dict:
    payload = {"title": "Repair guardrail", "action_type": "CORRECTIVE"}
    payload.update(overrides)
    return payload


def _make_action(db_session, *, organization_id, **overrides) -> SafetyAction:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=organization_id,
        title="Existing action",
        action_type="CORRECTIVE",
        priority="MEDIUM",
        status="OPEN",
        attributes={},
    )
    defaults.update(overrides)
    action = SafetyAction(**defaults)
    db_session.add(action)
    db_session.commit()
    db_session.refresh(action)
    return action


def _actions_for_org(db_session, organization_id) -> list[SafetyAction]:
    db_session.expire_all()
    return list(db_session.execute(select(SafetyAction).where(SafetyAction.organization_id == organization_id)).scalars().all())


def _history_for_org(db_session, organization_id) -> list[SafetyActionHistory]:
    db_session.expire_all()
    return list(
        db_session.execute(select(SafetyActionHistory).where(SafetyActionHistory.organization_id == organization_id))
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


# --- CREATE: history write fails ---------------------------------------------------


def test_create_action_history_failure_leaves_no_partial_state(db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated SafetyActionHistory write failure")

    monkeypatch.setattr("app.api.v1.actions.record_history", _boom)

    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "create-history-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers
        )
        assert failed.status_code == 500

        # Nothing from the failed attempt persisted -- not the action,
        # not a history row, not an audit row (never reached), and no
        # misleading IdempotencyKey a retry could be confused by.
        assert _actions_for_org(db_session, org.id) == []
        assert _history_for_org(db_session, org.id) == []
        assert _audit_rows(db_session, org.id, "SAFETY_ACTION_CREATED") == []
        assert _idempotency_rows(db_session) == []

        # A retry with the exact same Idempotency-Key, once the
        # underlying failure is gone, is a genuinely fresh attempt (not
        # a replay -- nothing was ever stored) and succeeds normally,
        # creating exactly one action.
        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers
        )
        assert retry.status_code == 201

    actions = _actions_for_org(db_session, org.id)
    assert len(actions) == 1
    assert str(actions[0].id) == retry.json()["id"]


# --- CREATE: audit write fails -------------------------------------------------


def test_create_action_audit_failure_leaves_no_partial_state(db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure")

    monkeypatch.setattr("app.api.v1.actions.audit_action_event", _boom)

    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "create-audit-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers
        )
        assert failed.status_code == 500

        # record_history() ran (and flushed) successfully before the
        # injected audit failure -- proving the rollback undoes an
        # already-flushed, not-yet-committed write too, not just one
        # that never got as far as the database.
        assert _actions_for_org(db_session, org.id) == []
        assert _history_for_org(db_session, org.id) == []
        assert _idempotency_rows(db_session) == []

        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers
        )
        assert retry.status_code == 201

    actions = _actions_for_org(db_session, org.id)
    assert len(actions) == 1


# --- CREATE: idempotency response persistence fails -----------------------------


def test_create_action_idempotency_store_failure_leaves_no_partial_state(db_session, monkeypatch):
    """The exact scenario milestone corrective spec §3 names: SafetyAction
    must not commit successfully while the IdempotencyKey response fails
    to persist -- with this fix, a failure at the very last write in the
    transaction still rolls back the action/history/audit that already
    flushed successfully earlier in the same block."""
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated IdempotencyKey write failure")

    monkeypatch.setattr("app.api.v1.actions.store_response", _boom)

    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "create-idempotency-fail"}
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        failed = unsafe_client.post(
            f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers
        )
        assert failed.status_code == 500

        # The action (and its history/audit rows, already flushed) must
        # NOT be left persisted just because only the final idempotency
        # write failed -- this is the specific "torn write" the
        # milestone spec's own item D describes.
        assert _actions_for_org(db_session, org.id) == []
        assert _history_for_org(db_session, org.id) == []
        assert _audit_rows(db_session, org.id, "SAFETY_ACTION_CREATED") == []
        assert _idempotency_rows(db_session) == []

        # Retrying the identical request with the same key, once the
        # failure is gone, must not be blocked by a leftover row and
        # must not create a second action -- it creates exactly one.
        monkeypatch.undo()
        retry = unsafe_client.post(
            f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers
        )
        assert retry.status_code == 201

    actions = _actions_for_org(db_session, org.id)
    assert len(actions) == 1
    idempotency_rows = _idempotency_rows(db_session)
    assert len(idempotency_rows) == 1


def test_create_action_replay_after_a_successful_create_still_works(client, db_session):
    """Sanity check that the transactional fix did not break the
    ordinary (no failure) replay path: same key, same body, second call
    replays the first response and creates no second action."""
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "create-normal-replay"}

    first = client.post(f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers)
    second = client.post(f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(_actions_for_org(db_session, org.id)) == 1
    assert len(_idempotency_rows(db_session)) == 1


# --- PATCH: a downstream failure must not leave a partial field update ---------


def test_update_action_failure_leaves_original_values_intact(db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, title="Original title", priority="LOW")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure during PATCH")

    monkeypatch.setattr("app.api.v1.actions.audit_action_event", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        response = unsafe_client.patch(
            f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
            json={"title": "Hijacked title", "priority": "CRITICAL"},
            headers=dev_auth_headers(user.id),
        )
        assert response.status_code == 500

    db_session.expire_all()
    persisted = db_session.get(SafetyAction, action.id)
    assert persisted.title == "Original title"
    assert persisted.priority.value == "LOW"
    assert _history_for_org(db_session, org.id) == []
    assert _audit_rows(db_session, org.id, "SAFETY_ACTION_UPDATED") == []


def test_update_action_assignment_failure_leaves_original_owner_intact(db_session, monkeypatch):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    action = _make_action(db_session, organization_id=org.id, owner_user_id=None)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated SafetyActionHistory write failure during assignment")

    monkeypatch.setattr("app.api.v1.actions.record_history", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        response = unsafe_client.patch(
            f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
            json={"owner_user_id": str(owner.id)},
            headers=dev_auth_headers(manager.id),
        )
        assert response.status_code == 500

    db_session.expire_all()
    persisted = db_session.get(SafetyAction, action.id)
    assert persisted.owner_user_id is None
    assert _history_for_org(db_session, org.id) == []
    assert _audit_rows(db_session, org.id, "SAFETY_ACTION_ASSIGNED") == []


# --- STATUS: a downstream failure must not leave a partial transition ----------


def test_status_transition_failure_leaves_status_and_timestamps_unchanged(db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated AuditLog write failure during status transition")

    monkeypatch.setattr("app.api.v1.actions.audit_action_event", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        response = unsafe_client.post(
            f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
            json={"status": "COMPLETED"},
            headers=dev_auth_headers(user.id),
        )
        assert response.status_code == 500

    db_session.expire_all()
    persisted = db_session.get(SafetyAction, action.id)
    assert persisted.status.value == "OPEN"
    assert persisted.completed_at is None
    assert persisted.cancelled_at is None
    assert _history_for_org(db_session, org.id) == []
    assert _audit_rows(db_session, org.id, "SAFETY_ACTION_STATUS_CHANGED") == []


def test_status_transition_history_failure_leaves_no_partial_state(db_session, monkeypatch):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated SafetyActionHistory write failure during status transition")

    monkeypatch.setattr("app.api.v1.actions.record_history", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        response = unsafe_client.post(
            f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
            json={"status": "CANCELLED"},
            headers=dev_auth_headers(user.id),
        )
        assert response.status_code == 500

    db_session.expire_all()
    persisted = db_session.get(SafetyAction, action.id)
    assert persisted.status.value == "OPEN"
    assert persisted.cancelled_at is None
    assert _audit_rows(db_session, org.id, "SAFETY_ACTION_STATUS_CHANGED") == []

    # A subsequent, unpatched status transition on the same action still
    # works normally -- the earlier failed attempt left nothing behind
    # that could block or corrupt it.
    monkeypatch.undo()
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        retry = unsafe_client.post(
            f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
            json={"status": "CANCELLED"},
            headers=dev_auth_headers(user.id),
        )
    assert retry.status_code == 200
    db_session.expire_all()
    persisted = db_session.get(SafetyAction, action.id)
    assert persisted.status.value == "CANCELLED"
    assert persisted.cancelled_at is not None
    history = _history_for_org(db_session, org.id)
    assert len(history) == 1
    assert history[0].change_type == "STATUS_CHANGED"
