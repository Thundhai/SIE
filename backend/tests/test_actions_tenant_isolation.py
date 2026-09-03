"""Actions / Intervention tenant isolation — SIE Milestone 17's own
explicit hard acceptance requirement (§15). Walks that section's
numbered checklist directly, mirroring
`tests/test_events_tenant_isolation.py`'s established shape.
"""

import uuid

from sqlalchemy import select

from app.models.safety_action import SafetyAction
from app.models.safety_action_history import SafetyActionHistory
from app.services.api_client_service import api_client_service
from app.services.permissions import OrganizationRole, Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, make_safety_event, make_site

_ACTIONS_URL = "/api/v1/actions"


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _make_action(db_session, *, organization_id, **overrides) -> SafetyAction:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=organization_id,
        title="Action",
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


def _two_orgs(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    action_a = _make_action(db_session, organization_id=org_a.id, title="Org A action")
    action_b = _make_action(db_session, organization_id=org_b.id, title="Org B action")
    return org_a, manager_a, action_a, org_b, manager_b, action_b


# 1. Human Org A cannot list Org B actions.
def test_human_org_a_cannot_list_org_b_actions(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)

    response = client.get(f"{_ACTIONS_URL}?organization_id={org_b.id}", headers=dev_auth_headers(manager_a.id))

    assert response.status_code == 403


# 2. Human Org A cannot read Org B action.
def test_human_org_a_cannot_read_org_b_action(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)

    # Using their own (legitimate) organization_id with the other org's
    # action id -- the action simply doesn't exist in org_a's scope.
    response = client.get(
        f"{_ACTIONS_URL}/{action_b.id}?organization_id={org_a.id}", headers=dev_auth_headers(manager_a.id)
    )

    assert response.status_code == 404


# 3. Human Org A cannot update Org B action.
def test_human_org_a_cannot_update_org_b_action(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)

    response = client.patch(
        f"{_ACTIONS_URL}/{action_b.id}?organization_id={org_a.id}",
        json={"title": "Hijacked"},
        headers=dev_auth_headers(manager_a.id),
    )

    assert response.status_code == 404
    db_session.refresh(action_b)
    assert action_b.title == "Org B action"


# 4. Human Org A cannot transition Org B action.
def test_human_org_a_cannot_transition_org_b_action(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)

    response = client.post(
        f"{_ACTIONS_URL}/{action_b.id}/status?organization_id={org_a.id}",
        json={"status": "IN_PROGRESS"},
        headers=dev_auth_headers(manager_a.id),
    )

    assert response.status_code == 404
    db_session.refresh(action_b)
    assert action_b.status.value == "OPEN"


# 5. Machine Org A cannot operate on Org B action.
def test_machine_org_a_cannot_operate_on_org_b_action(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)
    credential_a = api_client_service.create(
        db_session,
        organization_id=org_a.id,
        name="A",
        scopes=[Permission.INTERVENTION_READ, Permission.INTERVENTION_MANAGE, Permission.INTERVENTION_CLOSE],
    )

    list_response = client.get(f"{_ACTIONS_URL}?organization_id={org_b.id}", headers=_bearer(credential_a))
    get_response = client.get(
        f"{_ACTIONS_URL}/{action_b.id}?organization_id={org_b.id}", headers=_bearer(credential_a)
    )
    patch_response = client.patch(
        f"{_ACTIONS_URL}/{action_b.id}?organization_id={org_b.id}",
        json={"title": "x"},
        headers=_bearer(credential_a),
    )
    status_response = client.post(
        f"{_ACTIONS_URL}/{action_b.id}/status?organization_id={org_b.id}",
        json={"status": "IN_PROGRESS"},
        headers=_bearer(credential_a),
    )

    # A machine client is pinned to its own organization_id at
    # authentication time (app/api/deps_context.py) -- every one of
    # these is denied before any query even reaches action_b's row.
    assert list_response.status_code == 403
    assert get_response.status_code == 403
    assert patch_response.status_code == 403
    assert status_response.status_code == 403


# 6. Org A action cannot reference Org B event.
def test_org_a_action_cannot_reference_org_b_event(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)
    event_b = make_safety_event(organization_id=org_b.id)
    db_session.add(event_b)
    db_session.commit()

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org_a.id}",
        json={"title": "x", "action_type": "CORRECTIVE", "source_event_id": str(event_b.id)},
        headers=dev_auth_headers(manager_a.id),
    )

    assert response.status_code == 404


# 7. Org A action cannot reference Org B site.
def test_org_a_action_cannot_reference_org_b_site(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)
    site_b = make_site(db_session, org_b.id)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org_a.id}",
        json={"title": "x", "action_type": "CORRECTIVE", "site_id": str(site_b.id)},
        headers=dev_auth_headers(manager_a.id),
    )

    assert response.status_code == 404


# 8. Org A action cannot assign Org B user.
def test_org_a_action_cannot_assign_org_b_user(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)
    user_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_USER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org_a.id}",
        json={"title": "x", "action_type": "CORRECTIVE", "owner_user_id": str(user_b.id)},
        headers=dev_auth_headers(manager_a.id),
    )

    assert response.status_code == 404


# 9. Org A cannot access Org B history.
def test_org_a_cannot_access_org_b_history(client, db_session):
    """No HTTP history-read endpoint exists this milestone (see
    app/api/v1/actions.py's own docstring) -- verified directly at the
    service/database layer: a history row for an Org B action is always
    written with organization_id=org_b, so any query an org_a-scoped
    caller could ever legitimately issue (organization_id == org_a.id)
    structurally cannot return it."""
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)

    client.post(
        f"{_ACTIONS_URL}/{action_b.id}/status?organization_id={org_b.id}",
        json={"status": "IN_PROGRESS"},
        headers=dev_auth_headers(manager_b.id),
    )

    org_a_scoped_history = (
        db_session.execute(select(SafetyActionHistory).where(SafetyActionHistory.organization_id == org_a.id))
        .scalars()
        .all()
    )
    assert all(h.action_id != action_b.id for h in org_a_scoped_history)

    history_for_b = (
        db_session.execute(select(SafetyActionHistory).where(SafetyActionHistory.action_id == action_b.id))
        .scalars()
        .all()
    )
    assert all(h.organization_id == org_b.id for h in history_for_b)


# 10. Cross-tenant IDs do not reveal record existence.
def test_cross_tenant_action_id_is_indistinguishable_from_nonexistent(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)

    cross_tenant = client.get(
        f"{_ACTIONS_URL}/{action_b.id}?organization_id={org_a.id}", headers=dev_auth_headers(manager_a.id)
    )
    nonexistent = client.get(
        f"{_ACTIONS_URL}/{uuid.uuid4()}?organization_id={org_a.id}", headers=dev_auth_headers(manager_a.id)
    )

    assert cross_tenant.status_code == nonexistent.status_code == 404
    assert cross_tenant.json()["detail"] == nonexistent.json()["detail"]


# Symmetry check -- the isolation above is not a one-directional accident.
def test_org_a_can_fully_operate_on_its_own_actions_while_isolated_from_org_b(client, db_session):
    org_a, manager_a, action_a, org_b, manager_b, action_b = _two_orgs(db_session)

    own = client.get(f"{_ACTIONS_URL}/{action_a.id}?organization_id={org_a.id}", headers=dev_auth_headers(manager_a.id))
    own_list = client.get(f"{_ACTIONS_URL}?organization_id={org_a.id}", headers=dev_auth_headers(manager_a.id))

    assert own.status_code == 200
    assert own_list.status_code == 200
    assert own_list.json()["total"] == 1
    assert own_list.json()["items"][0]["id"] == str(action_a.id)
