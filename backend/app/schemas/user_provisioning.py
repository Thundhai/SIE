import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.identity_link import InvitationCreate


class UserAdd(InvitationCreate):
    """Email (validated like an invitation's) and role, plus an optional
    display name. Organization and actor come from the path and token."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)


class UserAddedRead(BaseModel):
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    # account_created: SIE created their sign-in; they set a password from the email.
    # existing_sign_in: they already had a verified sign-in; they can sign in now.
    # existing_sie_account: they already had an SIE account; only a membership was added.
    outcome: Literal["account_created", "existing_sign_in", "existing_sie_account"]
    email_sent: bool
    # True when a set-password email was needed but Auth0 refused or was
    # unreachable; the administrator can resend it.
    email_failed: bool


class PasswordEmailRead(BaseModel):
    email_sent: bool
