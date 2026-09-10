"""Actions / Intervention API — SIE Milestone 17: Actions & Intervention
Foundation v0.1. HTTP-level tests against the ordinary SQLite `client`
fixture, mirroring `tests/test_events_api.py`'s own shape. Tenant
isolation gets its own dedicated file
(`tests/test_actions_tenant_isolation.py`) since it is this milestone's
primary hard acceptance requirement (§15).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.safety_action import SafetyAction
from app.models.safety_action_history import SafetyActionHistory
from app.services.api_client_service import api_client_service
from app.services.permissions import OrganizationRole, Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, make_safety_event, make_site

_ACTIONS_URL = "/api/v1/actions"


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


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


# --- CREATE -------------------------------------------------------------------------


def test_create_action_requires_authentication(client, db_session):
    org = make_org(db_session)
    response = client.post(f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload())
    assert response.status_code == 401


def test_create_action_minimal_valid_payload(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=dev_auth_headers(user.id)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Repair guardrail"
    assert body["status"] == "OPEN"
    assert body["priority"] == "MEDIUM"
    assert body["created_by_user_id"] == str(user.id)
    assert body["created_by_api_client_id"] is None
    assert body["completed_at"] is None
    assert body["cancelled_at"] is None


def test_create_action_requires_title(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json={"action_type": "CORRECTIVE"},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_create_action_rejects_invalid_action_type(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(action_type="NOT_A_REAL_TYPE"),
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_create_action_rejects_invalid_priority(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(priority="SUPER_URGENT"),
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_create_action_with_a_valid_site(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(site_id=str(site.id)),
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 201
    assert response.json()["site_id"] == str(site.id)
    assert response.json()["site_name"] == site.name


def test_create_action_rejects_a_nonexistent_site(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(site_id=str(uuid.uuid4())),
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 404


def test_create_action_with_a_valid_source_event(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    event = make_safety_event(organization_id=org.id)
    db_session.add(event)
    db_session.commit()

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(source_event_id=str(event.id)),
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 201
    assert response.json()["source_event_id"] == str(event.id)


def test_create_action_rejects_a_nonexistent_source_event(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(source_event_id=str(uuid.uuid4())),
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 404


def test_create_action_with_a_valid_owner(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER, name="Owner")

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(owner_user_id=str(owner.id)),
        headers=dev_auth_headers(manager.id),
    )

    assert response.status_code == 201
    assert response.json()["owner_user_id"] == str(owner.id)
    assert response.json()["owner_name"] == owner.name


def test_create_action_rejects_an_owner_with_no_membership_in_the_organization(client, db_session):
    org = make_org(db_session)
    other_org = make_org(db_session, "Other Org")
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    outsider = make_org_member(db_session, other_org.id, role=OrganizationRole.HSE_USER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(owner_user_id=str(outsider.id)),
        headers=dev_auth_headers(manager.id),
    )

    assert response.status_code == 404


def test_create_action_assigning_an_owner_requires_the_assign_scope(client, db_session):
    """A machine client with only intervention:manage (not
    intervention:assign) may create an unassigned action but not an
    assigned one -- ASSIGN is required *in addition to* WRITE, never
    implied by it."""
    org = make_org(db_session)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Write-only", scopes=[Permission.INTERVENTION_MANAGE]
    )

    unassigned = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=_bearer(credential)
    )
    assigned = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(owner_user_id=str(owner.id)),
        headers=_bearer(credential),
    )

    assert unassigned.status_code == 201
    assert assigned.status_code == 403


def test_create_action_rejects_organization_id_in_the_body(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(organization_id=str(uuid.uuid4())),
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_create_action_rejects_oversized_attributes(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(attributes={"blob": "x" * 20_000}),
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_create_action_denies_a_viewer(client, db_session):
    org = make_org(db_session)
    viewer = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=dev_auth_headers(viewer.id)
    )

    assert response.status_code == 403


# --- READ -----------------------------------------------------------------------


def test_get_action(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    action = _make_action(db_session, organization_id=org.id)

    response = client.get(f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}", headers=dev_auth_headers(user.id))

    assert response.status_code == 200
    assert response.json()["id"] == str(action.id)


def test_get_action_nonexistent(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)

    response = client.get(
        f"{_ACTIONS_URL}/{uuid.uuid4()}?organization_id={org.id}", headers=dev_auth_headers(user.id)
    )

    assert response.status_code == 404


# --- LIST -----------------------------------------------------------------------


def test_list_actions_pagination(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    for i in range(5):
        _make_action(db_session, organization_id=org.id, title=f"Action {i}")

    page_1 = client.get(
        f"{_ACTIONS_URL}?organization_id={org.id}&page=1&page_size=2", headers=dev_auth_headers(user.id)
    ).json()
    page_2 = client.get(
        f"{_ACTIONS_URL}?organization_id={org.id}&page=2&page_size=2", headers=dev_auth_headers(user.id)
    ).json()
    page_3 = client.get(
        f"{_ACTIONS_URL}?organization_id={org.id}&page=3&page_size=2", headers=dev_auth_headers(user.id)
    ).json()

    assert page_1["total"] == page_2["total"] == page_3["total"] == 5
    assert len(page_1["items"]) == 2
    assert len(page_2["items"]) == 2
    assert len(page_3["items"]) == 1
    ids = {i["id"] for page in (page_1, page_2, page_3) for i in page["items"]}
    assert len(ids) == 5


def test_list_actions_sort_is_deterministic(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    for i in range(4):
        _make_action(db_session, organization_id=org.id, title=f"Action {i}")

    first = client.get(f"{_ACTIONS_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id)).json()
    second = client.get(f"{_ACTIONS_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id)).json()

    assert [i["id"] for i in first["items"]] == [i["id"] for i in second["items"]]


def test_list_actions_filters_by_status(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _make_action(db_session, organization_id=org.id, status="OPEN")
    _make_action(db_session, organization_id=org.id, status="BLOCKED")

    response = client.get(f"{_ACTIONS_URL}?organization_id={org.id}&status=BLOCKED", headers=dev_auth_headers(user.id))

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "BLOCKED"


def test_list_actions_filters_by_priority(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _make_action(db_session, organization_id=org.id, priority="LOW")
    _make_action(db_session, organization_id=org.id, priority="CRITICAL")

    response = client.get(
        f"{_ACTIONS_URL}?organization_id={org.id}&priority=CRITICAL", headers=dev_auth_headers(user.id)
    )

    assert response.json()["total"] == 1


def test_list_actions_filters_by_owner(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    _make_action(db_session, organization_id=org.id, owner_user_id=owner.id)
    _make_action(db_session, organization_id=org.id)

    response = client.get(
        f"{_ACTIONS_URL}?organization_id={org.id}&owner_user_id={owner.id}", headers=dev_auth_headers(user.id)
    )

    assert response.json()["total"] == 1


def test_list_actions_filters_by_site(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    site = make_site(db_session, org.id)
    _make_action(db_session, organization_id=org.id, site_id=site.id)
    _make_action(db_session, organization_id=org.id)

    response = client.get(f"{_ACTIONS_URL}?organization_id={org.id}&site_id={site.id}", headers=dev_auth_headers(user.id))

    assert response.json()["total"] == 1


def test_list_actions_filters_by_source_event(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    event = make_safety_event(organization_id=org.id)
    db_session.add(event)
    db_session.commit()
    _make_action(db_session, organization_id=org.id, source_event_id=event.id)
    _make_action(db_session, organization_id=org.id)

    response = client.get(
        f"{_ACTIONS_URL}?organization_id={org.id}&source_event_id={event.id}", headers=dev_auth_headers(user.id)
    )

    assert response.json()["total"] == 1


def test_list_actions_filters_by_action_type(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _make_action(db_session, organization_id=org.id, action_type="PREVENTIVE")
    _make_action(db_session, organization_id=org.id, action_type="INVESTIGATION")

    response = client.get(
        f"{_ACTIONS_URL}?organization_id={org.id}&action_type=INVESTIGATION", headers=dev_auth_headers(user.id)
    )

    assert response.json()["total"] == 1


def test_list_actions_filters_by_due_date_range(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _make_action(db_session, organization_id=org.id, due_date=datetime(2026, 1, 1, tzinfo=timezone.utc))
    _make_action(db_session, organization_id=org.id, due_date=datetime(2026, 6, 1, tzinfo=timezone.utc))
    _make_action(db_session, organization_id=org.id, due_date=datetime(2026, 12, 1, tzinfo=timezone.utc))

    response = client.get(
        f"{_ACTIONS_URL}?organization_id={org.id}"
        "&due_date_from=2026-02-01T00:00:00Z&due_date_to=2026-07-01T00:00:00Z",
        headers=dev_auth_headers(user.id),
    )

    assert response.json()["total"] == 1


def test_list_actions_search_matches_title(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _make_action(db_session, organization_id=org.id, title="Replace damaged guardrail")
    _make_action(db_session, organization_id=org.id, title="Unrelated action")

    response = client.get(f"{_ACTIONS_URL}?organization_id={org.id}&search=guardrail", headers=dev_auth_headers(user.id))

    assert response.json()["total"] == 1


# --- UPDATE (PATCH) --------------------------------------------------------------


def test_update_action_allowed_fields(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, title="Old title")

    response = client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={"title": "New title", "priority": "HIGH"},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New title"
    assert body["priority"] == "HIGH"


@pytest.mark.parametrize("forbidden_field,value", [
    ("status", "COMPLETED"),
    ("organization_id", str(uuid.uuid4())),
    ("created_at", "2020-01-01T00:00:00Z"),
    ("completed_at", "2020-01-01T00:00:00Z"),
    ("cancelled_at", "2020-01-01T00:00:00Z"),
    ("created_by_user_id", str(uuid.uuid4())),
    ("source_event_id", str(uuid.uuid4())),
])
def test_update_action_rejects_forbidden_fields(client, db_session, forbidden_field, value):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id)

    response = client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={forbidden_field: value},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_update_action_no_changes_is_a_noop_and_writes_no_history(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, title="Same title")

    response = client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={"title": "Same title"},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 200
    history = db_session.execute(select(SafetyActionHistory).where(SafetyActionHistory.action_id == action.id)).scalars().all()
    assert history == []


def test_update_action_assignment(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    action = _make_action(db_session, organization_id=org.id)

    response = client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={"owner_user_id": str(owner.id)},
        headers=dev_auth_headers(manager.id),
    )

    assert response.status_code == 200
    assert response.json()["owner_user_id"] == str(owner.id)


def test_update_action_assignment_requires_assign_scope(client, db_session):
    org = make_org(db_session)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    action = _make_action(db_session, organization_id=org.id)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Write-only", scopes=[Permission.INTERVENTION_MANAGE]
    )

    response = client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={"owner_user_id": str(owner.id)},
        headers=_bearer(credential),
    )

    assert response.status_code == 403


def test_update_action_rejects_a_cross_tenant_owner(client, db_session):
    org = make_org(db_session)
    other_org = make_org(db_session, "Other Org")
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    outsider = make_org_member(db_session, other_org.id, role=OrganizationRole.HSE_USER)
    action = _make_action(db_session, organization_id=org.id)

    response = client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={"owner_user_id": str(outsider.id)},
        headers=dev_auth_headers(manager.id),
    )

    assert response.status_code == 404


def test_update_action_rejects_blank_title(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id)

    response = client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={"title": "   "},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


# --- STATUS -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "current,target",
    [
        ("OPEN", "IN_PROGRESS"),
        ("OPEN", "BLOCKED"),
        ("OPEN", "COMPLETED"),
        ("OPEN", "CANCELLED"),
        ("IN_PROGRESS", "BLOCKED"),
        ("IN_PROGRESS", "COMPLETED"),
        ("IN_PROGRESS", "CANCELLED"),
        ("BLOCKED", "IN_PROGRESS"),
        ("BLOCKED", "COMPLETED"),
        ("BLOCKED", "CANCELLED"),
    ],
)
def test_status_transition_valid(client, db_session, current, target):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status=current)

    response = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": target},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == target


@pytest.mark.parametrize(
    "current,target",
    [
        ("COMPLETED", "OPEN"),
        ("COMPLETED", "IN_PROGRESS"),
        ("CANCELLED", "OPEN"),
        ("CANCELLED", "IN_PROGRESS"),
        ("IN_PROGRESS", "OPEN"),
        ("BLOCKED", "OPEN"),
    ],
)
def test_status_transition_invalid(client, db_session, current, target):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status=current)

    response = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": target},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_status_transition_to_completed_sets_completed_at(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")

    response = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "COMPLETED"},
        headers=dev_auth_headers(user.id),
    )

    body = response.json()
    assert body["completed_at"] is not None
    assert body["cancelled_at"] is None


def test_status_transition_to_cancelled_sets_cancelled_at(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")

    response = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "CANCELLED"},
        headers=dev_auth_headers(user.id),
    )

    body = response.json()
    assert body["cancelled_at"] is not None
    assert body["completed_at"] is None


def test_status_transition_out_of_completed_is_refused(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="COMPLETED", completed_at=datetime.now(timezone.utc))

    response = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "IN_PROGRESS"},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422
    db_session.refresh(action)
    assert action.status.value == "COMPLETED"


def test_status_transition_out_of_cancelled_is_refused(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="CANCELLED", cancelled_at=datetime.now(timezone.utc))

    response = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "COMPLETED"},
        headers=dev_auth_headers(user.id),
    )

    assert response.status_code == 422


def test_status_transition_to_a_terminal_state_requires_close_scope(client, db_session):
    org = make_org(db_session)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Write-only", scopes=[Permission.INTERVENTION_MANAGE]
    )

    to_in_progress = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "IN_PROGRESS"},
        headers=_bearer(credential),
    )
    to_completed = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "COMPLETED"},
        headers=_bearer(credential),
    )

    assert to_in_progress.status_code == 200
    assert to_completed.status_code == 403


def test_status_transition_with_close_scope_alone_cannot_make_a_non_terminal_transition(client, db_session):
    """CLOSE is a distinct capability from WRITE, not a superset of it --
    a caller with only intervention:close cannot move an action to
    IN_PROGRESS/BLOCKED, only into a terminal state."""
    org = make_org(db_session)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Close-only", scopes=[Permission.INTERVENTION_CLOSE]
    )

    to_in_progress = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "IN_PROGRESS"},
        headers=_bearer(credential),
    )
    to_completed = client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "COMPLETED"},
        headers=_bearer(credential),
    )

    assert to_in_progress.status_code == 403
    assert to_completed.status_code == 200


def test_status_transition_records_comment(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")

    client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "BLOCKED", "comment": "Waiting on parts"},
        headers=dev_auth_headers(user.id),
    )

    history = db_session.execute(select(SafetyActionHistory).where(SafetyActionHistory.action_id == action.id)).scalars().all()
    assert len(history) == 1
    assert history[0].comment == "Waiting on parts"


# --- IDEMPOTENCY -------------------------------------------------------------------


def test_create_action_idempotent_replay_does_not_duplicate(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "create-1"}

    first = client.post(f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers)
    second = client.post(f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    count = db_session.execute(select(SafetyAction).where(SafetyAction.organization_id == org.id)).scalars().all()
    assert len(count) == 1


def test_create_action_idempotency_key_reuse_with_different_payload_is_rejected(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = {**dev_auth_headers(user.id), "Idempotency-Key": "create-2"}

    first = client.post(f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=headers)
    second = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_valid_create_payload(title="A completely different action"),
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


# --- AUDIT -----------------------------------------------------------------------


def test_create_action_writes_an_audit_log_entry(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=dev_auth_headers(user.id)
    )

    action_id = uuid.UUID(response.json()["id"])
    entries = db_session.execute(select(AuditLog).where(AuditLog.resource_id == action_id)).scalars().all()
    assert any(e.action == "SAFETY_ACTION_CREATED" for e in entries)


def test_update_action_writes_an_audit_log_entry(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id)

    client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={"priority": "CRITICAL"},
        headers=dev_auth_headers(user.id),
    )

    entries = db_session.execute(select(AuditLog).where(AuditLog.resource_id == action.id)).scalars().all()
    assert any(e.action == "SAFETY_ACTION_UPDATED" for e in entries)


def test_assignment_writes_a_distinct_audit_log_entry(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    action = _make_action(db_session, organization_id=org.id)

    client.patch(
        f"{_ACTIONS_URL}/{action.id}?organization_id={org.id}",
        json={"owner_user_id": str(owner.id)},
        headers=dev_auth_headers(manager.id),
    )

    entries = db_session.execute(select(AuditLog).where(AuditLog.resource_id == action.id)).scalars().all()
    assert any(e.action == "SAFETY_ACTION_ASSIGNED" for e in entries)


def test_status_transition_writes_an_audit_log_entry(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")

    client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "IN_PROGRESS"},
        headers=dev_auth_headers(user.id),
    )

    entries = db_session.execute(select(AuditLog).where(AuditLog.resource_id == action.id)).scalars().all()
    assert any(e.action == "SAFETY_ACTION_STATUS_CHANGED" for e in entries)


# --- HISTORY (no HTTP endpoint this milestone -- verified at the service/DB layer) --


def test_creation_writes_a_history_entry(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=dev_auth_headers(user.id)
    )

    action_id = uuid.UUID(response.json()["id"])
    history = db_session.execute(select(SafetyActionHistory).where(SafetyActionHistory.action_id == action_id)).scalars().all()
    assert len(history) == 1
    assert history[0].change_type == "CREATED"
    assert history[0].to_status == "OPEN"
    assert history[0].changed_by_user_id == user.id


def test_status_transition_writes_a_from_to_history_entry(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    action = _make_action(db_session, organization_id=org.id, status="OPEN")

    client.post(
        f"{_ACTIONS_URL}/{action.id}/status?organization_id={org.id}",
        json={"status": "BLOCKED"},
        headers=dev_auth_headers(user.id),
    )

    history = db_session.execute(select(SafetyActionHistory).where(SafetyActionHistory.action_id == action.id)).scalars().all()
    assert len(history) == 1
    assert history[0].change_type == "STATUS_CHANGED"
    assert history[0].from_status == "OPEN"
    assert history[0].to_status == "BLOCKED"


def test_full_lifecycle_accumulates_history_in_order(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    owner = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)

    create = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_valid_create_payload(), headers=dev_auth_headers(user.id)
    )
    action_id = uuid.UUID(create.json()["id"])
    client.patch(
        f"{_ACTIONS_URL}/{action_id}?organization_id={org.id}",
        json={"owner_user_id": str(owner.id)},
        headers=dev_auth_headers(user.id),
    )
    client.post(
        f"{_ACTIONS_URL}/{action_id}/status?organization_id={org.id}",
        json={"status": "IN_PROGRESS"},
        headers=dev_auth_headers(user.id),
    )
    client.post(
        f"{_ACTIONS_URL}/{action_id}/status?organization_id={org.id}",
        json={"status": "COMPLETED"},
        headers=dev_auth_headers(user.id),
    )

    history = (
        db_session.execute(
            select(SafetyActionHistory)
            .where(SafetyActionHistory.action_id == action_id)
            .order_by(SafetyActionHistory.created_at)
        )
        .scalars()
        .all()
    )
    assert [h.change_type for h in history] == ["CREATED", "ASSIGNED", "STATUS_CHANGED", "STATUS_CHANGED"]
