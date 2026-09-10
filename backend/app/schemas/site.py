import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SiteBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=255)
    status: str = Field(default="active", max_length=50)


class SiteCreate(SiteBase):
    """Body for creating a Site.

    `organization_id` is deliberately not a field here: it is taken from
    the URL path (`/organizations/{organization_id}/sites`) so a caller can
    never smuggle in a different tenant via the request body.
    """

    pass


class SiteRead(SiteBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
