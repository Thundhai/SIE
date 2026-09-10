from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_organization_or_404
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationRead
from app.services.organization_service import organization_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
) -> Organization:
    return organization_service.create(db, obj_in=payload)


@router.get("/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization: Organization = Depends(get_organization_or_404),
) -> Organization:
    return organization
