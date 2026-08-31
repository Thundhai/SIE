"""Shared FastAPI dependencies."""

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.organization import Organization
from app.services.organization_service import organization_service

__all__ = ["get_db", "get_organization_or_404"]


def get_organization_or_404(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Organization:
    """Resolve the organization named in the URL path, or 404.

    Every route nested under `/organizations/{organization_id}/...` depends
    on this so that (a) a bad organization_id fails fast with a clear 404
    instead of silently returning an empty list, and (b) the resolved,
    trusted `organization_id` is the single value passed down into the
    tenant-scoped service layer.
    """
    organization = organization_service.get(db, id=organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    return organization
