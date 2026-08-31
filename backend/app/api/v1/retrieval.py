"""Semantic retrieval API — the one HTTP entry point onto
`RetrievalService`.

    authenticated user -> [organization_id requested?]
        -> authorization_service.can(KNOWLEDGE_READ) -> allowed scope
        -> RetrievalService -> RetrievalResponse

Mirrors `app/api/v1/ingestion.py`'s own authorization shape (calling
`authorization_service.can()` directly rather than the path-based
`require_permission` dependency, since — like ingestion — this route has
no `{organization_id}` URL segment: a search can target GLOBAL knowledge
alone, which has no organization at all) with one deliberate difference,
spelled out because it departs from that precedent:

  * **Every request must be authenticated** (`get_dev_authenticated_user_id`),
    even a GLOBAL-only search with no `organization_id` — per the
    milestone's own "for global-only search, authorization rules must
    still apply" instruction. `POST /api/v1/knowledge/retrieval/search`
    therefore requires authentication where the sibling *read* routes in
    `app/api/v1/knowledge.py` currently do not (a known, documented gap
    there — see the README's "Known gaps" section).
  * **`filters.organization_id`, if present, must be authorized before
    it is trusted.** `authorization_service.can(..., permission=KNOWLEDGE_READ,
    organization_id=...)` is called exactly as ingestion.py calls it for
    `KNOWLEDGE_MANAGE` — the caller must have an ACTIVE membership in
    that organization whose role grants `knowledge:read`, or the request
    is rejected with 403. This is what makes "Do NOT allow the client to
    bypass authorization by passing another organization_id" true: the
    value only ever reaches `RetrievalService` after this check passes,
    never before.
  * **`filters.organization_id` omitted -> GLOBAL-only, no organization
    authorization check.** This is a deliberate, narrower rule than
    `authorization_service.can()`'s own "no organization_id -> only a
    PLATFORM_ADMIN succeeds" behavior — that behavior is tuned for
    *writing* GLOBAL knowledge (see ingestion.py), a meaningfully more
    privileged action than *reading* already-published GLOBAL knowledge.
    `authorization_service.py`'s own docstring already states this
    explicitly: "Global-knowledge reads are deliberately never routed
    through this method at all." Requiring only authentication (not
    platform-admin) for a GLOBAL-only search follows that stated design
    intent rather than the write-path's stricter rule.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_dev_authenticated_user_id
from app.retrieval.filters import RetrievalFilters
from app.retrieval.results import RetrievalResponse
from app.retrieval.retrieval_service import retrieval_service
from app.schemas.retrieval import (
    EmbeddingModelRead,
    RetrievalResultRead,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

router = APIRouter(prefix="/knowledge/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalSearchResponse)
def search_knowledge(
    payload: RetrievalSearchRequest,
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> RetrievalSearchResponse:
    organization_id = payload.filters.organization_id
    if organization_id is not None and not authorization_service.can(
        db, user_id=user_id, permission=Permission.KNOWLEDGE_READ, organization_id=organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing knowledge:read permission in the requested organization.",
        )

    filters = RetrievalFilters(
        source_id=payload.filters.source_id,
        document_id=payload.filters.document_id,
        document_version_id=payload.filters.document_version_id,
        content_type=payload.filters.content_type,
        industry_sector=payload.filters.industry_sector,
        jurisdiction=payload.filters.jurisdiction,
        verification_status=payload.filters.verification_status,
        effective_date_from=payload.filters.effective_date_from,
        effective_date_to=payload.filters.effective_date_to,
    )

    result: RetrievalResponse = retrieval_service.search(
        db,
        query_text=payload.query,
        allowed_organization_id=organization_id,
        filters=filters,
        top_k=payload.top_k,
        min_similarity=payload.min_similarity,
    )

    return RetrievalSearchResponse(
        query=result.query,
        outcome=result.outcome.value,
        embedding_model=EmbeddingModelRead(
            provider=result.embedding_provider,
            model_name=result.embedding_model,
            model_version=result.embedding_model_version,
        ),
        results=[
            RetrievalResultRead(
                rank=r.rank,
                chunk_id=r.chunk_id,
                similarity=r.similarity,
                relevance=r.relevance.value,
                content=r.content,
                content_type=r.content_type,
                source_id=r.source_id,
                document_id=r.document_id,
                document_version_id=r.document_version_id,
                source=r.source_name,
                document=r.document_title,
                version=r.version_label,
                location=r.location,
                page_number=r.page_number,
                sheet_name=r.sheet_name,
                row_number=r.row_number,
                slide_number=r.slide_number,
                section_title=r.section_title,
                section_path=r.section_path,
                extraction_quality=r.extraction_quality,
                extraction_method=r.extraction_method,
                source_authority_level=r.source_authority_level,
                verification_status=r.verification_status,
                scope=r.scope,
                organization_id=r.organization_id,
                jurisdiction=r.jurisdiction,
                industry_sector=r.industry_sector,
                publication_date=r.publication_date,
                effective_date=r.effective_date,
            )
            for r in result.results
        ],
        result_count=result.result_count,
        filters_applied=result.filters_applied,
        search_metadata=result.search_metadata,
    )
