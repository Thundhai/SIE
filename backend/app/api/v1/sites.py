from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_organization_or_404
from app.models.organization import Organization
from app.models.site import Site
from app.schemas.site import SiteCreate, SiteRead
from app.services.site_service import site_service

router = APIRouter(
    prefix="/organizations/{organization_id}/sites",
    tags=["sites"],
    dependencies=[Depends(get_organization_or_404)],
)


@router.post("", response_model=SiteRead, status_code=201)
def create_site(
    payload: SiteCreate,
    organization: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
) -> Site:
    return site_service.create(db, organization_id=organization.id, obj_in=payload)


@router.get("", response_model=list[SiteRead])
def list_sites(
    organization: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Site]:
    return site_service.list(db, organization_id=organization.id, skip=skip, limit=limit)
