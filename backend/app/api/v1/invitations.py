"""Invitation-based registration (app/services/invitation_service.py).

Administrator routes. Each needs `users:manage` in the organization in the
path, and only sees that organization's invitations:

* `POST   /organizations/{organization_id}/invitations`: invite (the code is shown once)
* `GET    /organizations/{organization_id}/invitations[?status=]`: list
* `POST   /organizations/{organization_id}/invitations/{invitation_id}/resend`: new code; the old link dies
* `POST   /organizations/{organization_id}/invitations/{invitation_id}/revoke`

Invitee routes. These are rate-limited per client IP and take the code in
the body, never the URL:

* `POST /invitations/inspect`: what the invitation is for (no sign-in)
* `POST /invitations/start`: record the chosen sign-in method (no sign-in)
* `POST /auth/invitations/accept`: after signing in with the identity provider

Refusals are `INVITATION_REJECTED` errors with `details.reason`.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_verified_identity_claims_and_token, require_permission
from app.api.deps_public_rate_limit import require_invitation_rate_limit
from app.core.errors import ApiError, ErrorCode
from app.models.identity_link_grant import ALL_STATUSES, IdentityLinkGrant
from app.schemas.invitation import (
    InvitationAccept,
    InvitationAcceptRead,
    InvitationCreate,
    InvitationIssuedRead,
    InvitationPublicRead,
    InvitationRead,
    InvitationResend,
    InvitationStart,
    InvitationToken,
)
from app.services.identity_link_service import CreatedGrant
from app.services.invitation_service import (
    METHODS,
    InvitationError,
    InvitationView,
    effective_status,
    invitation_service,
)
from app.services.permissions import Permission
from app.services.tenant_context import TenantContext
from app.services.verified_email import resolve_verified_email

router = APIRouter(tags=["invitations"])


def _error(exc: InvitationError) -> ApiError:
    return ApiError(
        status_code=exc.status_code,
        code=ErrorCode.INVITATION_REJECTED,
        message=exc.message,
        details={"reason": exc.reason},
    )


def _read(grant: IdentityLinkGrant) -> InvitationRead:
    return InvitationRead(
        id=grant.id,
        organization_id=grant.organization_id,
        email=grant.invited_email,
        role=grant.role,
        status=effective_status(grant),
        created_at=grant.created_at,
        expires_at=grant.expires_at,
        created_by_user_id=grant.created_by_user_id,
        registration_started_at=grant.registration_started_at,
        verified_at=grant.verified_at,
        accepted_at=grant.redeemed_at,
        revoked_at=grant.revoked_at,
        accepted_user_id=grant.target_user_id,
        issue_count=grant.issue_count,
    )


def _issued(response: Response, created: CreatedGrant) -> InvitationIssuedRead:
    response.headers["Cache-Control"] = "no-store"
    return InvitationIssuedRead(invitation=_read(created.grant), code=created.code)


def _public(view: InvitationView) -> InvitationPublicRead:
    return InvitationPublicRead(
        status=view.status,
        organization_id=view.organization_id,
        organization_name=view.organization_name,
        role=view.role,
        invited_email=view.invited_email,
        expires_at=view.expires_at,
        methods=list(METHODS),
    )


# --- Administrator -----------------------------------------------------------------------


@router.post(
    "/organizations/{organization_id}/invitations",
    response_model=InvitationIssuedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    organization_id: uuid.UUID,
    payload: InvitationCreate,
    response: Response,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> InvitationIssuedRead:
    try:
        created = invitation_service.create(
            db,
            organization_id=organization_id,
            email=payload.email,
            role=payload.role,
            actor_user_id=context.user_id,
            actor_permissions=context.permissions,
            expires_in_hours=payload.expires_in_hours,
        )
    except InvitationError as exc:
        raise _error(exc) from exc
    return _issued(response, created)


@router.get("/organizations/{organization_id}/invitations", response_model=list[InvitationRead])
def list_invitations(
    organization_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(" + "|".join(ALL_STATUSES) + ")$"),
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> list[InvitationRead]:
    return [_read(g) for g in invitation_service.list(db, organization_id=organization_id, status=status_filter)]


@router.post(
    "/organizations/{organization_id}/invitations/{invitation_id}/resend",
    response_model=InvitationIssuedRead,
)
def resend_invitation(
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    response: Response,
    payload: InvitationResend | None = None,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> InvitationIssuedRead:
    try:
        created = invitation_service.resend(
            db,
            organization_id=organization_id,
            invitation_id=invitation_id,
            actor_user_id=context.user_id,
            expires_in_hours=payload.expires_in_hours if payload else None,
        )
    except InvitationError as exc:
        raise _error(exc) from exc
    return _issued(response, created)


@router.post("/organizations/{organization_id}/invitations/{invitation_id}/revoke", response_model=InvitationRead)
def revoke_invitation(
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> InvitationRead:
    try:
        grant = invitation_service.revoke(
            db, organization_id=organization_id, invitation_id=invitation_id, actor_user_id=context.user_id
        )
    except InvitationError as exc:
        raise _error(exc) from exc
    return _read(grant)


# --- Invitee -----------------------------------------------------------------------------


@router.post(
    "/invitations/inspect",
    response_model=InvitationPublicRead,
    dependencies=[Depends(require_invitation_rate_limit("inspect"))],
)
def inspect_invitation(payload: InvitationToken, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return _public(invitation_service.inspect(db, code=payload.token))
    except InvitationError as exc:
        raise _error(exc) from exc


@router.post(
    "/invitations/start",
    response_model=InvitationPublicRead,
    dependencies=[Depends(require_invitation_rate_limit("start"))],
)
def start_invitation(payload: InvitationStart, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return _public(invitation_service.start(db, code=payload.token, method=payload.method))
    except InvitationError as exc:
        raise _error(exc) from exc


@router.post(
    "/auth/invitations/accept",
    response_model=InvitationAcceptRead,
    dependencies=[Depends(require_invitation_rate_limit("accept"))],
)
def accept_invitation(
    payload: InvitationAccept,
    identity=Depends(get_verified_identity_claims_and_token),
    db: Session = Depends(get_db),
) -> InvitationAcceptRead:
    claims, access_token = identity
    verified = resolve_verified_email(claims, access_token)
    try:
        accepted = invitation_service.accept(
            db, claims=claims, verified=verified, code=payload.token, full_name=payload.full_name
        )
    except InvitationError as exc:
        raise _error(exc) from exc
    return InvitationAcceptRead(
        organization_id=accepted.organization_id,
        user_id=accepted.user.id,
        role=accepted.role,
        outcome=accepted.outcome,
    )
