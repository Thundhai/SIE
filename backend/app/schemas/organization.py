import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=255)
    status: str = Field(default="active", max_length=50)


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationRead(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
