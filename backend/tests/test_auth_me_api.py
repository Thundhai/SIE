"""`GET /api/v1/auth/me` — effective-permissions endpoint, SIE Enterprise
Read API & Browser Integration Foundation v0.1 (§8-9). Introduces zero
new authorization logic (see `app/api/v1/auth.py`'s own docstring) — the
one thing worth testing at the HTTP layer is that it serializes the
*real*, already-computed `TenantContext.permissions` correctly, denies a
caller with no membership, and stays human-only.
"""

import uuid

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission, ROLE_PERMISSIONS, OrganizationRole
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, make_platform_admin_user

_ME_URL = "/api/v1/auth/me"


def test_get_me_requires_authentication(client, db_session):
    org = make_org(db_session)
    response = client.get(f"{_ME_URL}?organization_id={org.id}")
    assert response.status_code == 401


def test_get_me_returns_the_real_effective_permission_set_for_the_role(client, db_session):
    org = make_org(db_session, "Acme")
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST, name="Ana Lyst")

    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["email"] == user.email
    assert body["organization_id"] == str(org.id)
    assert body["organization_name"] == "Acme"
    assert body["role"] == "HSE_ANALYST"
    assert body["is_platform_admin"] is False
    expected = sorted(p.value for p in ROLE_PERMISSIONS[OrganizationRole.HSE_ANALYST])
    assert body["permissions"] == expected
    # Never re-derived on the frontend -- this must genuinely be the
    # backend's own ROLE_PERMISSIONS mapping, not a hand-picked subset.
    assert Permission.SAFETY_DATA_READ.value in body["permissions"]


def test_get_me_viewer_has_no_write_or_manage_permissions(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)

    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id))

    permissions = response.json()["permissions"]
    assert Permission.SAFETY_DATA_READ.value in permissions
    assert Permission.SAFETY_DATA_WRITE.value not in permissions
    assert Permission.USERS_MANAGE.value not in permissions


def test_get_me_denies_a_user_with_no_membership_in_the_requested_organization(client, db_session):
    org = make_org(db_session)
    other_org = make_org(db_session, "Other Org")
    user = make_org_member(db_session, other_org.id)

    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id))

    assert response.status_code == 403


def test_get_me_rejects_a_malformed_organization_id(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    response = client.get(f"{_ME_URL}?organization_id=not-a-uuid", headers=dev_auth_headers(user.id))
    assert response.status_code == 422


def test_get_me_reflects_platform_admin_status(client, db_session):
    org = make_org(db_session)
    admin = make_platform_admin_user(db_session)
    from app.schemas.organization_membership import OrganizationMembershipCreate
    from app.services.membership_service import membership_service

    membership_service.create(
        db_session,
        organization_id=org.id,
        obj_in=OrganizationMembershipCreate(user_id=admin.id, role=OrganizationRole.VIEWER),
    )

    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=dev_auth_headers(admin.id))

    assert response.status_code == 200
    assert response.json()["is_platform_admin"] is True


def test_get_me_is_not_reachable_by_a_machine_client(client, db_session):
    """Human-only, deliberately -- a machine client has no per-session
    "current user" to introspect (see app/api/v1/auth.py's own
    docstring). A Bearer credential doesn't satisfy the dev-header
    dependency this route is built on, so it is rejected the same way any
    missing human identity would be."""
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Machine", scopes=[Permission.SAFETY_DATA_READ]
    )

    response = client.get(
        f"{_ME_URL}?organization_id={org.id}",
        headers={"Authorization": f"Bearer {credential.client_id}:{credential.secret}"},
    )

    assert response.status_code == 401
