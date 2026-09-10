"""Users and organization memberships — model/service and HTTP coverage.

Covers milestone test items 1-4, 8, and the membership HTTP endpoints
(item 14's "existing tenant isolation tests continue passing" for the new
resource, and tenant isolation on the new endpoints themselves).
"""

import uuid

from app.models.enums import MembershipStatus
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services.errors import KnowledgeNotFoundError, KnowledgeValidationError
from app.services.membership_service import membership_service
from app.services.permissions import OrganizationRole
from app.services.user_service import user_service
from tests.conftest import dev_auth_headers


def create_org(client, name="Acme Industrial"):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def make_user(db_session, email="user@example.com", name="Test User", **kwargs):
    return user_service.create(db_session, obj_in=UserCreate(email=email, name=name, **kwargs))


def make_membership(db_session, *, user_id, organization_id, role, status=MembershipStatus.ACTIVE):
    return membership_service.create(
        db_session,
        organization_id=organization_id,
        obj_in=OrganizationMembershipCreate(user_id=user_id, role=role, status=status),
    )


# --- 1. Create user ---------------------------------------------------


def test_create_user(db_session):
    user = make_user(db_session, email="alice@example.com", name="Alice")

    assert user.email == "alice@example.com"
    assert user.status == "active"
    assert user.platform_role is None
    assert user.organization_id is None


def test_user_email_is_unique_platform_wide(db_session):
    make_user(db_session, email="dup@example.com", name="First")
    try:
        make_user(db_session, email="dup@example.com", name="Second")
        raised = False
    except Exception:
        raised = True
    assert raised


# --- 2. Create organization membership ---------------------------------


def test_create_organization_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session)

    membership = make_membership(
        db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER"
    )

    assert membership.user_id == user.id
    assert membership.organization_id == uuid.UUID(org["id"])
    assert membership.role == "HSE_MANAGER"
    assert membership.status == MembershipStatus.ACTIVE


# --- 3. User can belong to multiple organizations -----------------------


def test_user_can_belong_to_multiple_organizations(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    user = make_user(db_session)

    make_membership(
        db_session, user_id=user.id, organization_id=uuid.UUID(org_a["id"]), role="ORG_ADMIN"
    )
    make_membership(
        db_session, user_id=user.id, organization_id=uuid.UUID(org_b["id"]), role="VIEWER"
    )

    memberships = membership_service.list_for_user(db_session, user_id=user.id)
    roles_by_org = {m.organization_id: m.role for m in memberships}

    assert len(memberships) == 2
    assert roles_by_org[uuid.UUID(org_a["id"])] == "ORG_ADMIN"
    assert roles_by_org[uuid.UUID(org_b["id"])] == "VIEWER"


# --- 4. Duplicate membership is rejected --------------------------------


def test_duplicate_membership_is_rejected(client, db_session):
    org = create_org(client)
    user = make_user(db_session)
    make_membership(
        db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="VIEWER"
    )

    try:
        make_membership(
            db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="ORG_ADMIN"
        )
        assert False, "expected KnowledgeValidationError"
    except KnowledgeValidationError:
        pass

    # Still exactly one membership row, with the original role untouched.
    memberships = membership_service.list_for_user(db_session, user_id=user.id)
    assert len(memberships) == 1
    assert memberships[0].role == "VIEWER"


def test_membership_creation_requires_existing_organization(db_session):
    user = make_user(db_session)

    try:
        membership_service.create(
            db_session,
            organization_id=uuid.uuid4(),
            obj_in=OrganizationMembershipCreate(user_id=user.id, role=OrganizationRole.VIEWER),
        )
        assert False, "expected KnowledgeNotFoundError"
    except KnowledgeNotFoundError:
        pass


def test_membership_creation_requires_existing_user(client, db_session):
    org = create_org(client)

    try:
        membership_service.create(
            db_session,
            organization_id=uuid.UUID(org["id"]),
            obj_in=OrganizationMembershipCreate(user_id=uuid.uuid4(), role=OrganizationRole.VIEWER),
        )
        assert False, "expected KnowledgeNotFoundError"
    except KnowledgeNotFoundError:
        pass


# --- HTTP: membership endpoints ------------------------------------------


def test_add_member_http_requires_users_manage_permission(client, db_session):
    org = create_org(client)
    admin = make_user(db_session, email="admin@example.com", name="Admin")
    make_membership(
        db_session, user_id=admin.id, organization_id=uuid.UUID(org["id"]), role="ORG_ADMIN"
    )
    new_member = make_user(db_session, email="newmember@example.com", name="New Member")

    response = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": str(new_member.id), "role": "HSE_ANALYST"},
        headers=dev_auth_headers(admin.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == str(new_member.id)
    assert body["role"] == "HSE_ANALYST"
    assert body["status"] == "ACTIVE"


def test_add_member_http_denied_for_viewer(client, db_session):
    org = create_org(client)
    viewer = make_user(db_session, email="viewer@example.com", name="Viewer")
    make_membership(
        db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER"
    )
    other_user = make_user(db_session, email="other@example.com", name="Other")

    response = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": str(other_user.id), "role": "VIEWER"},
        headers=dev_auth_headers(viewer.id),
    )

    assert response.status_code == 403


def test_list_members_http(client, db_session):
    org = create_org(client)
    admin = make_user(db_session, email="admin2@example.com", name="Admin")
    make_membership(
        db_session, user_id=admin.id, organization_id=uuid.UUID(org["id"]), role="ORG_ADMIN"
    )

    response = client.get(
        f"/api/v1/organizations/{org['id']}/members", headers=dev_auth_headers(admin.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["user_id"] == str(admin.id)


def test_get_member_http(client, db_session):
    org = create_org(client)
    admin = make_user(db_session, email="admin3@example.com", name="Admin")
    make_membership(
        db_session, user_id=admin.id, organization_id=uuid.UUID(org["id"]), role="ORG_ADMIN"
    )

    response = client.get(
        f"/api/v1/organizations/{org['id']}/members/{admin.id}",
        headers=dev_auth_headers(admin.id),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ORG_ADMIN"


# --- 8. Organization A cannot access Organization B's members (HTTP) -----


def test_org_a_admin_cannot_list_org_b_members(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    admin_a = make_user(db_session, email="admina@example.com", name="Admin A")
    make_membership(
        db_session, user_id=admin_a.id, organization_id=uuid.UUID(org_a["id"]), role="ORG_ADMIN"
    )
    member_b = make_user(db_session, email="memberb@example.com", name="Member B")
    make_membership(
        db_session, user_id=member_b.id, organization_id=uuid.UUID(org_b["id"]), role="VIEWER"
    )

    # admin_a has no membership at all in org_b, so every org_b members
    # route must deny them — including "just listing", not only writes.
    response = client.get(
        f"/api/v1/organizations/{org_b['id']}/members", headers=dev_auth_headers(admin_a.id)
    )

    assert response.status_code == 403
