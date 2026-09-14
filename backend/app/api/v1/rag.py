"""Evidence-grounded RAG API — the one HTTP entry point that used to
front `RAGService` (milestone item 21).

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** The entire
`app/rag/` package (evidence selection, sufficiency, conflict handling,
context construction, citation validation, RAG orchestration itself) has
been extracted to the private Commercial Core repository -- see
`sie-contract`'s `RAGAnswerDTO`/`CitationReferenceDTO` (in the Commercial
Core repository) for the public-shaped answer/citation types a future
integration would exchange, and
docs/M43_IP_03_PUBLIC_EXTRACTION.md for the full reasoning
(`app/schemas/rag.py`'s existing request/citation schemas are left in
place since they carry no algorithm, only field shapes).

Authorization is unchanged and still runs before the 501 -- this
endpoint used to reject an unauthorized `filters.organization_id` before
ever calling `RAGService`, and it still does; only the query itself is
now unavailable.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, authorize_context, get_request_context
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.integrations.commercial_core import commercial_core_client
from app.schemas.rag import RAGQueryRequest
from app.services.permissions import Permission

router = APIRouter(prefix="/knowledge/rag", tags=["rag"])


@router.post(
    "/query",
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def query_knowledge(
    payload: RAGQueryRequest,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    organization_id = payload.filters.organization_id
    if not authorize_context(db, context, permission=Permission.KNOWLEDGE_READ, organization_id=organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing knowledge:read permission in the requested organization.",
        )

    raise commercial_core_client.unavailable("Evidence-grounded RAG query")
