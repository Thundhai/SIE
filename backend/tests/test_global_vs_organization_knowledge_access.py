"""Milestone test items 13-14: global knowledge stays reachable
independent of organization membership; organization knowledge requires
an authorized tenant context.

Global knowledge access itself is deliberately never routed through
TenantContext/authorization at all (see
app/services/tenant_context.py's module docstring, and
app/services/knowledge_source_service.py, unchanged by this milestone) —
that absence *is* the feature being tested here: reading a GLOBAL source
requires nothing about the caller, while establishing trusted access to
an ORGANIZATION source's data requires a real, active membership.
"""

import pytest

from app.models.enums import MembershipStatus, ScopeType
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.schemas.organization import OrganizationCreate
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services.knowledge_source_service import knowledge_source_service
from app.services.membership_service import membership_service
from app.services.organization_service import organization_service
from app.services.permissions import Permission
from app.services.tenant_context import TenantContextError, authorize_tenant_context
from app.services.user_service import user_service


def test_global_knowledge_source_readable_with_no_user_no_org_at_all(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )

    # No TenantContext, no user, no membership anywhere in this test —
    # global knowledge just doesn't need any of that.
    fetched = knowledge_source_service.get(db_session, id=source.id, organization_id=None)

    assert fetched is not None
    assert fetched.organization_id is None


def test_global_knowledge_source_readable_regardless_of_the_readers_org_membership(db_session):
    """A user who belongs to *some* organization, or none at all, sees the
    same global knowledge either way."""
    org = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org"))
    user_with_membership = user_service.create(
        db_session, obj_in=UserCreate(email="member@example.com", name="Member")
    )
    membership_service.create(
        db_session,
        organization_id=org.id,
        obj_in=OrganizationMembershipCreate(user_id=user_with_membership.id, role="VIEWER"),
    )
    user_service.create(db_session, obj_in=UserCreate(email="noorg@example.com", name="No Org"))

    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )

    # Neither user's membership status is even consulted for this read.
    assert knowledge_source_service.get(db_session, id=source.id, organization_id=None) is not None


def test_organization_knowledge_requires_authorized_tenant_context(db_session):
    org = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org"))
    user = user_service.create(
        db_session, obj_in=UserCreate(email="analyst@example.com", name="Analyst")
    )
    membership_service.create(
        db_session,
        organization_id=org.id,
        obj_in=OrganizationMembershipCreate(user_id=user.id, role="HSE_ANALYST"),
    )
    org_source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.ORGANIZATION,
            organization_id=org.id,
            publisher="Acme",
            name="Internal Procedure",
            source_type="internal_procedure",
        ),
    )

    # The org member, with an authorized tenant context, can read it and
    # has knowledge:read.
    context = authorize_tenant_context(db_session, user_id=user.id, organization_id=org.id)
    assert context.has_permission(Permission.KNOWLEDGE_READ)
    fetched = knowledge_source_service.get(db_session, id=org_source.id, organization_id=org.id)
    assert fetched is not None

    # Without an org context (organization_id=None, exactly like a global
    # read), the same source is not reachable — it isn't global.
    assert knowledge_source_service.get(db_session, id=org_source.id, organization_id=None) is None


def test_outsider_cannot_obtain_a_tenant_context_for_organization_knowledge(db_session):
    org = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org"))
    outsider = user_service.create(
        db_session, obj_in=UserCreate(email="outsider@example.com", name="Outsider")
    )
    # No membership created for `outsider` in `org` at all.

    with pytest.raises(TenantContextError):
        authorize_tenant_context(db_session, user_id=outsider.id, organization_id=org.id)


def test_suspended_member_cannot_obtain_a_tenant_context_for_organization_knowledge(db_session):
    org = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org"))
    user = user_service.create(
        db_session, obj_in=UserCreate(email="suspendeduser@example.com", name="Suspended")
    )
    membership = membership_service.create(
        db_session,
        organization_id=org.id,
        obj_in=OrganizationMembershipCreate(user_id=user.id, role="HSE_ANALYST"),
    )
    membership_service.set_status(
        db_session, membership=membership, status=MembershipStatus.SUSPENDED
    )

    with pytest.raises(TenantContextError):
        authorize_tenant_context(db_session, user_id=user.id, organization_id=org.id)
