"""Semantic retrieval API — the one HTTP entry point onto
`RetrievalService`.

    human OR machine caller -> RequestContext -> [organization_id requested?]
        -> authorize_context(KNOWLEDGE_READ) -> allowed scope
        -> RetrievalService -> RetrievalResponse

Mirrors `app/api/v1/ingestion.py`'s own authorization shape (calling the
authorization check directly rather than a path-based dependency, since
— like ingestion — this route has no `{organization_id}` URL segment: a
search can target GLOBAL knowledge alone, which has no organization at
all) with one deliberate difference, spelled out because it departs from
that precedent:

  * **Every request must be authenticated**, even a GLOBAL-only search
    with no `organization_id` — per the milestone's own "for
    global-only search, authorization rules must still apply"
    instruction.
  * **`filters.organization_id`, if present, must be authorized before
    it is trusted.** `app.api.deps_context.authorize_context(...,
    permission=KNOWLEDGE_READ, organization_id=...)` is called exactly as
    ingestion.py calls `authorization_service.can()` for
    `KNOWLEDGE_MANAGE` — a human caller must have an ACTIVE membership in
    that organization whose role grants `knowledge:read`; a machine
    caller must be scoped to that exact organization (never overridable,
    item 36) and hold the `knowledge:read` scope — or the request is
    rejected with 403. This is what makes "Do NOT allow the client to
    bypass authorization by passing another organization_id" true: the
    value only ever reaches `RetrievalService` after this check passes,
    never before.
  * **`filters.organization_id` omitted -> GLOBAL-only.** For a *human*
    caller this means no further authorization check beyond
    authentication — a deliberate, narrower rule than the write path's
    own "no organization_id -> only a PLATFORM_ADMIN succeeds" behavior
    (see `app/api/v1/ingestion.py`/`knowledge.py`'s own
    `_authorize_manage()`), tuned for *writing* GLOBAL knowledge, a
    meaningfully more privileged action than *reading* already-published
    GLOBAL knowledge. A *machine* caller still needs the `knowledge:read`
    scope even for a GLOBAL-only search — it has no membership-derived
    role to fall back on the way a human's authentication alone implies
    one, only whatever scopes it was explicitly granted, so least
    privilege applies to GLOBAL reads too — see
    `app.api.deps_context.authorize_context()`'s own docstring, which
    encodes this exact rule for both identity kinds.

**Machine-client access (Intelligence Platform Integration & Enterprise
API v0.1, items 16, 20, 38).** A machine client holding `knowledge:read`
can now call this endpoint too — the same evidence-selection/sufficiency/
privacy-gate pipeline `RetrievalService` already enforces for a human
caller applies identically; nothing about that pipeline is bypassed or
duplicated here (item 20).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, authorize_context, get_request_context
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.retrieval.filters import RetrievalFilters
from app.retrieval.results import RetrievalResponse
from app.retrieval.retrieval_service import retrieval_service
from app.schemas.retrieval import (
    EmbeddingModelRead,
    RetrievalResultRead,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from app.services.permissions import Permission

router = APIRouter(prefix="/knowledge/retrieval", tags=["retrieval"])


@router.post(
    "/search",
    response_model=RetrievalSearchResponse,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def search_knowledge(
    payload: RetrievalSearchRequest,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> RetrievalSearchResponse:
    organization_id = payload.filters.organization_id
    if not authorize_context(db, context, permission=Permission.KNOWLEDGE_READ, organization_id=organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing knowledge:read permission in the requested organization.",
        )
    _audit_knowledge_query(db, context=context, organization_id=organization_id, endpoint="retrieval_search")

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


def _audit_knowledge_query(
    db: Session, *, context: RequestContext, organization_id: uuid.UUID | None, endpoint: str
) -> None:
    from app.services.audit_service import AuditAction, audit_service

    audit_service.log(
        db,
        action=AuditAction.KNOWLEDGE_QUERY,
        resource_type="KnowledgeRetrieval",
        organization_id=organization_id,
        user_id=context.user_id,
        metadata={"endpoint": endpoint, "caller_kind": context.kind},
    )
