"""Administrator-added users (app/services/user_provisioning_service.py).

Both routes need `users:manage` in the organization named in the path:

* `POST /organizations/{organization_id}/users`: add a person by email
  and role. If SIE creates their sign-in, Auth0 emails them a set-password link.
* `POST /organizations/{organization_id}/users/{user_id}/password-email`:
  send that email again (only for sign-ins SIE created).

Refusals are `USER_ADD_REJECTED` errors with `details.reason`, audited
with the operation and reason code, never the email.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_permission
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.errors import ApiError, ErrorCode
from app.integrations import auth0_management
from app.models.organization import Organization
from app.schemas.user_provisioning import PasswordEmailRead, UserAdd, UserAddedRead
from app.services.audit_service import AuditAction, audit_service
from app.services.permissions import Permission
from app.services.tenant_context import TenantContext
from app.services.user_provisioning_service import (
    ProvisioningError,
    user_provisioning_service,
)

router = APIRouter(tags=["users"])


def _refused(
    db: Session,
    exc: ProvisioningError,
    *,
    operation: str,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> ApiError:
    db.rollback()
    audit_service.log(
        db,
        action=AuditAction.USER_ADD_REJECTED,
        resource_type="OrganizationMembership",
        resource_id=None,
        # Only reference an organization that exists (audit_logs has a
        # foreign key; a platform administrator can name any UUID).
        organization_id=organization_id if db.get(Organization, organization_id) is not None else None,
        user_id=actor_user_id,
        metadata={"reason": exc.reason, "operation": operation},
    )
    error = ApiError(
        status_code=exc.status_code,
        code=ErrorCode.USER_ADD_REJECTED,
        message=exc.message,
        details={"reason": exc.reason, "retryable": exc.status_code == 503},
    )
    if exc.status_code == 503:
        error.headers = {"Retry-After": "5"}
    return error


@router.post(
    "/organizations/{organization_id}/users",
    response_model=UserAddedRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def add_user(
    organization_id: uuid.UUID,
    payload: UserAdd,
    response: Response,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> UserAddedRead:
    response.headers["Cache-Control"] = "no-store"
    try:
        added = user_provisioning_service.add_user(
            db,
            auth0_management.get_auth0_management_client(),
            organization_id=organization_id,
            email=payload.email,
            name=payload.name,
            role=payload.role,
            actor_user_id=context.user_id,
            actor_permissions=context.permissions,
        )
    except ProvisioningError as exc:
        raise _refused(db, exc, operation="add", organization_id=organization_id, actor_user_id=context.user_id) from exc
    return UserAddedRead(
        user_id=added.user_id,
        organization_id=added.organization_id,
        role=added.role,
        outcome=added.outcome,
        email_sent=added.email_sent,
        email_failed=added.email_failed,
    )


@router.post(
    "/organizations/{organization_id}/users/{user_id}/password-email",
    response_model=PasswordEmailRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def resend_password_email(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    response: Response,
    context: TenantContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> PasswordEmailRead:
    response.headers["Cache-Control"] = "no-store"
    try:
        user_provisioning_service.resend_password_email(
            db,
            auth0_management.get_auth0_management_client(),
            organization_id=organization_id,
            user_id=user_id,
            actor_user_id=context.user_id,
        )
    except ProvisioningError as exc:
        raise _refused(
            db, exc, operation="password_email", organization_id=organization_id, actor_user_id=context.user_id
        ) from exc
    return PasswordEmailRead(email_sent=True)
