import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.permissions import OrganizationRole


class InvitationCreate(BaseModel):
    """The new member's email (stored as their account email; never matched
    against a token's email claim) and their role in this organization."""

    email: str = Field(..., min_length=3, max_length=320)
    role: OrganizationRole

    @field_validator("email")
    @classmethod
    def _plausible_email(cls, value: str) -> str:
        value = value.strip()
        local, sep, domain = value.partition("@")
        if not sep or not local or "." not in domain or any(c.isspace() for c in value):
            raise ValueError("must be an email address")
        return value


class AccountLinkCreate(BaseModel):
    user_id: uuid.UUID


class GrantCreatedRead(BaseModel):
    """`code` is shown exactly once. Pass it to the person over a trusted
    channel; they redeem it after signing in."""

    grant_id: uuid.UUID
    kind: str
    code: str
    expires_at: datetime
    organization_id: uuid.UUID | None = None
    role: str | None = None
    target_user_id: uuid.UUID | None = None


class GrantRedeem(BaseModel):
    code: str = Field(..., min_length=10, max_length=200)


class GrantRedeemedRead(BaseModel):
    user_id: uuid.UUID
    kind: str
    organization_id: uuid.UUID | None = None
