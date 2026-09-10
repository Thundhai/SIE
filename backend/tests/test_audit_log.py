"""Audit log — covers milestone test item 17: "audit events are generated
for administrative/security-relevant actions where implemented."

Only the actions this milestone actually wires up are tested here (see
app/services/audit_service.py::AuditAction and the README's "Audit
foundation" section for the complete current list).
"""

import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.enums import MembershipStatus, ScopeType, VerificationStatus
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.schemas.organization import OrganizationCreate
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services.audit_service import AuditAction
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import knowledge_document_version_service
from app.services.knowledge_source_service import knowledge_source_service
from app.services.membership_service import membership_service
from app.services.organization_service import organization_service
from app.services.user_service import user_service


def audit_rows(db_session, *, action: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.action == action)
    return list(db_session.execute(stmt).scalars().all())


def test_knowledge_source_creation_is_audited(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )

    rows = audit_rows(db_session, action=AuditAction.KNOWLEDGE_SOURCE_CREATED)
    assert len(rows) == 1
    assert rows[0].resource_id == source.id
    assert rows[0].resource_type == "KnowledgeSource"
    assert rows[0].organization_id is None


def test_knowledge_verification_is_audited(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )
    actor_id = uuid.uuid4()

    knowledge_source_service.verify(
        db_session, source=source, status=VerificationStatus.VERIFIED, actor_user_id=actor_id
    )

    rows = audit_rows(db_session, action=AuditAction.KNOWLEDGE_VERIFIED)
    assert len(rows) == 1
    assert rows[0].resource_id == source.id
    assert rows[0].user_id == actor_id
    assert rows[0].event_metadata == {"previous_status": "PENDING", "new_status": "VERIFIED"}


def test_document_and_version_creation_are_audited(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )
    document = knowledge_document_service.create(
        db_session,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id, title="1910.147", document_type="regulation_text"
        ),
    )
    version = knowledge_document_version_service.create(
        db_session,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1", content_hash="hash-1", storage_reference="ref-1"
        ),
    )

    document_rows = audit_rows(db_session, action=AuditAction.DOCUMENT_CREATED)
    version_rows = audit_rows(db_session, action=AuditAction.DOCUMENT_VERSION_CREATED)

    assert len(document_rows) == 1
    assert document_rows[0].resource_id == document.id
    assert len(version_rows) == 1
    assert version_rows[0].resource_id == version.id


def test_idempotent_duplicate_version_is_not_re_audited(db_session):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )
    document = knowledge_document_service.create(
        db_session,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id, title="1910.147", document_type="regulation_text"
        ),
    )
    payload = KnowledgeDocumentVersionCreate(
        version_label="v1", content_hash="same-hash", storage_reference="ref"
    )

    knowledge_document_version_service.create(db_session, document=document, obj_in=payload)
    knowledge_document_version_service.create(db_session, document=document, obj_in=payload)

    rows = audit_rows(db_session, action=AuditAction.DOCUMENT_VERSION_CREATED)
    assert len(rows) == 1  # the second call was a no-op, not a new event


def test_member_added_is_audited(db_session):
    org = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org"))
    actor = user_service.create(
        db_session, obj_in=UserCreate(email="actor@example.com", name="Actor")
    )
    new_member = user_service.create(
        db_session, obj_in=UserCreate(email="newmember@example.com", name="New Member")
    )

    membership = membership_service.create(
        db_session,
        organization_id=org.id,
        obj_in=OrganizationMembershipCreate(user_id=new_member.id, role="VIEWER"),
        actor_user_id=actor.id,
    )

    rows = audit_rows(db_session, action=AuditAction.MEMBER_ADDED)
    assert len(rows) == 1
    assert rows[0].resource_id == membership.id
    assert rows[0].organization_id == org.id
    assert rows[0].user_id == actor.id
    assert rows[0].event_metadata["member_user_id"] == str(new_member.id)


def test_member_role_and_status_changes_are_audited(db_session):
    org = organization_service.create(db_session, obj_in=OrganizationCreate(name="Org"))
    user = user_service.create(
        db_session, obj_in=UserCreate(email="member@example.com", name="Member")
    )
    membership = membership_service.create(
        db_session,
        organization_id=org.id,
        obj_in=OrganizationMembershipCreate(user_id=user.id, role="VIEWER"),
    )

    membership_service.change_role(db_session, membership=membership, role="HSE_ANALYST")
    membership_service.set_status(
        db_session, membership=membership, status=MembershipStatus.SUSPENDED
    )

    role_rows = audit_rows(db_session, action=AuditAction.MEMBER_ROLE_CHANGED)
    status_rows = audit_rows(db_session, action=AuditAction.MEMBER_STATUS_CHANGED)

    assert len(role_rows) == 1
    assert role_rows[0].event_metadata == {
        "member_user_id": str(user.id),
        "previous_role": "VIEWER",
        "new_role": "HSE_ANALYST",
    }
    assert len(status_rows) == 1
    assert status_rows[0].event_metadata["new_status"] == "SUSPENDED"


def test_audit_log_never_contains_credential_like_fields(db_session):
    """Not a real secret-scanner — a structural check that the fields this
    milestone's own audit calls populate never happen to be named like a
    credential, matching the "do not log passwords/tokens/secrets"
    requirement for what's actually implemented here."""
    knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="OSHA",
            name="29 CFR 1910",
            source_type="regulation",
        ),
    )
    forbidden_keys = {"password", "token", "access_token", "refresh_token", "secret"}

    rows = db_session.execute(select(AuditLog)).scalars().all()
    for row in rows:
        metadata_keys = set((row.event_metadata or {}).keys())
        assert not (metadata_keys & forbidden_keys)
