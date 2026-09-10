"""Evidence-grounded RAG API — the one HTTP entry point onto `RAGService`
(milestone item 21).

    human OR machine caller -> RequestContext -> [organization_id requested?]
        -> authorize_context(KNOWLEDGE_READ) -> allowed scope
        -> RAGService -> RAGResponse

Authorization is byte-for-byte the same shape `app/api/v1/retrieval.py`
already uses (see that module's own docstring for the full rationale,
including why a GLOBAL-only query requires only authentication for a
*human* caller, but still requires the `knowledge:read` scope for a
*machine* caller): `filters.organization_id`, if present, must be
authorized via `app.api.deps_context.authorize_context(...,
KNOWLEDGE_READ, organization_id=...)` before it is ever passed to
`RAGService` as `allowed_organization_id`. There is no second
tenant-isolation mechanism here (milestone item 18) — RAG reuses exactly
this one.

**Milestone item 21: the client cannot select an embedding model or an
LLM provider/model.** `RAGQueryRequest` has no field for either — both
are resolved server-side by `RAGService` from app settings.

**Machine-client access (Intelligence Platform Integration & Enterprise
API v0.1, items 16, 20, 38).** A machine client holding `knowledge:read`
can now call this endpoint too — every safeguard `RAGService` already
enforces (evidence selection, sufficiency, the privacy gate, citation
validation) applies identically regardless of caller kind; the API layer
never bypasses or reimplements any of it (item 20).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, authorize_context, get_request_context
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.rag.rag_service import rag_service
from app.rag.results import RAGResponse
from app.retrieval.filters import RetrievalFilters
from app.schemas.rag import (
    CitationRead,
    RAGQueryRequest,
    RAGQueryResponse,
    SourceConflictRead,
    SourceRead,
)
from app.services.permissions import Permission

router = APIRouter(prefix="/knowledge/rag", tags=["rag"])


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def query_knowledge(
    payload: RAGQueryRequest,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> RAGQueryResponse:
    organization_id = payload.filters.organization_id
    if not authorize_context(db, context, permission=Permission.KNOWLEDGE_READ, organization_id=organization_id):
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

    result: RAGResponse = rag_service.query(
        db,
        query_text=payload.query,
        allowed_organization_id=organization_id,
        user_id=context.user_id,  # None for a machine caller -- rag_service.py's own audit logging handles that
        filters=filters,
        top_k=payload.top_k,
    )

    return _to_response(result)


def _to_response(result: RAGResponse) -> RAGQueryResponse:
    citations = [
        CitationRead(
            citation_id=c.citation_id,
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            document_version_id=c.document_version_id,
            source_id=c.source_id,
            source=c.source_name,
            document=c.document_title,
            version=c.version_label,
            location=c.location,
            content_type=c.content_type,
            verification_status=c.verification_status,
            extraction_quality=c.extraction_quality,
            source_authority_level=c.source_authority_level,
            similarity=c.similarity,
            scope=c.scope,
            organization_id=c.organization_id,
        )
        for c in result.citations
    ]

    sources_by_id: dict[uuid.UUID, SourceRead] = {}
    for c in result.citations:
        sources_by_id.setdefault(
            c.source_id,
            SourceRead(
                source_id=c.source_id,
                source=c.source_name,
                scope=c.scope,
                verification_status=c.verification_status,
            ),
        )

    conflicts = [
        SourceConflictRead(
            citation_id_a=cf.citation_id_a,
            citation_id_b=cf.citation_id_b,
            statement_a=cf.statement_a,
            statement_b=cf.statement_b,
            source_a=cf.source_name_a,
            source_b=cf.source_name_b,
            version_a=cf.version_label_a,
            version_b=cf.version_label_b,
            effective_date_a=cf.effective_date_a,
            effective_date_b=cf.effective_date_b,
        )
        for cf in result.conflicts
    ]

    return RAGQueryResponse(
        query=result.query,
        outcome=result.outcome.value,
        evidence_state=result.evidence_state.value,
        answer=result.answer,
        citations=citations,
        sources=list(sources_by_id.values()),
        conflicts=conflicts,
        evidence_count=result.evidence_count,
        warnings=result.warnings,
        abstention_reason=result.abstention_reason,
        retrieval_metadata=result.retrieval_metadata,
        model_metadata=result.model_metadata,
        prompt_version=result.prompt_version,
    )
