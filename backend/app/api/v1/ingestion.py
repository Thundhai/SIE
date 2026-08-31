"""Ingestion API — the one controlled entry point for uploading a file
into SIE's knowledge base.

    authenticated user -> TenantContext -> authorized organization -> ingestion
    (organization knowledge)

    authenticated user -> elevated (PLATFORM_ADMIN) permission -> ingestion
    (global knowledge — see below)

Unlike the membership endpoints (app/api/v1/memberships.py), there is no
`{organization_id}` URL segment here: a file can be ingested for GLOBAL
knowledge, which has no organization at all. `organization_id` is
instead an optional form field, and — this is the point the milestone is
explicit about — it is never trusted as proof of ownership by itself.
What decides ownership is `authorization_service.can()`:

  * `organization_id` provided -> the caller must have an ACTIVE
    membership in that organization AND its role must grant
    `knowledge:manage` (`can()` returns False otherwise, per the normal
    membership+role check — see app/services/authorization_service.py).
  * `organization_id` omitted (global knowledge) -> `can()` with no
    organization only ever succeeds for a PLATFORM_ADMIN. Omitting the
    field is *not* a way to create global knowledge with a lesser
    permission than an authorized organization upload would need — if
    anything it requires more.

This route calls `authorization_service.can()` directly rather than the
`require_permission`/`get_tenant_context` dependencies used elsewhere
(app/api/deps_auth.py), because those are built around a path
`organization_id` this route doesn't have — `organization_id` here is
caller-supplied *intent*, checked, not a trusted path segment.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_dev_authenticated_user_id
from app.ingestion.pipeline import UnsupportedFileTypeError
from app.schemas.ingestion import IngestionResponse
from app.services.authorization_service import authorization_service
from app.services.errors import KnowledgeNotFoundError, KnowledgeValidationError
from app.services.ingestion_service import IngestionRequestError, ingestion_service
from app.services.permissions import Permission

router = APIRouter(prefix="/knowledge", tags=["ingestion"])


@router.post("/ingestion", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED)
async def ingest_file(
    file: UploadFile = File(...),
    source_id: uuid.UUID = Form(...),
    organization_id: uuid.UUID | None = Form(default=None),
    document_id: uuid.UUID | None = Form(default=None),
    title: str | None = Form(default=None),
    document_type: str | None = Form(default=None),
    user_id: uuid.UUID = Depends(get_dev_authenticated_user_id),
    db: Session = Depends(get_db),
) -> IngestionResponse:
    if not authorization_service.can(
        db,
        user_id=user_id,
        permission=Permission.KNOWLEDGE_MANAGE,
        organization_id=organization_id,
    ):
        detail = (
            "Missing knowledge:manage permission in the given organization."
            if organization_id is not None
            else "Ingesting GLOBAL knowledge requires platform-wide knowledge:manage access."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    file_bytes = await file.read()

    try:
        outcome = ingestion_service.ingest(
            db,
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            source_id=source_id,
            organization_id=organization_id,
            document_id=document_id,
            title=title,
            document_type=document_type,
            actor_user_id=user_id,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except IngestionRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return IngestionResponse(
        ingestion_job_id=outcome.job.id,
        file_id=outcome.file.id,
        detected_media_type=outcome.file.detected_media_type,
        file_size=outcome.file.file_size,
        content_hash=outcome.file.content_hash,
        ingestion_status=outcome.job.status,
        extraction_status=outcome.file.extraction_status,
        extraction_method=outcome.file.extraction_method,
        document_id=outcome.document.id if outcome.document else None,
        version_id=outcome.version_id,
        chunk_count=outcome.chunk_count,
        warnings=outcome.warnings,
    )
