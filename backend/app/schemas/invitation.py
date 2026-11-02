import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.identity_link import InvitationCreate as _BaseInvitationCreate


class InvitationCreate(_BaseInvitationCreate):
    """`expires_in_hours` defaults to IDENTITY_LINK_GRANT_TTL_HOURS."""

    model_config = ConfigDict(extra="forbid")

    expires_in_hours: int | None = Field(default=None, ge=1, le=720)


class InvitationResend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_hours: int | None = Field(default=None, ge=1, le=720)


class InvitationRead(BaseModel):
    """Administrator view. Never includes a code or its hash."""

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: str
    status: str
    created_at: datetime
    expires_at: datetime
    created_by_user_id: uuid.UUID | None
    registration_started_at: datetime | None
    verified_at: datetime | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    accepted_user_id: uuid.UUID | None
    issue_count: int


class InvitationIssuedRead(BaseModel):
    """`code` is shown exactly once. The invitation link is
    `<frontend origin>/invite#token=<code>`: in the URL fragment, so it is
    never sent to a server or in a Referer header."""

    invitation: InvitationRead
    code: str


class InvitationToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=10, max_length=200)


class InvitationStart(InvitationToken):
    method: Literal["password", "sso"]


class InvitationAccept(InvitationToken):
    """No organization or role: those come only from the invitation."""

    full_name: str | None = Field(default=None, max_length=255)


class InvitationPublicRead(BaseModel):
    status: str
    organization_id: uuid.UUID
    organization_name: str
    role: str
    invited_email: str
    expires_at: datetime
    methods: list[str]


class InvitationAcceptRead(BaseModel):
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    outcome: Literal["account_created", "existing_account"]
