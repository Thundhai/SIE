"""Evidence-grounded RAG API — the one HTTP entry point onto Commercial
Core's RAG capability (milestone item 21; Roadmap Phase 2, item 4).

    human OR machine caller -> RequestContext -> authorize_context(KNOWLEDGE_READ)
        -> resolve_authorized_organization_id -> CommercialCoreClient.query_rag
        -> RAGAnswerDTO -> RAGAnswerRead

**History.** M43-IP-03 extracted the `app/rag/` package to the private
Commercial Core repository and left this route a 501 stub. It now calls
through `app.integrations.commercial_core`, the same seam Attention,
Analytics, Enterprise Intelligence and Decisions use. When Commercial Core
is not configured for this deployment the route still returns that 501.

**Contract.** The answer shape is `sie_contract.RAGAnswerDTO` (contract
0.8.0, Commercial Core PR #19), whose `outcome` says whether an answer was
produced at all.

**Authorization is unchanged** and still runs first: `filters.organization_id`
is authorized via `authorize_context(..., KNOWLEDGE_READ, ...)`, then the
operative organization is resolved with `resolve_authorized_organization_id()`
(a machine caller always gets its credential's own organization).

**What the Commercial Core boundary cannot do yet, and how this route says so:**

- *GLOBAL-only queries* (no `filters.organization_id`). Commercial Core's
  service credential is bound to one organization and the relay always
  answers for that organization, which would include its private
  documents. Forwarding a GLOBAL request would answer from an organization
  the caller never named, so it is refused with 501 instead.
- *Retrieval filters* other than `organization_id`. The relay accepts only
  `query` and `top_k`. Silently dropping a filter would answer from wider
  evidence than the caller asked for, so a request carrying one is
  rejected with 422.
- *`top_k` above 20*, Commercial Core's own limit. `RAGQueryRequest`
  declares that bound, so the published schema states it and FastAPI
  rejects a larger value with 422 before this route runs.

**Every RAG outcome is HTTP 200**, as it was before extraction: abstaining
(insufficient evidence, a source conflict, a rejected unsupported claim, a
provider failure, a privacy block) is a valid result, carried in `outcome`
with a plain-language `explanation`. Only a failure to *reach* or *trust*
Commercial Core is an HTTP error.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sie_contract import RAGAnswerDTO
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import (
    RequestContext,
    authorize_context,
    get_request_context,
    resolve_authorized_organization_id,
)
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.errors import ApiError, ErrorCode
from app.core.request_id import get_request_id
from app.integrations.commercial_core import (
    CommercialCoreCapabilityDisabledError,
    CommercialCoreIntegrationError,
    CommercialCoreTenantNotEntitledError,
    CommercialCoreUnavailable,
    CommercialCoreValidationError,
    get_commercial_core_client,
    tenant_not_entitled_error,
)
from app.integrations.tenant_assertion import tenant_actor_from_context
from app.schemas.rag import RAGAnswerRead, RAGCitationRead, RAGQueryRequest
from app.services.permissions import Permission

router = APIRouter(prefix="/knowledge/rag", tags=["rag"])


RAG_NOT_ENABLED_REASON = "RAG_NOT_ENABLED"
GLOBAL_QUERY_NOT_SUPPORTED_REASON = "GLOBAL_QUERY_NOT_SUPPORTED"


def _map_commercial_core_rag_error(exc: CommercialCoreIntegrationError) -> ApiError:
    """Mirrors `intelligence_decisions.py::_map_commercial_core_decision_error()`:
    a validation rejection is 422 and everything else is 503
    `MODEL_NOT_AVAILABLE` with the client's fixed, safe message. One
    addition: RAG being switched off on Commercial Core (503,
    `retryable: false`) gets its own message and `details.reason`, so a
    caller can tell "not enabled here" from "temporarily unreachable".
    Not being entitled (SIE-2) is a 403, as in the other routers."""
    if isinstance(exc, CommercialCoreTenantNotEntitledError):
        return tenant_not_entitled_error()
    if isinstance(exc, CommercialCoreCapabilityDisabledError):
        return ApiError(
            status_code=503,
            code=ErrorCode.MODEL_NOT_AVAILABLE,
            message="Knowledge question-answering is not enabled on this deployment.",
            details={"reason": RAG_NOT_ENABLED_REASON, "retryable": False},
        )
    if isinstance(exc, CommercialCoreValidationError):
        return ApiError(status_code=422, code=ErrorCode.VALIDATION_ERROR, message=str(exc))
    return ApiError(status_code=503, code=ErrorCode.MODEL_NOT_AVAILABLE, message=str(exc), details={"retryable": True})


def _unsupported_filters(payload: RAGQueryRequest) -> list[str]:
    filters = payload.filters.model_dump(exclude={"organization_id"})
    return sorted(name for name, value in filters.items() if value is not None)


def _to_read(dto: RAGAnswerDTO) -> RAGAnswerRead:
    return RAGAnswerRead(
        organization_id=dto.organization_id,
        query=dto.query,
        outcome=dto.outcome,
        answer=dto.answer,
        explanation=dto.explanation,
        citations=[RAGCitationRead.model_validate(c, from_attributes=True) for c in dto.citations],
        as_of=dto.as_of.as_of,
        generated_at=dto.as_of.generated_at,
    )


@router.post(
    "/query",
    response_model=RAGAnswerRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
    responses={
        422: {"description": "Invalid request, a retrieval filter Commercial Core cannot apply yet, or top_k above 20."},
        501: {"description": "Commercial Core is not configured for this deployment, or the query names no organization."},
        503: {"description": "Commercial Core is unavailable, or RAG is not enabled on it (`details.reason` = RAG_NOT_ENABLED)."},
    },
)
def query_knowledge(
    payload: RAGQueryRequest,
    context: RequestContext = Depends(get_request_context),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RAGAnswerRead:
    requested_organization_id = payload.filters.organization_id
    if not authorize_context(db, context, permission=Permission.KNOWLEDGE_READ, organization_id=requested_organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing knowledge:read permission in the requested organization.",
        )

    if requested_organization_id is None:
        raise ApiError(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code=ErrorCode.MODEL_NOT_AVAILABLE,
            message=(
                "Evidence-grounded RAG needs filters.organization_id: questions over GLOBAL knowledge "
                "alone are not available through Commercial Core yet."
            ),
            details={"reason": GLOBAL_QUERY_NOT_SUPPORTED_REASON},
        )

    unsupported = _unsupported_filters(payload)
    if unsupported:
        raise ApiError(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="These retrieval filters are not supported by evidence-grounded RAG yet: " + ", ".join(unsupported) + ".",
            details={"unsupported_filters": unsupported},
        )

    organization_id = resolve_authorized_organization_id(context, requested_organization_id)
    try:
        client = get_commercial_core_client()
        dto = client.query_rag(
            organization_id=organization_id,
            query=payload.query,
            top_k=payload.top_k,
            request_id=request_id,
            tenant_actor=tenant_actor_from_context(context, Permission.KNOWLEDGE_READ),
        )
    except CommercialCoreUnavailable:
        raise
    except CommercialCoreIntegrationError as exc:
        raise _map_commercial_core_rag_error(exc) from exc

    return _to_read(dto)
