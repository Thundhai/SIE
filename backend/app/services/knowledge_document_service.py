"""KnowledgeDocument service.

The core rule enforced here: a document's `organization_id` is always
derived from its parent KnowledgeSource, never taken at face value from
the client. `KnowledgeDocumentCreate.organization_id` (if the caller sends
one) is treated only as an assertion of the tenant context the caller
expects — it must match what the source actually resolves to, or the
request is rejected. This is what prevents a caller from attaching a
document under organization A's source to organization B (and, for a
GLOBAL source, from smuggling in any organization_id at all).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.services.audit_service import AuditAction, audit_service
from app.services.base import NullableTenantScopedRepository
from app.services.errors import KnowledgeNotFoundError, KnowledgeValidationError
from app.services.knowledge_source_service import knowledge_source_service


class KnowledgeDocumentService(NullableTenantScopedRepository[KnowledgeDocument]):
    def __init__(self) -> None:
        super().__init__(KnowledgeDocument)

    def create(
        self,
        db: Session,
        *,
        obj_in: KnowledgeDocumentCreate,
        actor_user_id: uuid.UUID | None = None,
    ) -> KnowledgeDocument:
        source = knowledge_source_service.get_by_id_unscoped(db, id=obj_in.source_id)
        if source is None:
            raise KnowledgeNotFoundError(f"knowledge source {obj_in.source_id} not found")

        expected_organization_id = source.organization_id

        organization_id_mismatch = (
            obj_in.organization_id is not None
            and obj_in.organization_id != expected_organization_id
        )
        if organization_id_mismatch:
            raise KnowledgeValidationError(
                "organization_id does not match the source's organization; "
                "a document cannot be attached to a different organization than its source"
            )
        if expected_organization_id is not None and obj_in.organization_id is None:
            raise KnowledgeValidationError(
                "organization_id is required when creating a document under an "
                "organization-scoped knowledge source"
            )
        if expected_organization_id is None and obj_in.organization_id is not None:
            raise KnowledgeValidationError(
                "organization_id must be omitted when creating a document under a "
                "GLOBAL knowledge source"
            )

        data = obj_in.model_dump(exclude={"organization_id"})
        obj = KnowledgeDocument(organization_id=expected_organization_id, **data)
        db.add(obj)
        db.commit()
        db.refresh(obj)

        audit_service.log(
            db,
            action=AuditAction.DOCUMENT_CREATED,
            resource_type="KnowledgeDocument",
            resource_id=obj.id,
            organization_id=obj.organization_id,
            user_id=actor_user_id,
            metadata={"source_id": str(obj.source_id), "document_type": obj.document_type},
        )
        return obj

    def list_for_source(
        self,
        db: Session,
        *,
        source_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[KnowledgeDocument]:
        """List documents under one source, still tenant-filtered exactly
        like `list()` — provided for internal/service-level use (e.g.
        tests, future ingestion tooling); no HTTP endpoint exposes this in
        this milestone."""
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.source_id == source_id)
        if organization_id is None:
            stmt = stmt.where(KnowledgeDocument.organization_id.is_(None))
        else:
            stmt = stmt.where(KnowledgeDocument.organization_id == organization_id)
        stmt = stmt.order_by(KnowledgeDocument.created_at).offset(skip).limit(limit)
        return list(db.execute(stmt).scalars().all())


knowledge_document_service = KnowledgeDocumentService()
