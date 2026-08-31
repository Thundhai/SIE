"""Knowledge foundation API routes.

None of these routes live under `/organizations/{organization_id}/...`:
a KnowledgeSource can be GLOBAL (owned by no organization at all), so
there is no single tenant path segment that fits every request the way
there is for Site or DataSource. Instead, organization context is passed
explicitly as an `organization_id` query parameter wherever a request
needs it — omitted for GLOBAL, required and checked against the resolved
resource's actual owner for ORGANIZATION-scoped ones. This keeps the same
principle as the rest of the API (tenant scoping is explicit, never
inferred) while accommodating the one resource type that isn't always
tenant-owned.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.knowledge_source import KnowledgeSource
from app.schemas.knowledge_document import KnowledgeDocumentCreate, KnowledgeDocumentRead
from app.schemas.knowledge_document_version import (
    KnowledgeDocumentVersionCreate,
    KnowledgeDocumentVersionRead,
)
from app.schemas.knowledge_source import KnowledgeSourceCreate, KnowledgeSourceRead
from app.services.errors import KnowledgeNotFoundError, KnowledgeValidationError
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import knowledge_document_version_service
from app.services.knowledge_source_service import knowledge_source_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def get_knowledge_source_or_404(
    source_id: uuid.UUID,
    organization_id: uuid.UUID | None = Query(
        default=None,
        description="Required, and must match the source's own organization, to reach an "
        "ORGANIZATION-scoped source. Omit to reach a GLOBAL source.",
    ),
    db: Session = Depends(get_db),
) -> KnowledgeSource:
    source = knowledge_source_service.get(db, id=source_id, organization_id=organization_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found"
        )
    return source


def get_knowledge_document_or_404(
    document_id: uuid.UUID,
    organization_id: uuid.UUID | None = Query(
        default=None,
        description="Required, and must match the document's own organization, to reach an "
        "ORGANIZATION-scoped document. Omit to reach a GLOBAL document.",
    ),
    db: Session = Depends(get_db),
) -> KnowledgeDocument:
    document = knowledge_document_service.get(db, id=document_id, organization_id=organization_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found"
        )
    return document


# --- Knowledge sources --------------------------------------------------


@router.post("/sources", response_model=KnowledgeSourceRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_source(
    payload: KnowledgeSourceCreate,
    db: Session = Depends(get_db),
) -> KnowledgeSource:
    try:
        return knowledge_source_service.create(db, obj_in=payload)
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/sources", response_model=list[KnowledgeSourceRead])
def list_knowledge_sources(
    db: Session = Depends(get_db),
    organization_id: uuid.UUID | None = Query(
        default=None,
        description="Omit to list GLOBAL sources. Provide to list only that organization's "
        "private sources — never both scopes in one call.",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[KnowledgeSource]:
    return knowledge_source_service.list(
        db, organization_id=organization_id, skip=skip, limit=limit
    )


@router.get("/sources/{source_id}", response_model=KnowledgeSourceRead)
def get_knowledge_source(
    source: KnowledgeSource = Depends(get_knowledge_source_or_404),
) -> KnowledgeSource:
    return source


# --- Knowledge documents --------------------------------------------------


@router.post(
    "/documents", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED
)
def create_knowledge_document(
    payload: KnowledgeDocumentCreate,
    db: Session = Depends(get_db),
) -> KnowledgeDocument:
    try:
        return knowledge_document_service.create(db, obj_in=payload)
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentRead)
def get_knowledge_document(
    document: KnowledgeDocument = Depends(get_knowledge_document_or_404),
) -> KnowledgeDocument:
    return document


# --- Knowledge document versions -----------------------------------------


@router.post(
    "/documents/{document_id}/versions",
    response_model=KnowledgeDocumentVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_document_version(
    payload: KnowledgeDocumentVersionCreate,
    document: KnowledgeDocument = Depends(get_knowledge_document_or_404),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentVersion:
    return knowledge_document_version_service.create(db, document=document, obj_in=payload)


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[KnowledgeDocumentVersionRead],
)
def list_knowledge_document_versions(
    document: KnowledgeDocument = Depends(get_knowledge_document_or_404),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[KnowledgeDocumentVersion]:
    return knowledge_document_version_service.list_for_document(
        db, document=document, skip=skip, limit=limit
    )
