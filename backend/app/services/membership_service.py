"""OrganizationMembership service.

This is the write/read path for the authoritative user <-> organization
relationship (see app/models/organization_membership.py). It is
deliberately *not* built on `TenantScopedRepository`/
`NullableTenantScopedRepository`: those scope a table by *its own*
`organization_id` for a caller who already has a trusted tenant context.
Membership is different — it's one of the two inputs (alongside the user)
that *establishes* whether a tenant context is trustworthy in the first
place (see app/services/tenant_context.py), so its own queries are scoped
by `organization_id` directly here rather than through that pattern.

`create` enforces the one-row-per-(user, organization) invariant declared
by the table's unique constraint at the application layer too, so a
duplicate is rejected with a clear `KnowledgeValidationError` (reused from
the knowledge domain — same shape of error, same meaning: a structurally
invalid request) rather than surfacing a raw database `IntegrityError`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import MembershipStatus
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.services.audit_service import AuditAction, audit_service
from app.services.errors import KnowledgeNotFoundError, KnowledgeValidationError
from app.services.organization_service import organization_service


class OrganizationMembershipService:
    def create(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        obj_in: OrganizationMembershipCreate,
        actor_user_id: uuid.UUID | None = None,
    ) -> OrganizationMembership:
        if organization_service.get(db, id=organization_id) is None:
            raise KnowledgeNotFoundError(f"organization {organization_id} not found")
        if db.get(User, obj_in.user_id) is None:
            raise KnowledgeNotFoundError(f"user {obj_in.user_id} not found")

        existing = self._get_row(db, user_id=obj_in.user_id, organization_id=organization_id)
        if existing is not None:
            raise KnowledgeValidationError(
                f"user {obj_in.user_id} already has a membership in organization "
                f"{organization_id} (status={existing.status.value}); update it instead of "
                "creating a duplicate"
            )

        membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=obj_in.user_id,
            role=obj_in.role.value,
            status=obj_in.status,
        )
        db.add(membership)
        db.commit()
        db.refresh(membership)

        audit_service.log(
            db,
            action=AuditAction.MEMBER_ADDED,
            resource_type="OrganizationMembership",
            resource_id=membership.id,
            organization_id=organization_id,
            user_id=actor_user_id,
            metadata={"member_user_id": str(obj_in.user_id), "role": membership.role},
        )
        return membership

    def get(
        self, db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMembership | None:
        return self._get_row(db, user_id=user_id, organization_id=organization_id)

    def get_active_membership(
        self, db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> OrganizationMembership | None:
        """The check `authorization_service.py` and `tenant_context.py`
        actually rely on: a membership row that exists *and* is ACTIVE.
        SUSPENDED and REVOKED both return None here — from the
        authorization path's point of view they are indistinguishable
        from no membership at all."""
        membership = self._get_row(db, user_id=user_id, organization_id=organization_id)
        if membership is None or membership.status != MembershipStatus.ACTIVE:
            return None
        return membership

    def list_for_organization(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[OrganizationMembership]:
        stmt = (
            select(OrganizationMembership)
            .where(OrganizationMembership.organization_id == organization_id)
            .order_by(OrganizationMembership.created_at)
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    def list_for_user(self, db: Session, *, user_id: uuid.UUID) -> list[OrganizationMembership]:
        stmt = (
            select(OrganizationMembership)
            .where(OrganizationMembership.user_id == user_id)
            .order_by(OrganizationMembership.created_at)
        )
        return list(db.execute(stmt).scalars().all())

    def set_status(
        self,
        db: Session,
        *,
        membership: OrganizationMembership,
        status: MembershipStatus,
        actor_user_id: uuid.UUID | None = None,
    ) -> OrganizationMembership:
        """Covers suspend/revoke/reactivate — all are the same operation
        (transition the one row's status in place), so one method rather
        than three near-identical ones."""
        previous_status = membership.status
        membership.status = status
        db.add(membership)
        db.commit()
        db.refresh(membership)

        audit_service.log(
            db,
            action=AuditAction.MEMBER_STATUS_CHANGED,
            resource_type="OrganizationMembership",
            resource_id=membership.id,
            organization_id=membership.organization_id,
            user_id=actor_user_id,
            metadata={
                "member_user_id": str(membership.user_id),
                "previous_status": previous_status.value,
                "new_status": status.value,
            },
        )
        return membership

    def change_role(
        self,
        db: Session,
        *,
        membership: OrganizationMembership,
        role: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> OrganizationMembership:
        previous_role = membership.role
        membership.role = role
        db.add(membership)
        db.commit()
        db.refresh(membership)

        audit_service.log(
            db,
            action=AuditAction.MEMBER_ROLE_CHANGED,
            resource_type="OrganizationMembership",
            resource_id=membership.id,
            organization_id=membership.organization_id,
            user_id=actor_user_id,
            metadata={
                "member_user_id": str(membership.user_id),
                "previous_role": previous_role,
                "new_role": role,
            },
        )
        return membership

    def _get_row(
        self, db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> OrganizationMembership | None:
        stmt = select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
        )
        return db.execute(stmt).scalar_one_or_none()


membership_service = OrganizationMembershipService()
