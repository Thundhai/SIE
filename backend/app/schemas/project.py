"""Project & ProjectSite HTTP response shapes — SIE Milestone 35:
Organizational & Operational Scope Foundation v0.1."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project_enums import ProjectStatus


class ProjectCreate(BaseModel):
    """Body for `POST /projects`. `organization_id` is deliberately not
    a field here — it is the authorize-then-trust query parameter every
    other route in this milestone's own domain already uses (mirrors
    `app/schemas/risk_assessment.py::RiskAssessmentCreate`'s own
    documented reasoning), never a client-suppliable value."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=100)
    status: ProjectStatus = ProjectStatus.ACTIVE
    description: str | None = Field(default=None, max_length=4000)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str | None
    status: ProjectStatus
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProjectListRead(BaseModel):
    items: list[ProjectRead]
    total: int
    page: int
    page_size: int


class ProjectSiteCreate(BaseModel):
    """Body for `POST /projects/{project_id}/sites` — `project_id`
    itself comes from the URL path, never the body."""

    model_config = ConfigDict(extra="forbid")

    site_id: uuid.UUID


class ProjectSiteSummaryRead(BaseModel):
    """A Site as it appears nested inside a Project/Site relationship
    response — deliberately minimal (id + name), mirroring
    `IntelligenceDecisionActionRead`'s own "small summary, not the full
    resource" precedent."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ProjectSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: ProjectStatus


__all__ = [
    "ProjectCreate",
    "ProjectRead",
    "ProjectListRead",
    "ProjectSiteCreate",
    "ProjectSiteSummaryRead",
    "ProjectSummaryRead",
]
