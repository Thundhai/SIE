from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_organization_or_404
from app.models.data_source import DataSource
from app.models.organization import Organization
from app.schemas.data_source import DataSourceCreate, DataSourceRead
from app.services.data_source_service import data_source_service

router = APIRouter(
    prefix="/organizations/{organization_id}/data-sources",
    tags=["data-sources"],
    dependencies=[Depends(get_organization_or_404)],
)


@router.post("", response_model=DataSourceRead, status_code=201)
def create_data_source(
    payload: DataSourceCreate,
    organization: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
) -> DataSource:
    return data_source_service.create(db, organization_id=organization.id, obj_in=payload)


@router.get("", response_model=list[DataSourceRead])
def list_data_sources(
    organization: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DataSource]:
    return data_source_service.list(db, organization_id=organization.id, skip=skip, limit=limit)
