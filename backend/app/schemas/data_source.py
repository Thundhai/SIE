import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DataSourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., min_length=1, max_length=100)
    status: str = Field(default="active", max_length=50)
    last_sync_at: datetime | None = None


class DataSourceCreate(DataSourceBase):
    """Body for creating a DataSource. `organization_id` comes from the URL path."""

    pass


class DataSourceRead(DataSourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
