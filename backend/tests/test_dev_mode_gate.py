"""The development-only identity mechanism (app/api/deps_auth.py) — its
own gating behavior, independent of the authorization tests in
test_authorization.py and test_users_and_memberships.py (which all run
with DEV_MODE on, per tests/conftest.py).

This file is the one place DEV_MODE=False is exercised, using a local
monkeypatch scoped to each test rather than touching the shared
session-wide setting other test modules rely on.
"""

import uuid

from app.api.deps_auth import DEV_USER_HEADER
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services.membership_service import membership_service
from app.services.user_service import user_service


def create_org(client, name="Acme Industrial"):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def test_dev_auth_disabled_by_default_returns_501(client, monkeypatch):
    """The literal production-safety requirement: with DEV_MODE off (the
    default), a route that requires authentication fails closed rather
    than falling back to trusting the caller."""
    monkeypatch.setattr("app.api.deps_auth.settings.DEV_MODE", False)
    org = create_org(client)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": str(uuid.uuid4()), "role": "VIEWER"},
        headers={DEV_USER_HEADER: str(uuid.uuid4())},
    )

    assert response.status_code == 501


def test_dev_auth_requires_the_header(client):
    org = create_org(client)

    response = client.get(f"/api/v1/organizations/{org['id']}/members")

    assert response.status_code == 401


def test_dev_auth_rejects_a_non_uuid_header(client):
    org = create_org(client)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/members",
        headers={DEV_USER_HEADER: "not-a-uuid"},
    )

    assert response.status_code == 401


def test_dev_auth_rejects_an_unknown_user_id(client):
    org = create_org(client)

    response = client.get(
        f"/api/v1/organizations/{org['id']}/members",
        headers={DEV_USER_HEADER: str(uuid.uuid4())},
    )

    assert response.status_code == 401


def test_dev_auth_cannot_grant_a_permission_the_named_user_lacks(client, db_session):
    """The header names a user; it cannot assert a role, a permission, or
    an organization directly. A real, existing, but merely VIEWER user
    still can't manage members through it."""
    org = create_org(client)
    viewer = user_service.create(
        db_session, obj_in=UserCreate(email="realviewer@example.com", name="Real Viewer")
    )
    membership_service.create(
        db_session,
        organization_id=uuid.UUID(org["id"]),
        obj_in=OrganizationMembershipCreate(user_id=viewer.id, role="VIEWER"),
    )

    response = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": str(uuid.uuid4()), "role": "ORG_ADMIN"},
        headers={DEV_USER_HEADER: str(viewer.id)},
    )

    assert response.status_code == 403


def test_dev_auth_cannot_impersonate_an_organization_without_membership(client, db_session):
    """The header authenticates *a user*; it never grants organization
    access by itself. A real user who simply has no membership anywhere
    is denied access to any organization's members endpoint."""
    org = create_org(client)
    unaffiliated = user_service.create(
        db_session, obj_in=UserCreate(email="noorg@example.com", name="No Org")
    )

    response = client.get(
        f"/api/v1/organizations/{org['id']}/members",
        headers={DEV_USER_HEADER: str(unaffiliated.id)},
    )

    assert response.status_code == 403
