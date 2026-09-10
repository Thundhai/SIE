import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataSourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., min_length=1, max_length=100)
    status: str = Field(default="active", max_length=50)
    last_sync_at: datetime | None = None
    # Enterprise Data Ingestion & Validation Foundation v0.1 additions —
    # see app/models/data_source.py's own docstring for what each means.
    system_identifier: str | None = Field(default=None, max_length=255)
    schema_version: str | None = Field(default=None, max_length=20)
    config_metadata: dict[str, Any] = Field(default_factory=dict)


class DataSourceCreate(DataSourceBase):
    """Body for creating a DataSource. `organization_id` comes from the
    authenticated caller's own authorized context, never the request body
    (see `app/api/v1/data_sources.py`). `api_client_id`, if given, must
    name a credential belonging to this same organization."""

    api_client_id: uuid.UUID | None = None


class DataSourceStatusUpdate(BaseModel):
    """Body for `PATCH .../data-sources/{id}/status` — the one mutation
    this milestone builds for an existing source (item 3's "active/
    inactive state"). Deliberately narrow: not a general-purpose update
    endpoint (see the router's own docstring for why)."""

    status: str = Field(..., max_length=50)


class DataSourceRead(DataSourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    api_client_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
