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

**Authentication/authorization (Intelligence Platform Integration &
Enterprise API v0.1, items 9, 16, 38, 48).** Every route below now
requires an authenticated caller — human or machine, via
`app.api.deps_context.RequestContext` — where previously (Knowledge
Foundation v0.1 through Universal Ingestion Engine v0.1) none of them
checked anything at all. This is a deliberate security tightening, not a
silent behavior change hidden from a reader of this file: before this
milestone, `POST /knowledge/sources` accepted a caller-supplied
`organization_id` with **no authorization check whatsoever** — any
unauthenticated caller could create an ORGANIZATION-scoped (or GLOBAL)
knowledge source for *any* organization it named. Item 48's "assume
every external caller is untrusted" and item 8's "never trust
organization_id from arbitrary client body data" both apply directly
here; this was the one place in the whole API surface that violated
them. See the README's "Known gaps" section (prior milestones) for
where this was previously documented as an open gap, and this
milestone's own final report for why it was closed now rather than left
for later.

  * **Reads** (`GET`) require `knowledge:read`, following
    `app/api/v1/retrieval.py`'s own already-established rule: an
    ORGANIZATION-scoped request (`organization_id` given) needs that
    permission in that organization; a GLOBAL-only request
    (`organization_id` omitted) needs only *authentication*, no specific
    permission — global content was never owned by any one
    organization's role or scope to begin with.
  * **Writes** (`POST`) require `knowledge:manage`, mirroring
    `app/api/v1/ingestion.py`'s own already-established rule exactly —
    including that GLOBAL writes are *stricter*, not looser, than an
    omitted check: only a `PLATFORM_ADMIN` human may write GLOBAL
    knowledge. A machine client can never write GLOBAL knowledge at all
    (it has no platform-admin concept — `ApiClient.organization_id` is
    always exactly one organization), only its own organization's,
    scoped and never overridable (item 36).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, authorize_context, get_request_context
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.knowledge_source import KnowledgeSource
from app.schemas.knowledge_chunk import KnowledgeChunkRead
from app.schemas.knowledge_document import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentRead,
)
from app.schemas.knowledge_document_version import (
    KnowledgeDocumentVersionCreate,
    KnowledgeDocumentVersionRead,
)
from app.schemas.knowledge_source import KnowledgeSourceCreate, KnowledgeSourceRead
from app.services.errors import KnowledgeNotFoundError, KnowledgeValidationError
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import (
    knowledge_document_version_service,
)
from app.services.knowledge_source_service import knowledge_source_service
from app.services.permissions import Permission

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _authorize_read(db: Session, context: RequestContext, organization_id: uuid.UUID | None) -> None:
    if not authorize_context(db, context, permission=Permission.KNOWLEDGE_READ, organization_id=organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing knowledge:read permission in the requested organization.",
        )


def _authorize_manage(db: Session, context: RequestContext, organization_id: uuid.UUID | None) -> None:
    """Deliberately NOT `authorize_context()` — that function's
    `organization_id is None -> authenticated is enough` rule is tuned
    for *reads* of already-published GLOBAL content (see
    `app/api/v1/retrieval.py`). Writing GLOBAL knowledge is a more
    privileged action (`app/api/v1/ingestion.py`'s own established
    rule): only a human `PLATFORM_ADMIN` may, and a machine client —
    which has no platform-admin concept at all — never can."""
    if context.is_machine:
        allowed = (
            organization_id is not None
            and organization_id == context.machine_organization_id
            and Permission.KNOWLEDGE_MANAGE.value in context.scopes
        )
    else:
        from app.services.authorization_service import authorization_service

        allowed = authorization_service.can(
            db, user_id=context.user_id, permission=Permission.KNOWLEDGE_MANAGE, organization_id=organization_id
        )
    if not allowed:
        detail = (
            "Missing knowledge:manage permission in the given organization."
            if organization_id is not None
            else "Writing GLOBAL knowledge requires platform-wide knowledge:manage access (human callers only)."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def get_knowledge_source_or_404(
    source_id: uuid.UUID,
    organization_id: uuid.UUID | None = Query(
        default=None,
        description="Required, and must match the source's own organization, to reach an "
        "ORGANIZATION-scoped source. Omit to reach a GLOBAL source.",
    ),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> KnowledgeSource:
    _authorize_read(db, context, organization_id)
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
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> KnowledgeDocument:
    _authorize_read(db, context, organization_id)
    document = knowledge_document_service.get(db, id=document_id, organization_id=organization_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found"
        )
    return document


# --- Knowledge sources --------------------------------------------------


@router.post(
    "/sources",
    response_model=KnowledgeSourceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_knowledge_source(
    payload: KnowledgeSourceCreate,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> KnowledgeSource:
    # payload.organization_id is caller-stated *intent* here (exactly
    # ingestion.py's own established shape for the one resource type
    # that isn't always tenant-owned) -- authorized before it is ever
    # trusted, never after.
    _authorize_manage(db, context, payload.organization_id)
    try:
        return knowledge_source_service.create(db, obj_in=payload)
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/sources", response_model=list[KnowledgeSourceRead], dependencies=[Depends(require_rate_limit(RateLimitClass.READ))]
)
def list_knowledge_sources(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
    organization_id: uuid.UUID | None = Query(
        default=None,
        description="Omit to list GLOBAL sources. Provide to list only that organization's "
        "private sources — never both scopes in one call.",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[KnowledgeSource]:
    _authorize_read(db, context, organization_id)
    return knowledge_source_service.list(
        db, organization_id=organization_id, skip=skip, limit=limit
    )


@router.get(
    "/sources/{source_id}",
    response_model=KnowledgeSourceRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_knowledge_source(
    source: KnowledgeSource = Depends(get_knowledge_source_or_404),
) -> KnowledgeSource:
    return source


# --- Knowledge documents --------------------------------------------------


@router.post(
    "/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_knowledge_document(
    payload: KnowledgeDocumentCreate,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> KnowledgeDocument:
    # organization_id is never taken from the request body here (see
    # KnowledgeDocumentCreate's own docstring) -- it is the *referenced
    # source's own* real organization_id (or None for a GLOBAL source)
    # that gets authorized, resolved server-side, before any document is
    # created under it.
    source = knowledge_source_service.get_by_id_unscoped(db, id=payload.source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"knowledge source {payload.source_id} not found")
    _authorize_manage(db, context, source.organization_id)
    try:
        return knowledge_document_service.create(db, obj_in=payload)
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_knowledge_document(
    document: KnowledgeDocument = Depends(get_knowledge_document_or_404),
) -> KnowledgeDocument:
    return document


# --- Knowledge document versions -----------------------------------------


@router.post(
    "/documents/{document_id}/versions",
    response_model=KnowledgeDocumentVersionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_knowledge_document_version(
    payload: KnowledgeDocumentVersionCreate,
    context: RequestContext = Depends(get_request_context),
    document: KnowledgeDocument = Depends(get_knowledge_document_or_404),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentVersion:
    # get_knowledge_document_or_404 already authorized a *read* of this
    # document (whatever organization_id the caller supplied for it) --
    # creating a new version under it is a manage-level action, checked
    # again here against the document's own real organization_id.
    _authorize_manage(db, context, document.organization_id)
    return knowledge_document_version_service.create(db, document=document, obj_in=payload)


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[KnowledgeDocumentVersionRead],
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
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


# --- Knowledge chunks (read-only) ------------------------------------------
#
# No chunk-*writing* endpoint exists anywhere in this API, by design — see
# the milestone spec and app/services/chunking_service.py's docstring:
# chunk generation is controlled by ingestion processing only. This one
# read endpoint exists because a future citation/evidence UI needs a
# stable way to fetch a specific version's chunks; it costs no new
# authorization mechanism because it reuses the exact same tenant check
# every other read route in this file already uses —
# `get_knowledge_document_or_404` requires the caller to already supply
# the document's own `organization_id` (or omit it for a GLOBAL document)
# to resolve the document at all, so a chunk can never be reached via the
# wrong organization. `get_for_document` below applies that same
# containment one level further: a `version_id` that exists but doesn't
# belong to *this* document 404s rather than leaking another document's
# chunks.


def get_knowledge_document_version_or_404(
    version_id: uuid.UUID,
    document: KnowledgeDocument = Depends(get_knowledge_document_or_404),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentVersion:
    version = knowledge_document_version_service.get_for_document(
        db, document=document, version_id=version_id
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document version not found"
        )
    return version


@router.get(
    "/documents/{document_id}/versions/{version_id}/chunks",
    response_model=list[KnowledgeChunkRead],
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_knowledge_chunks(
    version: KnowledgeDocumentVersion = Depends(get_knowledge_document_version_or_404),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> list[KnowledgeChunk]:
    return knowledge_chunk_service.list_for_version(
        db, document_version=version, skip=skip, limit=limit
    )
