"""KnowledgeSource service.

`create` is not built on the generic repository's create() because the
tenant context for a KnowledgeSource comes from the request body itself
(there is no `/organizations/{organization_id}/...` URL to derive it
from) — so this is the one place in the knowledge domain that has to
trust a client-supplied `organization_id`, and it does so only after
independently re-checking the scope/organization consistency rule (not
just relying on the Pydantic schema validator) and confirming the
organization actually exists.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.enums import ScopeType
from app.models.knowledge_source import KnowledgeSource
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.base import NullableTenantScopedRepository
from app.services.errors import KnowledgeValidationError
from app.services.organization_service import organization_service


class KnowledgeSourceService(NullableTenantScopedRepository[KnowledgeSource]):
    def __init__(self) -> None:
        super().__init__(KnowledgeSource)

    def create(self, db: Session, *, obj_in: KnowledgeSourceCreate) -> KnowledgeSource:
        if obj_in.scope_type == ScopeType.GLOBAL and obj_in.organization_id is not None:
            raise KnowledgeValidationError(
                "organization_id must be omitted for a GLOBAL knowledge source"
            )
        if obj_in.scope_type == ScopeType.ORGANIZATION:
            if obj_in.organization_id is None:
                raise KnowledgeValidationError(
                    "organization_id is required for an ORGANIZATION-scoped knowledge source"
                )
            if organization_service.get(db, id=obj_in.organization_id) is None:
                raise KnowledgeValidationError(
                    f"organization {obj_in.organization_id} does not exist"
                )

        obj = KnowledgeSource(**obj_in.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def get_by_id_unscoped(self, db: Session, *, id: uuid.UUID) -> KnowledgeSource | None:
        """See `NullableTenantScopedRepository.get_unscoped` — used only by
        KnowledgeDocumentService.create to resolve a source's real scope
        before enforcing it, never to answer a client-facing read."""
        return self.get_unscoped(db, id=id)


knowledge_source_service = KnowledgeSourceService()
