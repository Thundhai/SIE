import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    status: str = Field(default="active", max_length=50)


class UserCreate(UserBase):
    """Body for creating a User — a platform identity, not an
    organization-scoped resource (see app/models/user.py). There is no
    `role` field: a role is per-organization, granted via
    OrganizationMembership, not a property of the user itself.
    `organization_id` here is optional and only ever sets the convenience
    "default organization" — it grants no access by itself.
    """

    organization_id: uuid.UUID | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    platform_role: str | None
    created_at: datetime
    updated_at: datetime
