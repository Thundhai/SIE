"""Organization membership endpoints.

The reference implementation, in this milestone, of the full
Authentication -> Identity -> Authorization -> TenantContext pipeline: every
route here requires a (development-mode, see app/api/deps_auth.py)
authenticated user and an explicit permission check before touching the
database, rather than trusting the `organization_id` path segment on its
own. Compare with app/api/v1/sites.py / data_sources.py / organizations.py,
which predate this milestone and still trust the URL directly — see the
README's "Existing organization-scoped APIs" section for why those were
deliberately not retrofitted in the same change.

No self-registration and no email invitations here (per spec): adding a
member names an *existing* user id and is itself an administrative
operation gated by `users:manage`.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_permission
from app.models.organization_membership import OrganizationMembership
from app.schemas.organization_membership import (
    OrganizationMembershipCreate,
    OrganizationMembershipRead,
)
from app.services.errors import KnowledgeNotFoundError, KnowledgeValidationError
from app.services.membership_service import membership_service
from app.services.permissions import Permission
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/organizations/{organization_id}/members", tags=["memberships"])


@router.post("", response_model=OrganizationMembershipRead, status_code=status.HTTP_201_CREATED)
def add_member(
    organization_id: uuid.UUID,
    payload: OrganizationMembershipCreate,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> OrganizationMembership:
    try:
        return membership_service.create(
            db,
            organization_id=organization_id,
            obj_in=payload,
            actor_user_id=context.user_id,
        )
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[OrganizationMembershipRead])
def list_members(
    organization_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.USERS_READ)),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OrganizationMembership]:
    return membership_service.list_for_organization(
        db, organization_id=organization_id, skip=skip, limit=limit
    )


@router.get("/{user_id}", response_model=OrganizationMembershipRead)
def get_member(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.USERS_READ)),
    db: Session = Depends(get_db),
) -> OrganizationMembership:
    membership = membership_service.get(db, organization_id=organization_id, user_id=user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    return membership
