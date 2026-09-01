"""Machine-client (API client) management — milestone item 10's
"credential rotation/revocation" requirement, exposed to human
administrators. Gated by `Permission.USERS_MANAGE` — provisioning a
credential that can write organizational data on a system's behalf is an
administrative action, the same permission tier
`app/api/v1/memberships.py` already requires for adding a human member.

Every response here (`ApiClientRead`) omits the secret entirely except
immediately after creation/rotation (`ApiClientCreatedRead`) — see
`app/services/api_client_service.py`'s own docstring for why the raw
secret is never stored or shown again afterward.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_permission
from app.models.api_client import ApiClient
from app.schemas.intelligence import ApiClientCreatedRead, ApiClientCreateRequest, ApiClientRead
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/organizations/{organization_id}/api-clients", tags=["api-clients"])


def _get_or_404(db: Session, *, organization_id: uuid.UUID, client_id: uuid.UUID) -> ApiClient:
    api_client = db.execute(
        select(ApiClient).where(ApiClient.id == client_id, ApiClient.organization_id == organization_id)
    ).scalar_one_or_none()
    if api_client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API client not found")
    return api_client


@router.post("", response_model=ApiClientCreatedRead, status_code=status.HTTP_201_CREATED)
def create_api_client(
    organization_id: uuid.UUID,
    body: ApiClientCreateRequest,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> ApiClientCreatedRead:
    credential = api_client_service.create(
        db, organization_id=organization_id, name=body.name, scopes=body.scopes
    )
    return ApiClientCreatedRead(**_read_fields(credential.api_client), secret=credential.secret)


@router.get("", response_model=list[ApiClientRead])
def list_api_clients(
    organization_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> list[ApiClientRead]:
    rows = db.execute(select(ApiClient).where(ApiClient.organization_id == organization_id)).scalars().all()
    return [ApiClientRead(**_read_fields(c)) for c in rows]


@router.post("/{client_id}/rotate", response_model=ApiClientCreatedRead)
def rotate_api_client_secret(
    organization_id: uuid.UUID,
    client_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> ApiClientCreatedRead:
    api_client = _get_or_404(db, organization_id=organization_id, client_id=client_id)
    credential = api_client_service.rotate_secret(db, api_client=api_client)
    return ApiClientCreatedRead(**_read_fields(credential.api_client), secret=credential.secret)


@router.post("/{client_id}/revoke", response_model=ApiClientRead)
def revoke_api_client(
    organization_id: uuid.UUID,
    client_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> ApiClientRead:
    api_client = _get_or_404(db, organization_id=organization_id, client_id=client_id)
    api_client = api_client_service.revoke(db, api_client=api_client)
    return ApiClientRead(**_read_fields(api_client))


def _read_fields(api_client: ApiClient) -> dict:
    return {
        "id": api_client.id,
        "organization_id": api_client.organization_id,
        "name": api_client.name,
        "client_id": api_client.client_id,
        "secret_prefix": api_client.secret_prefix,
        "scopes": api_client.scopes,
        "status": api_client.status,
        "created_at": api_client.created_at,
        "last_used_at": api_client.last_used_at,
        "rotated_at": api_client.rotated_at,
        "revoked_at": api_client.revoked_at,
    }
