"""Ingestion source management — Enterprise Data Ingestion & Validation
Foundation v0.1, item 3's "Ingestion source" and item 19's "ingestion
source management" scope.

**This is `DataSource`, reused as the registered-ingestion-source
concept, not a new table** — see `app/models/data_source.py`'s own
docstring for why. What changes this milestone is authentication: these
two routes had **no authentication or authorization check at all**
before this milestone (a pre-existing gap, structurally identical to the
one closed in `app/api/v1/knowledge.py` last milestone) — every route
here now goes through the same `RequestContext`/`authorize_context()`
pipeline every other organization-scoped route uses, human or machine.

    human OR machine caller -> RequestContext -> authorize_context(SAFETY_DATA_WRITE|READ, organization_id)
        -> DataSourceService -> DataSource row

`organization_id` is a required URL path segment here (matching
`app/api/v1/api_clients.py`'s existing convention for this same
"nested under one organization" shape), so
`app.api.deps_context.require_context_permission()` (which expects
`organization_id` as a *query* parameter, for GLOBAL-capable routes)
doesn't fit directly — `authorize_context()` itself is called explicitly
instead, exactly like `app/api/v1/knowledge.py`'s own
`_authorize_read()`/`_authorize_manage()` helpers.

**Permission mapping (item 19 — reusing the existing vocabulary, never a
second one).** Registering/updating where safety data is expected to
come from is treated as part of the same `safety_data:write` capability
that lets a caller push safety data in the first place — there is no
separate "source admin" permission invented for this. Reading source
records uses `safety_data:read`.

**Deliberately narrow mutation surface.** Only `status` can be changed
after creation (`PATCH .../status`) — a full general-purpose update
endpoint was out of scope for this milestone; see the README's
"Enterprise Data Ingestion" section for this documented limitation.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, authorize_context, get_request_context
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.models.api_client import ApiClient
from app.models.data_source import DataSource
from app.models.organization import Organization
from app.schemas.data_source import (
    DataSourceCreate,
    DataSourceRead,
    DataSourceStatusUpdate,
)
from app.services.audit_service import AuditAction, audit_service
from app.services.data_source_service import data_source_service
from app.services.permissions import Permission

router = APIRouter(prefix="/organizations/{organization_id}/data-sources", tags=["data-sources"])


def _authorize(db: Session, context: RequestContext, organization_id: uuid.UUID, *, permission: Permission) -> None:
    # A missing organization 404s before authorization is even evaluated
    # -- restores app/api/deps.py::get_organization_or_404's existing-org
    # guarantee (this router no longer uses that dependency directly,
    # since it needs RequestContext, not TenantContext) and, as a side
    # effect, avoids a raw FK-constraint IntegrityError for a
    # platform-admin caller (whose authorize_context() check alone would
    # otherwise pass unconditionally before ever touching the database).
    if db.get(Organization, organization_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    if not authorize_context(db, context, permission=permission, organization_id=organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing {permission.value} permission in the requested organization.",
        )


def _validate_api_client_ownership(db: Session, *, organization_id: uuid.UUID, api_client_id: uuid.UUID) -> None:
    """A source may only be linked to a credential that belongs to the
    *same* organization — never a cross-tenant reference, even an
    innocuous-looking display link (item 10's tenant-isolation principle
    applied to this association too)."""
    owned = db.get(ApiClient, api_client_id)
    if owned is None or owned.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="api_client_id not found in this organization."
        )


@router.post(
    "",
    response_model=DataSourceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_data_source(
    organization_id: uuid.UUID,
    payload: DataSourceCreate,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> DataSource:
    _authorize(db, context, organization_id, permission=Permission.SAFETY_DATA_WRITE)
    if payload.api_client_id is not None:
        _validate_api_client_ownership(db, organization_id=organization_id, api_client_id=payload.api_client_id)

    source = data_source_service.create(db, organization_id=organization_id, obj_in=payload)
    audit_service.log(
        db,
        action=AuditAction.INGESTION_SOURCE_CREATED,
        resource_type="DataSource",
        resource_id=source.id,
        organization_id=organization_id,
        user_id=context.user_id,
        metadata={"name": source.name, "source_type": source.source_type, "caller_kind": context.kind},
    )
    return source


@router.get(
    "", response_model=list[DataSourceRead], dependencies=[Depends(require_rate_limit(RateLimitClass.READ))]
)
def list_data_sources(
    organization_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DataSource]:
    _authorize(db, context, organization_id, permission=Permission.SAFETY_DATA_READ)
    return data_source_service.list(db, organization_id=organization_id, skip=skip, limit=limit)


@router.get(
    "/{source_id}",
    response_model=DataSourceRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_data_source(
    organization_id: uuid.UUID,
    source_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> DataSource:
    _authorize(db, context, organization_id, permission=Permission.SAFETY_DATA_READ)
    source = data_source_service.get(db, organization_id=organization_id, id=source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found.")
    return source


@router.patch(
    "/{source_id}/status",
    response_model=DataSourceRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def update_data_source_status(
    organization_id: uuid.UUID,
    source_id: uuid.UUID,
    payload: DataSourceStatusUpdate,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> DataSource:
    _authorize(db, context, organization_id, permission=Permission.SAFETY_DATA_WRITE)
    source = data_source_service.get(db, organization_id=organization_id, id=source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found.")

    previous_status = source.status
    source.status = payload.status
    db.commit()
    db.refresh(source)
    audit_service.log(
        db,
        action=AuditAction.INGESTION_SOURCE_STATUS_CHANGED,
        resource_type="DataSource",
        resource_id=source.id,
        organization_id=organization_id,
        user_id=context.user_id,
        metadata={"previous_status": previous_status, "new_status": source.status, "caller_kind": context.kind},
    )
    return source
