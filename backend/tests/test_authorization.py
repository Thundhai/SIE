"""Authorization service and TenantContext — covers milestone test items
5-7, 9-12, 15, and the guarded-construction requirement in section 5.
"""

import uuid

import pytest

from app.models.enums import MembershipStatus
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.organization import OrganizationCreate
from app.schemas.user import UserCreate
from app.services.authorization_service import authorization_service
from app.services.membership_service import membership_service
from app.services.organization_service import organization_service
from app.services.permissions import PLATFORM_ADMIN, Permission
from app.services.tenant_context import TenantContext, TenantContextError, authorize_tenant_context
from app.services.user_service import user_service


def make_org(db_session, name="Org"):
    return organization_service.create(db_session, obj_in=OrganizationCreate(name=name))


def make_user(db_session, email, name="User", platform_role=None):
    user = user_service.create(db_session, obj_in=UserCreate(email=email, name=name))
    if platform_role is not None:
        user = user_service.set_platform_role(db_session, user=user, platform_role=platform_role)
    return user


def make_membership(db_session, *, user_id, organization_id, role, status=MembershipStatus.ACTIVE):
    return membership_service.create(
        db_session,
        organization_id=organization_id,
        obj_in=OrganizationMembershipCreate(user_id=user_id, role=role, status=status),
    )


# --- 5-7. Membership status gates access --------------------------------


def test_active_membership_grants_access(db_session):
    org = make_org(db_session)
    user = make_user(db_session, "active@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org.id, role="HSE_USER")

    assert authorization_service.can(
        db_session, user_id=user.id, permission=Permission.SITE_READ, organization_id=org.id
    )


def test_suspended_membership_denies_access(db_session):
    org = make_org(db_session)
    user = make_user(db_session, "suspended@example.com")
    membership = make_membership(
        db_session, user_id=user.id, organization_id=org.id, role="ORG_ADMIN"
    )
    membership_service.set_status(
        db_session, membership=membership, status=MembershipStatus.SUSPENDED
    )

    assert not authorization_service.can(
        db_session, user_id=user.id, permission=Permission.SITE_READ, organization_id=org.id
    )


def test_revoked_membership_denies_access(db_session):
    org = make_org(db_session)
    user = make_user(db_session, "revoked@example.com")
    membership = make_membership(
        db_session, user_id=user.id, organization_id=org.id, role="ORG_ADMIN"
    )
    membership_service.set_status(
        db_session, membership=membership, status=MembershipStatus.REVOKED
    )

    assert not authorization_service.can(
        db_session, user_id=user.id, permission=Permission.SITE_READ, organization_id=org.id
    )


def test_invited_membership_does_not_grant_access(db_session):
    """INVITED is a pending state — not yet ACTIVE — so it must not grant
    access either, even though it isn't explicitly "denied" the way
    SUSPENDED/REVOKED are described in the spec."""
    org = make_org(db_session)
    user = make_user(db_session, "invited@example.com")
    make_membership(
        db_session,
        user_id=user.id,
        organization_id=org.id,
        role="VIEWER",
        status=MembershipStatus.INVITED,
    )

    assert not authorization_service.can(
        db_session, user_id=user.id, permission=Permission.ORGANIZATION_READ, organization_id=org.id
    )


# --- 8. Cross-organization denial ----------------------------------------


def test_user_from_organization_a_cannot_access_organization_b(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    user = make_user(db_session, "crosstenant@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org_a.id, role="ORG_ADMIN")

    assert authorization_service.can(
        db_session, user_id=user.id, permission=Permission.SITE_READ, organization_id=org_a.id
    )
    assert not authorization_service.can(
        db_session, user_id=user.id, permission=Permission.SITE_READ, organization_id=org_b.id
    )


# --- 9-10. Role permission sets -------------------------------------------


def test_hse_manager_has_expected_permissions(db_session):
    org = make_org(db_session)
    user = make_user(db_session, "hsemanager@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org.id, role="HSE_MANAGER")

    def can(permission: Permission) -> bool:
        return authorization_service.can(
            db_session, user_id=user.id, permission=permission, organization_id=org.id
        )

    assert can(Permission.SITE_MANAGE)
    assert can(Permission.KNOWLEDGE_MANAGE)
    assert can(Permission.KNOWLEDGE_VERIFY)
    assert can(Permission.INTERVENTION_MANAGE)
    # ...but member management stays reserved for admins.
    assert not can(Permission.USERS_MANAGE)
    assert not can(Permission.ORGANIZATION_MANAGE)


def test_viewer_cannot_perform_administrative_operations(db_session):
    org = make_org(db_session)
    user = make_user(db_session, "viewer@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org.id, role="VIEWER")

    def can(permission: Permission) -> bool:
        return authorization_service.can(
            db_session, user_id=user.id, permission=permission, organization_id=org.id
        )

    # Every :manage/:verify/:write permission is denied...
    assert not can(Permission.ORGANIZATION_MANAGE)
    assert not can(Permission.SITE_MANAGE)
    assert not can(Permission.KNOWLEDGE_MANAGE)
    assert not can(Permission.KNOWLEDGE_VERIFY)
    assert not can(Permission.SAFETY_DATA_WRITE)
    assert not can(Permission.INTERVENTION_MANAGE)
    assert not can(Permission.GOVERNANCE_MANAGE)
    assert not can(Permission.USERS_MANAGE)
    # ...while read access still works.
    assert can(Permission.ORGANIZATION_READ)
    assert can(Permission.KNOWLEDGE_READ)


# --- 11. Org Admin can manage members -------------------------------------


def test_org_admin_can_manage_organization_members(db_session):
    org = make_org(db_session)
    admin = make_user(db_session, "orgadmin@example.com")
    make_membership(db_session, user_id=admin.id, organization_id=org.id, role="ORG_ADMIN")

    assert authorization_service.can(
        db_session, user_id=admin.id, permission=Permission.USERS_MANAGE, organization_id=org.id
    )


# --- 12. Platform admin behavior -------------------------------------------


def test_platform_admin_has_permission_everywhere_without_membership(db_session):
    org = make_org(db_session)
    admin = make_user(db_session, "platformadmin@example.com", platform_role=PLATFORM_ADMIN)

    # No OrganizationMembership row exists for `admin` in `org` at all.
    assert authorization_service.can(
        db_session,
        user_id=admin.id,
        permission=Permission.KNOWLEDGE_VERIFY,
        organization_id=org.id,
    )
    assert authorization_service.can(
        db_session, user_id=admin.id, permission=Permission.USERS_MANAGE, organization_id=org.id
    )


def test_platform_admin_status_is_not_a_generic_bypass(db_session):
    """The platform-admin exception is gated on the specific
    `platform_role == PLATFORM_ADMIN` value — a user with no platform role
    at all gets no special treatment, even with a made-up string that
    isn't the real constant."""
    org = make_org(db_session)
    not_quite_admin = make_user(
        db_session, "notquite@example.com", platform_role="platform_admin"  # wrong case
    )

    assert not authorization_service.can(
        db_session,
        user_id=not_quite_admin.id,
        permission=Permission.USERS_MANAGE,
        organization_id=org.id,
    )


def test_can_returns_false_for_unknown_user(db_session):
    assert not authorization_service.can(
        db_session,
        user_id=uuid.uuid4(),
        permission=Permission.ORGANIZATION_READ,
        organization_id=uuid.uuid4(),
    )


# --- TenantContext ----------------------------------------------------


def test_tenant_context_cannot_be_constructed_directly():
    with pytest.raises(TypeError):
        TenantContext(
            user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            role="ORG_ADMIN",
            permissions=frozenset(Permission),
        )


def test_tenant_context_rejects_a_forged_token():
    """Even a caller who supplies *something* for the private `_token`
    field is rejected unless it's the exact sentinel only
    `authorize_tenant_context` holds — passing the missing-argument case
    above isn't the only thing enforcing this."""
    with pytest.raises(TypeError):
        TenantContext(
            user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            role="ORG_ADMIN",
            permissions=frozenset(Permission),
            _token=object(),
        )


def test_authorize_tenant_context_succeeds_for_active_membership(db_session):
    org = make_org(db_session)
    user = make_user(db_session, "contextuser@example.com")
    make_membership(db_session, user_id=user.id, organization_id=org.id, role="HSE_ANALYST")

    context = authorize_tenant_context(db_session, user_id=user.id, organization_id=org.id)

    assert context.user_id == user.id
    assert context.organization_id == org.id
    assert context.role == "HSE_ANALYST"
    assert context.has_permission(Permission.KNOWLEDGE_READ)
    assert not context.has_permission(Permission.USERS_MANAGE)


# --- 15. TenantContext cannot be created without active membership -------


def test_authorize_tenant_context_fails_without_membership(db_session):
    org = make_org(db_session)
    user = make_user(db_session, "nomembership@example.com")

    with pytest.raises(TenantContextError):
        authorize_tenant_context(db_session, user_id=user.id, organization_id=org.id)


def test_authorize_tenant_context_fails_for_suspended_membership(db_session):
    org = make_org(db_session)
    user = make_user(db_session, "suspendedcontext@example.com")
    membership = make_membership(
        db_session, user_id=user.id, organization_id=org.id, role="VIEWER"
    )
    membership_service.set_status(
        db_session, membership=membership, status=MembershipStatus.SUSPENDED
    )

    with pytest.raises(TenantContextError):
        authorize_tenant_context(db_session, user_id=user.id, organization_id=org.id)


def test_authorize_tenant_context_fails_for_unknown_user(db_session):
    org = make_org(db_session)

    with pytest.raises(TenantContextError):
        authorize_tenant_context(db_session, user_id=uuid.uuid4(), organization_id=org.id)
