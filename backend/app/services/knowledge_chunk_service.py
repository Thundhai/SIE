"""KnowledgeChunk service.

No HTTP endpoint exposes chunk creation in this milestone (there is no
document-processing step yet to produce chunks from — see
app/ingestion, currently an empty placeholder package). This service
exists so that layer can be built against a stable interface later, and
so lineage/provenance can be exercised and tested now. Like
KnowledgeDocumentVersionService, methods take an already-resolved,
tenant-checked `KnowledgeDocumentVersion` rather than a bare id.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.schemas.knowledge_chunk import KnowledgeChunkCreate


class KnowledgeChunkService:
    def create_many(
        self,
        db: Session,
        *,
        document_version: KnowledgeDocumentVersion,
        chunks_in: list[KnowledgeChunkCreate],
    ) -> list[KnowledgeChunk]:
        objs = [
            KnowledgeChunk(document_version_id=document_version.id, **chunk_in.model_dump())
            for chunk_in in chunks_in
        ]
        db.add_all(objs)
        db.commit()
        for obj in objs:
            db.refresh(obj)
        return objs

    def list_for_version(
        self,
        db: Session,
        *,
        document_version: KnowledgeDocumentVersion,
        skip: int = 0,
        limit: int = 1000,
    ) -> list[KnowledgeChunk]:
        stmt = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_version_id == document_version.id)
            .order_by(KnowledgeChunk.chunk_index)
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())


knowledge_chunk_service = KnowledgeChunkService()
