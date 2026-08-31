"""Organization service.

Organization is the tenant root, not a tenant-owned resource, so it is
deliberately *not* built on `TenantScopedRepository` — there is no
organization_id to scope by. Every other service in this package scopes by
organization_id; this one is the sole, intentional exception.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate


class OrganizationService:
    def create(self, db: Session, *, obj_in: OrganizationCreate) -> Organization:
        obj = Organization(**obj_in.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def get(self, db: Session, *, id: uuid.UUID) -> Organization | None:
        stmt = select(Organization).where(Organization.id == id)
        return db.execute(stmt).scalar_one_or_none()


organization_service = OrganizationService()
