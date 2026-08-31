"""KnowledgeDocumentVersion service.

Versions are immutable once written, and re-ingesting byte-identical
content for the same document must not create a diverging duplicate row:
`create` is idempotent on (document_id, content_hash) — if a version with
that exact hash already exists for the document, it is returned as-is
rather than creating a new one. The unique constraint on the table is the
safety net for concurrent writers; this check is what makes the common
case (a caller retries, or an ingestion job reprocesses the same file) a
no-op instead of an integrity error.

Every method here takes an already-resolved, tenant-checked
`KnowledgeDocument` rather than a bare id — the caller (the API route) is
responsible for resolving and authorizing the document first via
`knowledge_document_service.get(...)`, exactly the same shape as the
foundation's `get_organization_or_404` pattern.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate


class KnowledgeDocumentVersionService:
    def create(
        self,
        db: Session,
        *,
        document: KnowledgeDocument,
        obj_in: KnowledgeDocumentVersionCreate,
    ) -> KnowledgeDocumentVersion:
        existing = db.execute(
            select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.document_id == document.id,
                KnowledgeDocumentVersion.content_hash == obj_in.content_hash,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        previous_current_id = document.current_version_id

        version = KnowledgeDocumentVersion(document_id=document.id, **obj_in.model_dump())
        db.add(version)
        db.flush()  # assign version.id without committing yet

        if previous_current_id is not None and previous_current_id != version.id:
            previous = db.get(KnowledgeDocumentVersion, previous_current_id)
            if previous is not None and previous.superseded_at is None:
                previous.superseded_at = utcnow()

        document.current_version_id = version.id

        db.commit()
        db.refresh(version)
        return version

    def list_for_document(
        self,
        db: Session,
        *,
        document: KnowledgeDocument,
        skip: int = 0,
        limit: int = 100,
    ) -> list[KnowledgeDocumentVersion]:
        stmt = (
            select(KnowledgeDocumentVersion)
            .where(KnowledgeDocumentVersion.document_id == document.id)
            .order_by(KnowledgeDocumentVersion.created_at)
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())


knowledge_document_version_service = KnowledgeDocumentVersionService()
