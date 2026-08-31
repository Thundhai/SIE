import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(default="member", max_length=50)
    status: str = Field(default="active", max_length=50)


class UserCreate(UserBase):
    """Body for creating a User. `organization_id` comes from the URL path."""

    pass


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
