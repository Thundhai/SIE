"""Invitation and account-link endpoints: the explicit ways an external
identity is bound to a SIE user (app/services/identity_link_service.py).

* Invitations live in app/api/v1/invitations.py.
* `POST /identity-links`: a platform administrator issues an
  account-link code for one existing, non-administrator user (migration
  and recovery). Platform-administrator accounts are linked only with the
  operator script, never here.
* `POST /auth/identity-links/redeem`: the person signs in with the
  identity provider, then redeems the code with their Bearer token. This
  is the one route that accepts a verified token whose identity is not
  bound yet.

Codes come back once, in the creation response, with `Cache-Control:
no-store`. Only their hashes are stored.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_authenticated_user_id, get_verified_identity_claims
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.schemas.identity_link import (
    AccountLinkCreate,
    GrantCreatedRead,
    GrantRedeem,
    GrantRedeemedRead,
)
from app.services.authorization_service import authorization_service
from app.services.identity_link_service import (
    CreatedGrant,
    GrantCreationError,
    GrantRedemptionError,
    identity_link_service,
)
from app.services.identity_service import ExternalIdentityClaims
from app.services.permissions import Permission

router = APIRouter(tags=["identity-links"])


def _created(response: Response, created: CreatedGrant) -> GrantCreatedRead:
    response.headers["Cache-Control"] = "no-store"
    grant = created.grant
    return GrantCreatedRead(
        grant_id=grant.id,
        kind=grant.kind,
        code=created.code,
        expires_at=grant.expires_at,
        organization_id=grant.organization_id,
        role=grant.role,
        target_user_id=grant.target_user_id,
    )


@router.post(
    "/identity-links",
    response_model=GrantCreatedRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_account_link(
    payload: AccountLinkCreate,
    response: Response,
    user_id: uuid.UUID = Depends(get_authenticated_user_id),
    db: Session = Depends(get_db),
) -> GrantCreatedRead:
    # organization_id=None: only a platform administrator holds users:manage
    # platform-wide (same rule as organization creation).
    if not authorization_service.can(db, user_id=user_id, permission=Permission.USERS_MANAGE, organization_id=None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Issuing an account-link code requires platform administrator privileges.",
        )
    try:
        created = identity_link_service.create_account_link(
            db, target_user_id=payload.user_id, actor_user_id=user_id, allow_platform_admin=False
        )
    except GrantCreationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _created(response, created)


@router.post("/auth/identity-links/redeem", response_model=GrantRedeemedRead)
def redeem_identity_link(
    payload: GrantRedeem,
    claims: ExternalIdentityClaims = Depends(get_verified_identity_claims),
    db: Session = Depends(get_db),
) -> GrantRedeemedRead:
    try:
        user, grant = identity_link_service.redeem(db, claims=claims, code=payload.code)
    except GrantRedemptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return GrantRedeemedRead(user_id=user.id, kind=grant.kind, organization_id=grant.organization_id)
