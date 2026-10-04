import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_organization_or_404
from app.api.deps_auth import get_authenticated_user_id
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationRead
from app.services.authorization_service import authorization_service
from app.services.organization_service import organization_service
from app.services.permissions import Permission

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    user_id: uuid.UUID = Depends(get_authenticated_user_id),
    db: Session = Depends(get_db),
) -> Organization:
    """G3-BE-01: the organization being created doesn't exist yet, so
    there is no OrganizationMembership to check -- `require_permission`/
    `get_tenant_context` (built around an existing, path-supplied
    organization_id) don't apply here. This instead reuses the one
    precedent this codebase already has for "no organization_id, is the
    caller still authorized" -- the GLOBAL-write rule established by
    app/api/v1/knowledge.py and app/api/v1/ingestion.py:
    `authorization_service.can(organization_id=None, ...)` succeeds only
    for a PLATFORM_ADMIN, never an ordinary authenticated human, since
    there is no membership-derived role to fall back on without a tenant
    to belong to yet.
    """
    if not authorization_service.can(
        db, user_id=user_id, permission=Permission.ORGANIZATION_MANAGE, organization_id=None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Creating an organization requires platform administrator privileges.",
        )
    return organization_service.create(db, obj_in=payload)


@router.get("/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization: Organization = Depends(get_organization_or_404),
) -> Organization:
    return organization
